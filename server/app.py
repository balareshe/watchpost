#!/usr/bin/env python3
"""站点事件 / 公告 / 维护窗口 API（标准库，无第三方依赖）。

公开 GET：
  /api/incidents  /api/announcements  /api/maintenance
管理写操作（Authorization: Bearer <ADMIN_TOKEN>）：
  POST/PATCH/DELETE 同上路径
数据存 /data/status-data.json，原子写入。
"""
import datetime as dt
import hashlib
import json
import os
import secrets
import smtplib
import threading
import time
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = os.environ.get("DATA_FILE", "/data/status-data.json")
TOKEN = (os.environ.get("ADMIN_TOKEN") or "").strip()
TZ = dt.timezone(dt.timedelta(hours=8))
LOCK = threading.Lock()

# ---- 登录 / 邮件 ----
ADMIN_EMAILS = {e.strip().lower() for e in (os.environ.get("ADMIN_EMAILS") or "").split(",") if e.strip()}
SMTP_HOST = (os.environ.get("SMTP_HOST") or "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT") or 465)
SMTP_USER = (os.environ.get("SMTP_USER") or "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS") or ""
SMTP_FROM = (os.environ.get("SMTP_FROM") or SMTP_USER).strip()
SMTP_SECURE = (os.environ.get("SMTP_SECURE") or "1") != "0"
DEV_ECHO = (os.environ.get("DEV_ECHO_CODE") or "") == "1"
SESSION_TTL = 7 * 86400
CODE_TTL = 600
CODE_RESEND = 60
CODE_MAX_PER_HOUR = 5
SESSIONS_FILE = os.path.join(os.path.dirname(DATA), "sessions.json")
SITE_URL = (os.environ.get("SITE_URL") or "https://status.example.com").rstrip("/")
try:
    APP_VERSION = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION"), encoding="utf-8").read().strip()
except OSError:
    APP_VERSION = "dev"
CODES = {}      # email -> {"hash", "exp", "tries", "sent"}
IP_CODES = {}   # ip -> [timestamps]
IP_LIMIT_PER_HOUR = 10
CODE_SENT = {}  # email -> list of timestamps

STATUSES = ("investigating", "identified", "in_progress", "monitoring", "resolved")
ROLES = ("admin", "maintainer", "viewer")
# 严重程度：critical 重大 / major 严重 / minor 一般 / info 提示 / maintenance 维护
SEVERITIES = ("critical", "major", "minor", "info", "maintenance")
SEVERITY_ALIASES = {"down": "critical", "warn": "minor"}
COLLECTIONS = ("incidents", "announcements", "maintenance", "nodes", "users")


def now_iso():
    return dt.datetime.now(TZ).isoformat(timespec="seconds")


def load():
    try:
        with open(DATA, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, ValueError):
        data = {}
        legacy = os.path.join(os.path.dirname(DATA), "incidents.json")
        try:
            with open(legacy, encoding="utf-8") as fh:
                old = json.load(fh)
            if isinstance(old, dict) and isinstance(old.get("incidents"), list):
                data["incidents"] = old["incidents"]
                print("migrated legacy incidents.json -> %s" % DATA, flush=True)
        except (OSError, ValueError):
            pass
    for key in COLLECTIONS:
        if not isinstance(data.get(key), list):
            data[key] = []
    if not isinstance(data.get("settings"), dict):
        data["settings"] = {}
    return data


def save(data):
    tmp = DATA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, DATA)


