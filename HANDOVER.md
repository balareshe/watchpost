# Watchpost 交接文档

面向接手维护的人：项目是什么、文件在哪、怎么部署更新、出问题怎么查、以及我们踩过的坑。

> 私有部署信息（域名、服务器地址、账号、凭据位置）**不要写进这个文件**。
> 建一个 `HANDOVER.local.md`（已在 `.gitignore` 中）记录，或写进自己的密码管理器。

---

## 1. 项目是什么

一个自包含、可自托管的状态页：探测目标服务 → 展示状态 → 自动开单 → 邮件通知 → 后台管理。

```
浏览器 ──HTTPS──► Caddy ──┬─► 静态页（web/）
                          ├─► /api/{incidents,announcements,maintenance,nodes,users,settings,auth}
                          │        └─► status-api（Python 标准库 HTTP 服务）
                          └─► /api/v1/* ─► Gatus（探针与历史，SQLite）
                                              ▲
                     status-watcher（自动工单/通知/RSS/自定义节点探测）
                     status-collector（每 2 分钟导出 status.json）
```

设计取舍：

- **不依赖数据库服务**：业务数据是 JSON 文件，探针历史交给 Gatus 的 SQLite；
- **后端纯标准库**：不装任何 pip 包，镜像小、升级不容易坏；
- **前后端分离**：前台是原生 JS，后台是 Vue 3 + Vite 构建后的静态产物；
- **只做只读监控**：不提供重启服务、改数据、回滚部署等自动修复能力。

---

## 2. 仓库文件地图

| 路径 | 作用 | 改这里会影响 |
|---|---|---|
| `docker-compose.yml` | 生产编排（镜像模式，5 个服务） | 部署形态 |
| `docker-compose.dev.yml` | 本地调试覆盖（挂载源码 + 本地构建） | 只影响开发 |
| `Dockerfile` | 核心镜像（api / watcher / collector 共用） | 三个容器 |
| `.env.example` | 配置模板 | 新部署 |
| `server/app.py` | 业务 API：事件 / 公告 / 维护 / 节点 / 用户 / 设置 / 登录 | 后台全功能 |
| `server/watch.py` | 后台任务：失败重试→开单、慢响应记录、邮件通知、RSS、自定义节点探测 | 自动化行为 |
| `collector/collect.py` | 把 Gatus 的 SQLite 导成 `web/data/status.json` | 状态页数据 |
| `config/gatus/config.yaml` | 探针定义（名称、URL、间隔、条件） | 监控目标 |
| `caddy/Caddyfile` | 域名、反代、安全响应头、敏感路径 404 | 入口与安全 |
| `web/` | 状态页静态资源（`index.html`、`app.js`、`style.css`、详情页） | 前台展示 |
| `web/admin/` | 后台构建产物（**已提交，部署时不需要 Node**） | 后台界面 |
| `admin-app/` | 后台源码（Vue 3 + Vite） | 改完要 `npm run build` |
| `deploy/update.sh` | 一键更新：备份 → 拉代码 → 重建 → 验收 | 升级流程 |
| `deploy/verify.sh` | 18 项验收检查 | 上线自检 |
| `.github/workflows/ci.yml` | CI：Python 语法+冒烟、前端构建、compose 校验 | PR 质量 |
| `.github/workflows/release.yml` | 打 tag 自动构建镜像推 GHCR（amd64+arm64） | 镜像发布 |
| `VERSION` | 版本号，`/api/health` 与后台侧栏显示 | 版本标识 |
| `LICENSE` / `NOTICE` | 非商业许可 + 第三方组件许可证 | 授权 |

**数据文件不在仓库里**：`web/data/status.json`、`web/data/nodes.json` 由采集器/watcher 生成，已 gitignore。

---

## 3. 运行形态

| 服务 | 镜像 | 说明 |
|---|---|---|
| `caddy` | `caddy:2-alpine` | 唯一公网入口，80/443 |
| `status-api` | `ghcr.io/balareshe/watchpost-core` | 内部 8099 |
| `status-watcher` | 同上 | 无端口，只跑后台任务 |
| `status-collector` | 同上 | 无端口，`while true` 每 2 分钟导出 |
| `gatus` | `twinproduction/gatus` | 内部 8080 |

命名卷（`docker compose down` 不会删，`down -v` 会）：

