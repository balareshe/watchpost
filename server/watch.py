#!/usr/bin/env python3
# Copyright (C) 2026 balareshe（摆烂人生） <https://github.com/balareshe/watchpost>. All rights reserved.
# Licensed under the Watchpost Non-Commercial Source License 1.0 (see LICENSE).
# 本项目禁止商业使用；分发须保留本声明与授权协议，并署名 Watchpost。
"""自动开工单 + 维护窗口抑制 + RSS 生成。

每 60 秒：
  1. 读 Gatus 探针结果，某组件连续失败 ≥ FAIL_THRESHOLD 次且没有未恢复工单 → 自动创建「排查中」事件
  2. 自动创建的事件对应组件连续成功 ≥ RECOVER_THRESHOLD 次 → 自动追加「已恢复」更新
  3. 维护窗口内不自动开单
  4. 生成 /web/feed.xml（RSS 2.0：事件 + 公告）
"""
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

GATUS = os.environ.get("GATUS_URL", "http://gatus:8080").rstrip("/")
API = os.environ.get("API_URL", "http://status-api:8099").rstrip("/")
TOKEN = (os.environ.get("ADMIN_TOKEN") or "").strip()
WEB = os.environ.get("WEB_DIR", "/web")
STATE_DIR = os.environ.get("STATE_DIR", "/state")
NODES_STATE = os.path.join(STATE_DIR, "nodes.json")
SITE = os.environ.get("SITE_URL", "https://status.example.com")
FAIL_THRESHOLD = int(os.environ.get("FAIL_THRESHOLD", "3"))
RECOVER_THRESHOLD = int(os.environ.get("RECOVER_THRESHOLD", "3"))
INTERVAL = int(os.environ.get("INTERVAL_SEC", "60"))
RETRY_TIMES = int(os.environ.get("RETRY_TIMES", "3"))
RETRY_GAP = float(os.environ.get("RETRY_GAP_SEC", "2"))
CONFIG_PATH = os.environ.get("GATUS_CONFIG", "/config/config.yaml")
SLOW_MS = int(os.environ.get("SLOW_MS", "800"))
SLOW_STREAK = int(os.environ.get("SLOW_STREAK", "3"))
TZ = dt.timezone(dt.timedelta(hours=8))

DEFAULT_TEMPLATES = {
    "downTitle": "{name} 无法访问（{time} 起）",
    "downSummary": "自动监控发现「{name}」无法正常访问：连续 {fails} 次探测失败，"
                   "立即重试 {retries} 次仍未恢复，异常始于 {startedAt}。已自动创建工单，等待值班确认。",
    "downUpdate": "最近一次探测：{status}，{cost}。自动监控已创建工单。",
    "slowTitle": "{name} 响应变慢（{time} 起）",
    "slowSummary": "自动监控发现「{name}」响应变慢：连续 {streak} 次探测耗时超过 {threshold} ms，"
                   "最近一次 {lastMs} ms。可用性未受影响，已记录以便观察。",
    "slowUpdate": "最近一次探测 {lastMs} ms，超过阈值 {threshold} ms。",
}


def log(msg):
    print("[%s] %s" % (dt.datetime.now(TZ).strftime("%H:%M:%S"), msg), flush=True)


def http_json(url, method="GET", body=None, auth=False):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if auth and TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


def trailing_run(results, want_success):
    """从最新端往回数，连续满足条件（成功/失败）的次数。results 为旧→新。"""
    count = 0
    for item in reversed(results or []):
        ok = bool(item.get("success"))
        if ok == want_success:
            count += 1
        else:
            break
    return count


def active_window(maintenance):
    now = dt.datetime.now(TZ)
    for win in maintenance or []:
        try:
            start = dt.datetime.fromisoformat(win.get("startAt", ""))
            end = dt.datetime.fromisoformat(win.get("endAt", ""))
        except ValueError:
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=TZ)
        if end.tzinfo is None:
            end = end.replace(tzinfo=TZ)
        if start <= now <= end:
            return win
    return None