DEFAULT_SETTINGS = {
    "siteName": "站点状态",
    "pageTitle": "站点状态",
    "subtitle": "数据每 30 秒刷新一次",
    "favicon": "",
    "slowMs": 800,
    "templates": {
        "downTitle": "{name} 无法访问（{time} 起）",
        "downSummary": "自动监控发现「{name}」无法正常访问：连续 {fails} 次探测失败，"
                       "立即重试 {retries} 次仍未恢复，异常始于 {startedAt}。已自动创建工单，等待值班确认。",
        "downUpdate": "最近一次探测：{status}，{cost}。自动监控已创建工单。",
        "slowTitle": "{name} 响应变慢（{time} 起）",
        "slowSummary": "自动监控发现「{name}」响应变慢：连续 {streak} 次探测耗时超过 {threshold} ms，"
                       "最近一次 {lastMs} ms。可用性未受影响，已记录以便观察。",
        "slowUpdate": "最近一次探测 {lastMs} ms，超过阈值 {threshold} ms。",
    },
    "notify": {
        "enabled": False,
        "smtpHost": "",
        "smtpPort": 465,
        "smtpUser": "",
        "smtpPass": "",
        "smtpFrom": "",
        "smtpSecure": True,
        "subject": "[{site}] {title}",
        "body": "{time}\\n{site} 检测到异常：{title}\\n\\n受影响组件：{components}\\n严重程度：{severity}\\n\\n{summary}\\n\\n查看详情：{url}",
    },
}

PUBLIC_SETTING_KEYS = ("siteName", "pageTitle", "subtitle", "favicon", "slowMs")
MASKED = "********"


def get_settings():
    with LOCK:
        data = load()
    merged = json.loads(json.dumps(DEFAULT_SETTINGS))
    stored = data.get("settings") or {}
    for key, value in stored.items():
        if key in ("notify", "templates") and isinstance(value, dict):
            merged[key].update(value)
        elif key in merged:
            merged[key] = value
    return merged


def save_settings(patch):
    with LOCK:
        data = load()
        current = data.get("settings") or {}
        for key, value in patch.items():
            if key in ("notify", "templates") and isinstance(value, dict):
                incoming = dict(value)
                if key == "notify" and incoming.get("smtpPass") == MASKED:
                    incoming.pop("smtpPass", None)
                current.setdefault(key, {}).update(incoming)
            elif key in DEFAULT_SETTINGS:
                current[key] = value
        data["settings"] = current
        save(data)
    return get_settings()


def new_id(prefix=""):
    return prefix + dt.datetime.now(TZ).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3)


def norm_severity(value):
    value = str(value or "").strip().lower()
    value = SEVERITY_ALIASES.get(value, value)
    return value if value in SEVERITIES else "minor"


def clean_list(value, limit=20):
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        text = str(item).strip()
        if text and len(text) <= 60:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def text(value, limit=600):
    return str(value or "").strip()[:limit]


# ---------- 各集合的构造与更新 ----------

def build_incident(body):
    status = body.get("status") if body.get("status") in STATUSES else "investigating"
    started = text(body.get("startedAt"), 40) or now_iso()
    incident = {
        "id": new_id(),
        "title": text(body.get("title"), 120) or "服务异常",
        "titleEn": text(body.get("titleEn"), 160),
        "status": status,
        "severity": norm_severity(body.get("severity")),
        "startedAt": started,
        "resolvedAt": started if status == "resolved" else None,
        "summary": text(body.get("summary")),
        "summaryEn": text(body.get("summaryEn")),
        "affected": clean_list(body.get("affected")),
        "owner": text(body.get("owner"), 40),
        "auto": bool(body.get("auto")),
        "silent": bool(body.get("silent")),
        "updates": [],
        "createdAt": now_iso(),
    }
    first = text(body.get("firstUpdate"))
    if first:
        incident["updates"].append({
            "at": now_iso(), "status": status, "text": first,
            "textEn": text(body.get("firstUpdateEn")), "author": incident["owner"],
        })
    return incident


def build_announcement(body):
    return {
        "id": new_id(),
        "title": text(body.get("title"), 120) or "公告",
        "body": text(body.get("body"), 2000),
        "level": body.get("level") if body.get("level") in ("info", "warning") else "info",
        "pinned": bool(body.get("pinned")),
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }


def build_maintenance(body):
    return {
        "id": new_id(),
        "title": text(body.get("title"), 120) or "维护窗口",
        "startAt": text(body.get("startAt"), 40),
        "endAt": text(body.get("endAt"), 40),
        "affected": clean_list(body.get("affected")),
        "note": text(body.get("note")),
        "createdAt": now_iso(),
    }