```
watchpost_gatus-data     探针历史（SQLite，含 -wal）
watchpost_api-data       业务 JSON + 会话
watchpost_watcher-state  自定义节点采样
watchpost_caddy-data     证书
watchpost_caddy-config   Caddy 配置缓存
```

---

## 4. 部署

### 镜像方式（推荐）

```bash
cp .env.example .env      # 至少改 ADMIN_TOKEN、ADMIN_EMAILS
docker compose pull
docker compose up -d
sh deploy/verify.sh <域名>
```

固定版本：`.env` 里 `WATCHPOST_VERSION=0.1.0`；留空跟随 `latest`。

### 源码方式

```bash
tar -xzf watchpost-v0.1.0.tar.gz -C /opt/watchpost
cd /opt/watchpost && cp .env.example .env && docker compose up -d
```

### 本地开发

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
# 改 server/*.py 后只需 docker compose restart status-api status-watcher
```

### HTTPS / 证书

- 默认 `tls internal`（Caddy 自签，浏览器报警，CDN 需设为 **Full** 而非 Full strict）
- 想用正规证书：换成 Cloudflare Origin 证书或 Let's Encrypt（DNS-01），把 CDN 改为 Full (strict)

---

## 5. 配置项（`.env`）

| 变量 | 必填 | 说明 |
|---|---|---|
| `ADMIN_TOKEN` | ✅ | 服务令牌，watcher 调 API 用；随机 24 位以上 |
| `ADMIN_EMAILS` | ✅ | 可登录后台的邮箱，逗号分隔；首次启动自动建账号 |
| `DOMAIN` / `PUBLIC_URL` | ✅ | 域名与完整地址（Caddy 模板变量 / 通知链接） |
| `WATCHPOST_VERSION` | — | 镜像版本，空则 `latest` |
| `SMTP_HOST/PORT/USER/PASS/FROM/SECURE` | — | 邮件；也可在后台「通知」页配置（后台优先） |
| `DEV_ECHO_CODE` | — | 调试用：把验证码回显到登录框，**生产必须为 0** |
| `RETRY_TIMES` / `RETRY_GAP_SEC` | — | 失败重试次数与间隔，全失败才升红开单 |
| `SLOW_MS` / `SLOW_STREAK` | — | 慢响应阈值（ms）与连续次数 |
| `RECOVER_THRESHOLD` | — | 连续成功多少次判定恢复 |
| `COLLECT_INTERVAL` / `INTERVAL_SEC` | — | 采集与 watcher 轮询间隔（秒） |

---

## 6. 更新与回滚

```bash
sh deploy/update.sh            # 备份数据 → git pull → compose up → 验收
sh deploy/update.sh v0.1.0     # 切到指定 tag
```

**镜像模式下的关键点**：镜像由打 tag 触发构建，光 `git pull` 不会更新容器里的代码。

```bash
git tag -a v0.1.1 -m "..." && git push origin v0.1.1   # 触发 Actions 构建
# 构建完成后：
docker compose pull && docker compose up -d
```

只改 `web/`、`config/`、`caddy/` 不需要重新构建镜像。

**回滚数据**：

```bash
docker run --rm -v watchpost_api-data:/d -v /root/dsh-backups:/b alpine \
  sh -c 'rm -rf /d/* && tar -C /d -xzf /b/api-data-<时间戳>.tgz'