def write_feed(incidents, announcements):
    items = []

    for inc in (incidents or [])[:30]:
        title = inc.get("title", "服务异常")
        link = "%s/incident.html?id=%s" % (SITE, urllib.parse.quote(inc.get("id", "")))
        parts = []
        if inc.get("summary"):
            parts.append(inc["summary"])
        for upd in reversed(inc.get("updates") or []):
            parts.append("%s %s" % (upd.get("at", "")[11:16], upd.get("text", "")))
        desc = "\n".join(p for p in parts if p)
        items.append({
            "title": title,
            "link": link,
            "guid": inc.get("id", ""),
            "date": inc.get("startedAt") or inc.get("createdAt"),
            "desc": desc,
        })

    for ann in (announcements or [])[:20]:
        items.append({
            "title": "公告：" + ann.get("title", ""),
            "link": SITE + "/#announcements",
            "guid": ann.get("id", ""),
            "date": ann.get("createdAt"),
            "desc": ann.get("body", ""),
        })

    items.sort(key=lambda i: i["date"] or "", reverse=True)

    def rfc822(value):
        try:
            moment = dt.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            moment = dt.datetime.now(TZ)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=TZ)
        return moment.astimezone(dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    entries = "".join(
        "<item><title>%s</title><link>%s</link><guid isPermaLink=\"false\">%s</guid>"
        "<pubDate>%s</pubDate><description>%s</description></item>"
        % (escape(i["title"]), escape(i["link"]), escape(i["guid"]),
           rfc822(i["date"]), escape(i["desc"]))
        for i in items
    )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        "<title>站点状态 · 事件与公告</title>"
        "<link>%s/</link><description>西木会馆 · 应用 服务状态与公告</description>"
        "<language>zh-CN</language>%s</channel></rss>\n" % (SITE, entries)
    )
    target = os.path.join(WEB, "feed.xml")
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(xml)
    os.replace(tmp, target)