def build_node(body):
    return {
        "id": new_id("n"),
        "name": text(body.get("name"), 60) or "新节点",
        "url": text(body.get("url"), 300),
        "interval": max(30, min(int(body.get("interval") or 60), 3600)),
        "order": int(body.get("order") or 0),
        "slowMs": body.get("slowMs") if isinstance(body.get("slowMs"), (int, float)) else None,
        "builtin": bool(body.get("builtin")),
        "enabled": body.get("enabled", True) is not False,
        "createdAt": now_iso(),
    }


def build_user(body):
    return {
        "id": new_id("u"),
        "email": (text(body.get("email"), 120) or "").lower(),
        "name": text(body.get("name"), 40),
        "role": body.get("role") if body.get("role") in ROLES else "viewer",
        "enabled": body.get("enabled", True) is not False,
        "createdAt": now_iso(),
        "lastLoginAt": None,
    }


BUILDERS = {
    "incidents": build_incident,
    "announcements": build_announcement,
    "maintenance": build_maintenance,
    "nodes": build_node,
    "users": build_user,
}


def apply_update(name, item, body):
    if name == "incidents":
        if "status" in body and body["status"] in STATUSES:
            item["status"] = body["status"]
            item["resolvedAt"] = now_iso() if body["status"] == "resolved" else None
        for key in ("title", "titleEn", "summary", "summaryEn", "owner"):
            if key in body:
                item[key] = text(body[key])
        if "affected" in body:
            item["affected"] = clean_list(body["affected"])
        if "severity" in body:
            item["severity"] = norm_severity(body["severity"])
    elif name == "announcements":
        for key in ("title", "body"):
            if key in body:
                item[key] = text(body[key], 2000)
        if "level" in body and body["level"] in ("info", "warning"):
            item["level"] = body["level"]
        if "pinned" in body:
            item["pinned"] = bool(body["pinned"])
        item["updatedAt"] = now_iso()
    elif name == "users":
        if "email" in body:
            item["email"] = text(body["email"], 120).lower()
        if "name" in body:
            item["name"] = text(body["name"], 40)
        if "role" in body:
            item["role"] = body["role"] if body["role"] in ROLES else "viewer"
        if "enabled" in body:
            item["enabled"] = bool(body["enabled"])
    elif name == "nodes":
        if "name" in body:
            item["name"] = text(body["name"], 60)
        if "url" in body:
            item["url"] = text(body["url"], 300)
        if "interval" in body:
            try:
                item["interval"] = max(30, min(int(body["interval"]), 3600))
            except (TypeError, ValueError):
                pass
        if "order" in body:
            try:
                item["order"] = int(body["order"])
            except (TypeError, ValueError):
                pass
        if "slowMs" in body:
            value = body["slowMs"]
            item["slowMs"] = value if isinstance(value, (int, float)) else None
        if "enabled" in body:
            item["enabled"] = bool(body["enabled"])
    elif name == "maintenance":
        for key in ("title", "startAt", "endAt", "note"):
            if key in body:
                item[key] = text(body[key], 2000 if key == "note" else 120)
        if "affected" in body:
            item["affected"] = clean_list(body["affected"])
    return item


# ---------------- 登录与邮件 ----------------

def load_sessions():
    try:
        with open(SESSIONS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_sessions(data):
    os.makedirs(os.path.dirname(SESSIONS_FILE) or ".", exist_ok=True)
    tmp = SESSIONS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, SESSIONS_FILE)


def session_user(sid):
    """返回 {"email", "role"} 或 None。"""
    if not sid:
        return None
    sessions = load_sessions()
    item = sessions.get(sid)
    if not item:
        return None
    if item.get("exp", 0) < time.time():
        sessions.pop(sid, None)
        save_sessions(sessions)
        return None
    email = item.get("email")
    role = item.get("role") or "admin"
    return {"email": email, "role": role}


def session_email(sid):
    user = session_user(sid)
    return user["email"] if user else None


def find_user(data, email):
    email = (email or "").lower()
    for user in data.get("users", []):
        if (user.get("email") or "").lower() == email:
            return user
    return None