```

---

## 7. 数据与备份

- 业务数据：`watchpost_api-data` → `/data/status-data.json`（事件/公告/维护/节点/用户/设置）
- 探针历史：`watchpost_gatus-data` → `/data/data.db`（**真正数据在 `data.db-wal`，主库只有几 KB**）
- 备份命令见 `deploy/update.sh`（每次更新前自动备份到 `/root/dsh-backups`）
- 迁移到新机器：导出各卷 → 新机器建同名卷 → 导入 → `docker compose up -d`

---

## 8. 运维命令速查

```bash
docker compose ps                                  # 状态
docker compose logs -f status-watcher              # 自动工单/通知
docker compose logs -f status-collector            # 数据导出
docker compose restart status-api                  # 改后端后重启（源码模式）
docker compose exec status-api sh                  # 进容器
curl -s https://<域名>/api/health                  # 版本与存活
sh deploy/verify.sh <域名>                         # 18 项验收
```

排障顺序：`/api/health` → 容器状态 → 对应服务日志 → `web/data/status.json` 是否有新数据 → Caddy 反代。

---

## 9. 踩坑记录（都是实际发生过的）

### Caddy

1. **`redir` 不能写在 `handle` 里**：`handle /admin { redir /admin/ 302 }` 会被当成「匹配器 + 目标」解析，结果是 **200 + 空响应体**（页面白屏）。必须写在站点层：`redir /admin /admin/ 302`。
2. **API 路由是白名单**：新增一个接口（如 `/api/users`）必须在 Caddyfile 里显式加 `handle`，否则会被 `/api/*` 兜给 Gatus 返回 404。
3. **`try_files {path} /index.html` 会把任意路径兜成 200 首页**：敏感路径看起来"存在"其实返回的是 HTML。必须显式 `respond 404`，同时**单独放行**前台真正要读的 `/data/status.json`、`/data/nodes.json`。
4. **`header` 指令用块写法**才能一次加多个安全头；`-Server` 可去掉 `Server: Caddy`。

### 缓存

5. **Cloudflare 会缓存 `.js` 和 `.json`**：只发 `Cache-Control: no-store` 不够，还要 `CDN-Cache-Control: no-store`；前端资源改完用 `?v=N` 版本号兜底。

### 前端

6. **`[hidden]` 会被 `display` 覆盖**：元素明明 `hidden` 却还显示，需要全局 `[hidden] { display: none !important; }`。
7. **构建产物要提交**：`web/admin/` 是 Vite 产物，部署机不装 Node，改后台必须本地/CI 构建后提交。

### Gatus / 采集

8. **`results` 数组是旧→新正序**：最新一条是 `results[len-1]`，取「最近 5 条」要 `slice(-5).reverse()`。
9. **Gatus 数据主要在 WAL**：`cp data.db` 只有 4 KB，必须连 `data.db-wal`、`data.db-shm` 一起拷。
10. **Gatus 时区是 UTC**：时间戳形如 `2026-11-12 11:31:07.189 +0000 UTC`，展示要转本地时区。
11. **采集器曾每 2 分钟全表读 `endpoint_results`**：已改为 `WHERE endpoint_id=? AND timestamp>=?`，并补 `(endpoint_id, timestamp)` 复合索引；`EXPLAIN QUERY PLAN` 可验证走索引。

### Docker / 编排

12. **容器内访问自己的公网域名会被 CDN 拦**（Cloudflare 403）：容器间调用一律用服务名（`http://status-api:8099`）。
13. **改 compose 项目名会改卷名前缀**：`status-page_*` → `watchpost_*`，旧容器还在用旧项目名；`docker compose down` 必须显式 `-p <旧项目名>` 才停得掉，否则报容器名冲突。
14. **只读挂载里不能再挂文件**：往 `./server:/app:ro` 里挂 `/app/VERSION` 会失败（read-only file system），版本文件要跟着源码目录走。
15. **打包要排除 `.git`**：不排除时包从 64 个文件涨到 345 个、体积翻 4 倍。

### 后端 / 鉴权

16. **鉴权前必须先读完请求体**：否则 401/403 时 body 留在 keep-alive 连接里，被当作下一个请求行解析，出现 `{"email":...}GET /api/users` → 501 的诡异错误。
17. **枚举防护**：验证码校验失败统一返回「验证码不正确或该邮箱无权限」，不区分邮箱是否存在。
18. **设置接口要把 SMTP 密码打码**，保存时忽略打码值，否则会把 `********` 写进配置。

### 前端脚本

19. **Windows 上的 shell 脚本会带 CRLF**：用 PowerShell 写出的 `.sh` 在 Linux 上执行报 `word unexpected`，需统一转 LF。
20. **PowerShell 双引号里 `\n` 不是换行**：往文件写 Markdown 时会写进字面量 `\n`。改文件内容优先用 Python/Node 脚本。

---

## 10. 已知限制

- 监控端自身是单点：监控机挂了不会自动告警（规划：外部探活 + 面板心跳）
- 不做主机级指标（磁盘/内存/进程），只做可达性
- 慢响应只做「连续 N 次」判定，不区分上游/应用原因
- 前台日历按自然周固定展示最近 4 周，不随日期滚动
- 单机部署，无集群与多副本

---

## 11. 许可

**Watchpost 非商业源代码许可协议 1.0**（见 `LICENSE`）：允许个人/非营利使用与修改，**禁止商业使用**，分发须保留版权声明并署名 Watchpost。

Copyright (C) 2026 balareshe（摆烂人生） · https://github.com/balareshe/watchpost
第三方组件许可证见 `NOTICE`。