def load_probe_urls():
    """从 Gatus 配置里读 name -> url（API 里隐藏了 url）。"""
    mapping = {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            current = None
            for raw in fh:
                line = raw.strip()
                if line.startswith("- name:"):
                    current = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("url:") and current:
                    mapping[current] = line.split(":", 1)[1].strip().strip('"').strip("'")
                    current = None
    except OSError:
        pass
    return mapping


def confirm_failure(url):
    """连不上时立刻重试 N 次；任一次成功即视为波动。返回 (全部失败, 明细)。"""
    if not url:
        return True, []
    detail = []
    for i in range(RETRY_TIMES):
        ok, code, ms = probe(url)
        detail.append({"ok": ok, "code": code, "ms": ms})
        if ok:
            return False, detail
        if i < RETRY_TIMES - 1:
            time.sleep(RETRY_GAP)
    return True, detail


def load_state():
    try:
        with open(NODES_STATE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(data):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = NODES_STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, NODES_STATE)


def probe(url):
    """返回 (ok, status, ms)。自定义节点的探活，不依赖 Gatus。"""
    started = time.time()
    code = 0
    ok = False
    try:
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "status-watcher/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = getattr(resp, "status", 0) or 0
        ok = 200 <= code < 400
    except urllib.error.HTTPError as exc:
        code = exc.code
        ok = 200 <= code < 400
    except Exception:
        ok = False
    return ok, code, int((time.time() - started) * 1000)


def sync_nodes():
    """探测自定义节点，维护 24h 采样，写出 /web/data/nodes.json。"""
    try:
        nodes = http_json(API + "/api/nodes").get("nodes", [])
    except Exception as exc:
        log("读取节点失败: %r" % (exc,))
        return

    state = load_state()
    now = time.time()

    for node in nodes:
        if node.get("builtin") or not node.get("enabled", True) or not node.get("url"):
            continue
        ok, code, ms = probe(node["url"])
        state.setdefault(node["id"], []).append([now, 1 if ok else 0, ms, code])

    for key in list(state):
        state[key] = [s for s in state[key] if s[0] > now - 86400]

    save_state(state)

    step = 86400 / 96
    out = {"generatedAt": dt.datetime.now(TZ).isoformat(timespec="seconds"), "nodes": []}
    for node in nodes:
        if node.get("builtin"):
            continue
        samples = state.get(node["id"], [])
        buckets = [None] * 96
        for ts, ok, ms, code in samples:
            idx = int((ts - (now - 86400)) // step)
            if idx < 0 or idx > 95:
                continue
            cell = buckets[idx] or {"ok": 0, "total": 0}
            cell["total"] += 1
            cell["ok"] += ok
            buckets[idx] = cell
        total = len(samples)
        ok_count = sum(1 for sm in samples if sm[1])
        latest = samples[-1] if samples else None
        out["nodes"].append({
            "id": node["id"],
            "name": node.get("name"),
            "order": node.get("order", 0),
            "ok": bool(latest and latest[1]),
            "status": latest[3] if latest else None,
            "ms": latest[2] if latest else None,
            "uptime": (ok_count / total) if total else None,
            "bars": buckets,
            # 最近 50 次逐次探测，供前台「详情」使用
            "recent": [[int(ts), ok, ms, code] for ts, ok, ms, code in samples[-50:]],
        })

    target = os.path.join(WEB, "data", "nodes.json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, target)


def slow_streak_from_results(results, threshold_ms):
    """从 Gatus results（旧→新）末尾数连续「成功但慢」的次数。"""
    streak = 0
    for item in reversed(results or []):
        if not item.get("success"):
            break
        duration = item.get("duration") or 0
        if duration / 1e6 < threshold_ms:
            break
        streak += 1
    return streak


def is_slow_incident(inc):
    return bool(inc.get("silent")) and "响应变慢" in (inc.get("title") or "")



def load_templates():
    """模板以「系统设置」为准，读取失败回落到内置默认值。"""
    try:
        data = http_json(API + "/api/settings/full", auth=True)
        merged = dict(DEFAULT_TEMPLATES)
        merged.update((data.get("templates") or {}))
        return merged
    except Exception:
        return dict(DEFAULT_TEMPLATES)


def render_tpl(tpl, ctx):
    out = tpl or ""
    for key, value in ctx.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def fmt_hm(value):
    if not value:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(TZ).strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


def last_probe_info(results):
    """最近一次探测的耗时 / 状态码 / 错误。"""
    if not results:
        return None
    item = results[-1]
    return {
        "ms": int((item.get("duration") or 0) / 1e6),
        "status": item.get("status"),
        "success": bool(item.get("success")),
        "errors": item.get("errors") or [],
        "timestamp": item.get("timestamp"),
    }


def failure_started_at(results):
    """连续失败段的起始时间（ISO 字符串）。"""
    start = None
    for item in reversed(results or []):
        if item.get("success"):
            break
        start = item.get("timestamp")
    return start


def fmt_when(value):
    """把 Gatus 时间戳格式化成 2026-11-12 22:31。"""
    if not value:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(TZ).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return ""


def tick():

    statuses = http_json(GATUS + "/api/v1/endpoints/statuses")
    incidents = http_json(API + "/api/incidents").get("incidents", [])
    maintenance = http_json(API + "/api/maintenance").get("maintenance", [])
    announcements = http_json(API + "/api/announcements").get("announcements", [])

    urls = load_probe_urls()
    window = active_window(maintenance)
    changed = False

    def active_for(name):
        for inc in incidents:
            if inc.get("status") == "resolved":
                continue
            if name in (inc.get("affected") or []):
                return inc
        return None

    for ep in statuses:
        name = ep.get("name")
        results = ep.get("results") or []
        fails = trailing_run(results, False)
        oks = trailing_run(results, True)
        open_incident = active_for(name)

        # 黄色波动先自动重试，3 次都失败才升级为红色并开单
        if fails >= 1 and not open_incident and not window:
            confirmed, detail = confirm_failure(urls.get(name))
            if not confirmed:
                log("重试成功，忽略本次波动: %s（连续失败 %d 次）" % (name, fails))
                continue
            log("重试 %d 次仍失败，升级为红色并开单: %s" % (RETRY_TIMES, name))

        # 自动开单
        if fails >= 1 and not open_incident and not window:
            probe = last_probe_info(results)
            started_at = fmt_when(failure_started_at(results))
            code = probe["status"] if probe else None
            if not code:
                status_text = "连接失败"
            elif code == 200:
                status_text = "HTTP 200"
            else:
                status_text = "HTTP %s" % code
            cost_text = ("耗时 %d ms" % probe["ms"]) if (probe and probe["ms"] > 0) else "无响应"
            tpl = load_templates()
            ctx_down = {
                "name": name,
                "time": fmt_hm(started_at) or dt.datetime.now(TZ).strftime("%H:%M"),
                "startedAt": started_at or dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
                "fails": fails,
                "retries": RETRY_TIMES,
                "status": status_text,
                "cost": cost_text,
                "components": name,
            }
            try:
                created = http_json(API + "/api/incidents", "POST", {
                    "title": render_tpl(tpl["downTitle"], ctx_down),
                    "titleEn": "%s Unavailable" % name,
                    "severity": "critical",
                    "status": "investigating",
                    "affected": [name],
                    "owner": "自动监控",
                    "auto": True,
                    "summary": render_tpl(tpl["downSummary"], ctx_down),
                    "summaryEn": "%s has been unreachable%s (%d failed checks, %d retries)."
                                 % (name, (" since " + started_at) if started_at else "", fails, RETRY_TIMES),
                    "firstUpdate": render_tpl(tpl["downUpdate"], ctx_down),
                }, auth=True)
                log("自动开单: %s（连续失败 %d 次）" % (name, fails))
                changed = True
                # 邮件通知由 API 在创建事件时统一发送，这里不重复触发
            except (urllib.error.URLError, urllib.error.HTTPError) as exc:
                log("开单失败 %s: %s" % (name, exc))

        # 自动恢复
        if open_incident and open_incident.get("auto") and not is_slow_incident(open_incident) and oks >= RECOVER_THRESHOLD:
            affected = open_incident.get("affected") or []
            recovered_all = True
            for other in affected:
                other_ep = next((e for e in statuses if e.get("name") == other), None)
                if other_ep and trailing_run(other_ep.get("results") or [], True) < RECOVER_THRESHOLD:
                    recovered_all = False
                    break
            if recovered_all:
                try:
                    http_json(API + "/api/incidents/%s/updates" % open_incident["id"], "POST", {
                        "status": "resolved",
                        "text": "监控确认服务已连续 %d 次探测成功，自动标记恢复。" % oks,
                        "textEn": "Service recovered after %d consecutive successful checks." % oks,
                        "author": "自动监控",
                    }, auth=True)
                    log("自动恢复: %s（%s）" % ("、".join(affected), open_incident["id"]))
                    changed = True

                except (urllib.error.URLError, urllib.error.HTTPError) as exc:
                    log("恢复失败: %s" % exc)

    if changed:
        incidents = http_json(API + "/api/incidents").get("incidents", [])

    try:
        write_feed(incidents, announcements)
    except OSError as exc:
        log("RSS 写入失败: %s" % exc)

    try:
        sync_nodes()
    except Exception as exc:
        log("自定义节点同步失败: %r" % (exc,))

    # ---- 慢响应：连续 N 次超过阈值 → 记录一条黄色事件（不发邮件、不升级红色）----
    try:
        nodes_cfg = http_json(API + "/api/nodes").get("nodes", [])
    except Exception:
        nodes_cfg = []

    thresholds = {}
    for n in nodes_cfg:
        if isinstance(n.get("slowMs"), (int, float)) and n["slowMs"] > 0:
            thresholds[n.get("name")] = n["slowMs"]

    def threshold_for(name):
        return thresholds.get(name, SLOW_MS)

    incidents = http_json(API + "/api/incidents").get("incidents", [])
    local_state = load_state()

    def open_incident_for(name):
        for inc in incidents:
            if inc.get("status") == "resolved":
                continue
            if name in (inc.get("affected") or []):
                return inc
        return None

    slow_candidates = []
    for ep in statuses:
        results_ep = ep.get("results") or []
        last_ms = int(((results_ep[-1].get("duration") or 0) / 1e6)) if results_ep else 0
        slow_candidates.append((ep.get("name"),
                                slow_streak_from_results(results_ep, threshold_for(ep.get("name"))),
                                last_ms))
    for node in nodes_cfg:
        if node.get("builtin"):
            continue
        samples = local_state.get(node.get("id"), [])
        streak = 0
        for ts, ok, ms, code in reversed(samples):
            if not ok or (ms or 0) < threshold_for(node.get("name")):
                break
            streak += 1
        last_ms = samples[-1][2] if samples else 0
        slow_candidates.append((node.get("name"), streak, last_ms))

    for name, streak, last_ms in slow_candidates:
        open_inc = open_incident_for(name)
        threshold = threshold_for(name)
        tpl = load_templates()
        ctx_slow = {
            "name": name,
            "time": dt.datetime.now(TZ).strftime("%H:%M"),
            "startedAt": dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
            "streak": streak,
            "threshold": threshold,
            "lastMs": last_ms,
            "components": name,
        }
        if streak >= SLOW_STREAK and not open_inc and not window:
            try:
                http_json(API + "/api/incidents", "POST", {
                    "title": render_tpl(tpl["slowTitle"], ctx_slow),
                    "titleEn": "%s Slow Response" % name,
                    "severity": "minor",
                    "status": "investigating",
                    "affected": [name],
                    "owner": "自动监控",
                    "auto": True,
                    "silent": True,
                    "summary": render_tpl(tpl["slowSummary"], ctx_slow),
                    "summaryEn": "%s latency exceeded %d ms for %d consecutive checks (latest %d ms)."
                                 % (name, threshold, streak, last_ms),
                    "firstUpdate": render_tpl(tpl["slowUpdate"], ctx_slow),
                }, auth=True)
                log("慢响应记录: %s（连续 %d 次 > %d ms）" % (name, streak, threshold))
            except Exception as exc:
                log("慢响应记录失败 %s: %r" % (name, exc))
        elif open_inc and is_slow_incident(open_inc) and streak == 0:
            try:
                http_json(API + "/api/incidents/%s/updates" % open_inc["id"], "POST", {
                    "status": "resolved",
                    "text": "延迟已恢复正常，自动关闭本条记录。",
                    "textEn": "Latency returned to normal.",
                    "author": "自动监控",
                }, auth=True)
                log("慢响应恢复: %s" % name)
            except Exception as exc:
                log("慢响应恢复失败 %s: %r" % (name, exc))

    if window:
        log("维护窗口进行中：%s（不做自动开单）" % window.get("title"))


def main():
    log("watcher 启动：失败阈值=%d 恢复阈值=%d 间隔=%ds" % (FAIL_THRESHOLD, RECOVER_THRESHOLD, INTERVAL))
    while True:
        try:
            tick()
        except Exception as exc:  # 单轮失败不影响下一轮
            log("本轮异常: %r" % (exc,))
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