def ensure_users():
    """首次启动时用 ADMIN_EMAILS 播种管理员账号。"""
    with LOCK:
        data = load()
        if data["users"]:
            return
        for email in sorted(ADMIN_EMAILS):
            data["users"].append(build_user({"email": email, "role": "admin"}))
        if data["users"]:
            save(data)
            print("seeded %d admin user(s) from ADMIN_EMAILS" % len(data["users"]), flush=True)


def allowed_user(email):
    """登录校验：用户存在且启用（ADMIN_EMAILS 始终放行，防止把自己锁在外面）。"""
    email = (email or "").lower()
    if email in ADMIN_EMAILS:
        return True
    with LOCK:
        data = load()
    user = find_user(data, email)
    return bool(user and user.get("enabled", True))


def create_session(email, role="admin"):
    sid = secrets.token_urlsafe(32)
    sessions = load_sessions()
    now = time.time()
    sessions = {k: v for k, v in sessions.items() if v.get("exp", 0) > now}
    sessions[sid] = {"email": email, "role": role, "exp": now + SESSION_TTL, "at": now}
    save_sessions(sessions)
    return sid


def drop_session(sid):
    sessions = load_sessions()
    if sid in sessions:
        sessions.pop(sid)
        save_sessions(sessions)


def resolve_smtp():
    """后台「通知」页配置优先，未配置时回落到环境变量。"""
    cfg = (get_settings().get("notify") or {})
    host = (cfg.get("smtpHost") or SMTP_HOST or "").strip()
    user = (cfg.get("smtpUser") or SMTP_USER or "").strip()
    password = cfg.get("smtpPass") or SMTP_PASS or ""
    sender = (cfg.get("smtpFrom") or SMTP_FROM or user or "").strip()
    try:
        port = int(cfg.get("smtpPort") or SMTP_PORT)
    except (TypeError, ValueError):
        port = SMTP_PORT
    secure = cfg.get("smtpSecure")
    if secure is None:
        secure = SMTP_SECURE
    return {"host": host, "port": port, "user": user, "password": password,
            "sender": sender, "secure": bool(secure)}


def smtp_send(to_addr, subject, body, cfg=None):
    cfg = cfg or resolve_smtp()
    if not cfg["host"] or not cfg["user"]:
        raise RuntimeError("邮件服务未配置")
    msg = EmailMessage()
    msg["From"] = cfg["sender"] or cfg["user"]
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    if cfg["secure"]:
        server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15)
    else:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
        server.starttls()
    try:
        server.login(cfg["user"], cfg["password"])
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def render_template(tpl, ctx):
    out = tpl
    for key, value in ctx.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def notify_incident(incident, kind="new"):
    """给所有启用用户发邮件；返回 (sent, failed, skipped)。"""
    settings = get_settings()
    notify = settings.get("notify") or {}
    cfg = resolve_smtp()
    with LOCK:
        data = load()
    emails = [u.get("email") for u in data.get("users", [])
              if u.get("email") and u.get("enabled", True)]
    if not notify.get("enabled"):
        print("notify skipped: disabled, %d recipient(s)" % len(emails), flush=True)
        return 0, 0, len(emails)
    if not cfg["host"] or not cfg["user"]:
        print("notify skipped: smtp not configured, %d recipient(s)" % len(emails), flush=True)
        return 0, 0, len(emails)

    site = settings.get("siteName") or "站点状态"
    ctx = {
        "site": site,
        "title": incident.get("title") or "",
        "components": "、".join(incident.get("affected") or []) or "—",
        "severity": "不可用" if incident.get("severity") == "down" else "部分异常",
        "summary": incident.get("summary") or "",
        "status": incident.get("status") or "",
        "time": dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "url": SITE_URL + "/incident.html?id=" + str(incident.get("id") or ""),
    }
    subject_tpl = notify.get("subject") or DEFAULT_SETTINGS["notify"]["subject"]
    body_tpl = notify.get("body") or DEFAULT_SETTINGS["notify"]["body"]
    if kind == "resolved":
        subject_tpl = "[已恢复] " + subject_tpl
        ctx["title"] = "%s（已恢复）" % ctx["title"]
    subject = render_template(subject_tpl, ctx)
    body = render_template(body_tpl, ctx)

    sent = failed = 0
    for email in emails:
        try:
            smtp_send(email, subject, body, cfg)
            sent += 1
        except Exception as exc:
            failed += 1
            print("notify failed %s: %r" % (email, exc), flush=True)
    return sent, failed, 0


def issue_code(email):
    """生成并发送验证码；返回 (ok, message, code_or_None)。"""
    now = time.time()
    sent = [t for t in CODE_SENT.get(email, []) if t > now - 3600]
    CODE_SENT[email] = sent
    if sent and now - sent[-1] < CODE_RESEND:
        return False, "请求过于频繁，请 %d 秒后再试" % int(CODE_RESEND - (now - sent[-1])), None
    if len(sent) >= CODE_MAX_PER_HOUR:
        return False, "本小时发送次数过多，请稍后再试", None

    code = "%06d" % secrets.randbelow(1000000)
    print("[login] %s 验证码 %s（10 分钟内有效）" % (email, code), flush=True)
    CODES[email] = {"hash": hashlib.sha256(code.encode()).hexdigest(), "exp": now + CODE_TTL, "tries": 0}
    sent.append(now)

    cfg = resolve_smtp()
    if cfg["host"] and cfg["user"]:
        try:
            smtp_send(
                email,
                "站点后台登录验证码",
                "你的登录验证码是：%s\n\n%d 分钟内有效，如非本人操作请忽略。" % (code, CODE_TTL // 60),
            )
        except Exception as exc:
            return False, "邮件发送失败：%s" % exc, None
    elif DEV_ECHO:
        pass  # 开发模式：把验证码放在响应里
    else:
        return False, "服务器未配置邮件服务，暂时无法发送验证码", None

    return True, "验证码已发送", (code if DEV_ECHO and not (SMTP_HOST and SMTP_USER) else None)


def check_code(email, code):
    item = CODES.get(email)
    if not item:
        return False, "请先获取验证码"
    if item["exp"] < time.time():
        CODES.pop(email, None)
        return False, "验证码已过期，请重新获取"
    if item["tries"] >= 5:
        CODES.pop(email, None)
        return False, "尝试次数过多，请重新获取"
    item["tries"] += 1
    if hashlib.sha256(str(code).encode()).hexdigest() != item["hash"]:
        print("[login] %s 验证码错误（第 %d 次）" % (email, item["tries"]), flush=True)
        return False, "验证码不正确"
    CODES.pop(email, None)
    return True, ""


def cookie_sid(handler):
    raw = handler.headers.get("Cookie", "") or ""
    for part in raw.split(";"):
        name, _, value = part.strip().partition("=")
        if name == "sid":
            return value.strip()
    return ""


class Handler(BaseHTTPRequestHandler):
    server_version = "status-api"
    protocol_version = "HTTP/1.1"

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _service_ok(self):
        return bool(TOKEN) and self.headers.get("Authorization", "") == "Bearer " + TOKEN

    def _user(self):
        return session_user(cookie_sid(self))

    def _authorized(self, level="read"):
        """level: read（已登录即可） / write（管理员或维护人员） / admin（仅管理员）。"""
        if self._service_ok():
            return True
        user = self._user()
        if not user:
            return False
        role = user.get("role") or "viewer"
        if level == "admin":
            return role == "admin"
        if level == "write":
            return role in ("admin", "maintainer")
        return True

    def _deny(self, level="read"):
        if self._user():
            return self._send(403, {"error": "权限不足"})
        return self._send(401, {"error": "unauthorized"})

    def _level_for(self, parts):
        if len(parts) >= 2 and parts[1] == "users":
            return "admin"
        return "write"

    def _send_cookie(self, code, payload, sid):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if sid:
            self.send_header("Set-Cookie",
                             "sid=%s; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=%d"
                             % (sid, SESSION_TTL))
        else:
            self.send_header("Set-Cookie", "sid=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _read_body(self):
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if size <= 0 or size > 2_000_000:
            return None
        try:
            body = json.loads(self.rfile.read(size))
            return body if isinstance(body, dict) else None
        except ValueError:
            return None

    def _client_ip(self):
        forwarded = self.headers.get("X-Forwarded-For") or ""
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "?"

    def _ip_allowed(self):
        ip = self._client_ip()
        now = time.time()
        stamps = [t for t in IP_CODES.get(ip, []) if t > now - 3600]
        if len(stamps) >= IP_LIMIT_PER_HOUR:
            IP_CODES[ip] = stamps
            return False
        stamps.append(now)
        IP_CODES[ip] = stamps
        return True

    def _parts(self):
        return [p for p in self.path.split("?", 1)[0].split("/") if p]

    def do_GET(self):
        parts = self._parts()
        if parts == ["api", "settings"]:
            settings = get_settings()
            return self._send(200, {k: settings.get(k) for k in PUBLIC_SETTING_KEYS})
        if parts == ["api", "settings", "full"]:
            if not self._authorized("admin"):
                return self._deny("admin")
            settings = json.loads(json.dumps(get_settings()))
            notify = settings.get("notify") or {}
            if notify.get("smtpPass"):
                notify["smtpPass"] = MASKED
            return self._send(200, settings)
        if parts == ["api", "auth", "me"]:
            user = self._user()
            if user:
                return self._send(200, user)
            return self._send(401, {"error": "unauthorized"})
        if parts == ["api", "health"]:
            return self._send(200, {"ok": True, "version": APP_VERSION})
        if len(parts) == 2 and parts[0] == "api" and parts[1] in COLLECTIONS:
            if parts[1] == "users" and not self._authorized("admin"):
                return self._deny("admin")
            with LOCK:
                data = load()
            return self._send(200, {parts[1]: data[parts[1]]})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        parts = self._parts()
        # 先读掉请求体：否则鉴权失败返回 401/403 时，body 会留在 socket 里污染下一个请求
        raw_body = self._read_body()

        if parts == ["api", "settings"]:
            if not self._authorized("admin"):
                return self._deny("admin")
            if raw_body is None:
                return self._send(400, {"error": "invalid json"})
            updated = save_settings(raw_body)
            public = {k: updated.get(k) for k in PUBLIC_SETTING_KEYS}
            full = dict(updated)
            return self._send(200, {"settings": full, "public": public})

        if parts == ["api", "settings", "test"]:
            if not self._authorized("admin"):
                return self._deny("admin")
            body = raw_body or {}
            target = str(body.get("email") or "").strip()
            if not target:
                return self._send(400, {"error": "请填写收件邮箱"})
            cfg = resolve_smtp()
            try:
                smtp_send(
                    target,
                    "【测试】站点通知配置",
                    "这是一封测试邮件。\n\n如果你的收件箱收到了它，说明 SMTP 配置可用。\n发送时间：%s"
                    % dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
                    cfg,
                )
            except Exception as exc:
                return self._send(400, {"error": "发送失败：%s" % exc})
            return self._send(200, {"ok": True, "message": "测试邮件已发送"})

        if parts == ["api", "notify"]:
            if not self._service_ok():
                return self._send(401, {"error": "unauthorized"})
            body = raw_body or {}
            incident = body.get("incident") or {}
            sent, failed, skipped = notify_incident(incident, body.get("kind") or "new")
            return self._send(200, {"sent": sent, "failed": failed, "skipped": skipped})

        if parts == ["api", "auth", "request-code"]:
            body = raw_body or {}
            email = str(body.get("email") or "").strip().lower()
            if not email or "@" not in email:
                return self._send(400, {"error": "邮箱格式不正确"})
            if not self._ip_allowed():
                return self._send(429, {"sent": False, "message": "请求过于频繁，请稍后再试"})
            if not allowed_user(email):
                return self._send(200, {"sent": True, "message": "如果该邮箱有权限，验证码已发送"})
            ok, msg, dev = issue_code(email)
            payload = {"sent": ok, "message": msg}
            if dev:
                payload["devCode"] = dev
            return self._send(200 if ok else 429, payload)

        if parts == ["api", "auth", "verify"]:
            body = raw_body or {}
            email = str(body.get("email") or "").strip().lower()
            code = str(body.get("code") or "").strip()
            if not allowed_user(email):
                return self._send(401, {"error": "验证码不正确或该邮箱无权限"})
            ok, msg = check_code(email, code)
            if not ok:
                return self._send(401, {"error": msg})
            role = "admin"
            with LOCK:
                data = load()
                user = find_user(data, email)
                if user:
                    role = user.get("role") or "viewer"
                    user["lastLoginAt"] = now_iso()
                    save(data)
            sid = create_session(email, role)
            return self._send_cookie(200, {"email": email, "role": role}, sid)

        if parts == ["api", "auth", "logout"]:
            drop_session(cookie_sid(self))
            return self._send_cookie(200, {"ok": True}, None)

        level = self._level_for(parts)
        if not self._authorized(level):
            return self._deny(level)
        body = raw_body
        if body is None:
            return self._send(400, {"error": "invalid json"})

        with LOCK:
            data = load()
            # 新建
            if len(parts) == 2 and parts[0] == "api" and parts[1] in COLLECTIONS:
                name = parts[1]
                item = BUILDERS[name](body)
                data[name].insert(0, item)
                save(data)
                if name == "incidents" and not item.get("silent"):
                    threading.Thread(target=notify_incident, args=(item, "new"), daemon=True).start()
                return self._send(201, {name[:-1] if name.endswith("s") else name: item})

            # 事件：追加更新
            if len(parts) == 4 and parts[:2] == ["api", "incidents"] and parts[3] == "updates":
                incident = next((i for i in data["incidents"] if i.get("id") == parts[2]), None)
                if not incident:
                    return self._send(404, {"error": "not found"})
                status = body.get("status") if body.get("status") in STATUSES else ""
                update = {
                    "at": now_iso(), "status": status,
                    "text": text(body.get("text")), "textEn": text(body.get("textEn")),
                    "author": text(body.get("author"), 40),
                }
                if not update["text"]:
                    return self._send(400, {"error": "text required"})
                incident["updates"].append(update)
                if status:
                    incident["status"] = status
                    incident["resolvedAt"] = update["at"] if status == "resolved" else None
                save(data)
                return self._send(201, {"incident": incident})

        self._send(404, {"error": "not found"})

    def do_PATCH(self):
        parts = self._parts()
        level = self._level_for(parts)
        if not self._authorized(level):
            return self._deny(level)
        if len(parts) != 3 or parts[0] != "api" or parts[1] not in COLLECTIONS:
            return self._send(404, {"error": "not found"})
        body = self._read_body()
        if body is None:
            return self._send(400, {"error": "invalid json"})
        name = parts[1]
        with LOCK:
            data = load()
            item = next((i for i in data[name] if i.get("id") == parts[2]), None)
            if not item:
                return self._send(404, {"error": "not found"})
            apply_update(name, item, body)
            save(data)
            return self._send(200, {name[:-1] if name.endswith("s") else name: item})

    def do_DELETE(self):
        parts = self._parts()
        level = self._level_for(parts)
        if not self._authorized(level):
            return self._deny(level)
        if len(parts) != 3 or parts[0] != "api" or parts[1] not in COLLECTIONS:
            return self._send(404, {"error": "not found"})
        name = parts[1]
        with LOCK:
            data = load()
            before = len(data[name])
            removed = [i for i in data[name] if i.get("id") == parts[2]]
            data[name] = [i for i in data[name] if i.get("id") != parts[2]]
            save(data)
            if name == "users" and removed:
                gone = (removed[0].get("email") or "").lower()
                sessions = load_sessions()
                keep = {k: v for k, v in sessions.items() if (v.get("email") or "").lower() != gone}
                if len(keep) != len(sessions):
                    save_sessions(keep)
            return self._send(200, {"deleted": before - len(data[name])})

    def log_message(self, fmt, *args):
        print("[%s] %s" % (now_iso(), fmt % args), flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8099"))
    os.makedirs(os.path.dirname(DATA) or ".", exist_ok=True)
    print("status-api :%d data=%s token=%s" % (port, DATA, "set" if TOKEN else "MISSING"), flush=True)
    try:
        ensure_users()
    except Exception as exc:
        print("seed users failed: %r" % (exc,), flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
