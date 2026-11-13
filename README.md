# Watchpost（哨塔）

> 一个自包含的状态页（源代码开放，非商业许可）：探针、事件工单、公告、维护窗口、邮件通知、后台管理，一条 docker compose up -d 跑起来。接手维护请先看 [交接文档](HANDOVER.md)。

## 文档导航

| 文档 | 什么时候看 |
|---|---|
| 本文件 | 第一次跑起来：快速开始、配置项、上线检查 |
| [HANDOVER](HANDOVER.md) | 接手维护：文件地图、部署与回滚、运维命令、踩坑记录 |
| [docs/ARCHITECTURE](docs/ARCHITECTURE.md) | 想改架构：每个选择的理由、付出的代价、什么时候该换 |
| [SECURITY](SECURITY.md) | 上报漏洞、部署侧安全基线 |
| [LICENSE](LICENSE) / [NOTICE](NOTICE) | 授权范围与第三方组件许可证 |

> 阅读顺序：README → HANDOVER → ARCHITECTURE。

```
浏览器 ──HTTPS──► Caddy ──┬─► 静态页（web/）
                          ├─► /api/incidents|announcements|maintenance|nodes|users|settings|auth ─► status-api
                          └─► /api/v1/*   ─► Gatus（探针与历史）
                                        ▲
              status-watcher（自动工单/通知/RSS）  status-collector（导出 status.json）
```

## 快速开始

```bash
cp .env.example .env
# 至少改这两项：
#   ADMIN_TOKEN=<随机 24 位以上>
#   ADMIN_EMAILS=you@example.com
docker compose pull      # 拉取预构建镜像 ghcr.io/balareshe/watchpost-core
docker compose up -d
```

打开 `https://<你的域名>/admin/`，用 `ADMIN_EMAILS` 里的邮箱接收验证码登录。

> 镜像由 GitHub Actions 在打 tag 时构建并推送到 GHCR（`linux/amd64` + `linux/arm64`）。
> 用 `WATCHPOST_VERSION=0.1.0` 固定版本，留空则跟随 `latest`。
> 想直接跑本地源码调试：`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`

> 首次启动会自动用 `ADMIN_EMAILS` 建管理员账号。
> 如果没有配 SMTP 且 `DEV_ECHO_CODE=0`，验证码会打印在 `docker compose logs status-api` 里（`[login] ... 验证码`）。

## 组成

| 服务 | 作用 | 端口 |
|---|---|---|
| `caddy` | 唯一对外入口：HTTPS、静态页、API 反代、安全响应头 | 80 / 443 |
| `status-api` | 事件 / 公告 / 维护窗口 / 节点 / 用户 / 设置 / 邮箱登录 | 内部 8099 |
| `status-watcher` | 失败重试→自动开单、慢响应记录、邮件通知、RSS、自定义节点探测 | 内部 |
| `status-collector` | 每 2 分钟把 Gatus 的 SQLite 导成 `web/data/status.json` | 内部 |
| `gatus` | 实际探测与历史存储（30 秒一次） | 内部 8080 |

数据都在命名卷里：`gatus-data`、`api-data`、`watcher-state`、`caddy-data`、`caddy-config`。

## 目录

```
├── docker-compose.yml     编排（5 个服务）
├── .env.example           配置模板
├── caddy/Caddyfile        域名、反代、安全头
├── config/gatus/          探针配置（节点名称、URL、间隔）
├── server/app.py          API 服务
├── server/watch.py        自动化工单 + 通知 + RSS
├── collector/collect.py   Gatus → status.json
├── web/                   状态页与后台构建产物
└── admin-app/             后台源码（Vue 3 + Vite）
```

## 常用操作

```bash
docker compose ps                      # 服务状态
docker compose logs -f status-watcher  # 看自动工单/通知日志
docker compose restart status-api      # 改完后端代码后重启
docker compose down                    # 停止（保留数据卷）
docker compose down -v                 # 停止并删除数据（危险）
```

**改后台界面**（`admin-app/`）：

```bash
cd admin-app && npm install && npm run build   # 产物输出到 web/admin/
```

**加/改探针节点**：编辑 `config/gatus/config.yaml`，然后 `docker compose restart gatus`。
也可以直接在后台「节点」页添加自定义节点（不经过 Gatus，由 watcher 探测）。

## 配置项（.env）

| 变量 | 说明 |
|---|---|
| `ADMIN_TOKEN` | 服务令牌，watcher 调 API 用；请用随机串 |
| `ADMIN_EMAILS` | 可登录后台的邮箱，逗号分隔 |
| `DOMAIN` / `PUBLIC_URL` | 对外域名与完整地址 |
| `SMTP_*` | 邮件服务器（也可在后台「通知」页配置） |
| `RETRY_TIMES` / `RETRY_GAP_SEC` | 失败重试次数与间隔，全失败才升红开单 |
| `FAIL_THRESHOLD` | 连续失败多少次才进入「重试 → 开单」流程，默认 1 |
| `SLOW_MS` / `SLOW_STREAK` | 慢响应阈值与连续次数 |
| `RECOVER_THRESHOLD` | 连续成功多少次判定恢复 |

## 上线检查

```bash
sh deploy/verify.sh 你的域名
```

会检查：页面可达、敏感路径 404、匿名接口 401、安全头齐全、5 个容器在跑、`.env` 权限 600、开发模式已关闭。

## 安全说明

- 后台登录用邮箱验证码，验证码 10 分钟有效、错 5 次作废、同邮箱 60 秒冷却、同 IP 每小时 10 次
- 会话 Cookie：`HttpOnly; Secure; SameSite=Lax`，7 天有效
- 安全响应头：HSTS、nosniff、X-Frame-Options、CSP(frame-ancestors)、Referrer-Policy
- `/data/*`、`/config/*`、`/.env`、`/.git/*` 一律 404
- 自定义节点的地址只对登录用户 / 服务令牌可见，匿名读 `GET /api/nodes` 不含 `url`
- **证书**：默认 Caddy 自签（`tls internal`），Cloudflare 需设 `Full`；若用 Cloudflare Origin 证书可设 `Full (strict)`
- 生产建议：关闭 SSH 密码登录、给 `/admin` 加 WAF 速率限制、定期轮换 `ADMIN_TOKEN`

## 数据备份与迁移

所有业务数据在命名卷里，导出/导入都在宿主机执行：

```bash
# 导出（当前机器）
docker run --rm -v watchpost_api-data:/d -v $PWD:/o alpine tar -C /d -czf /o/api-data.tgz .
docker run --rm -v watchpost_gatus-data:/d -v $PWD:/o alpine tar -C /d -czf /o/gatus-data.tgz .
docker run --rm -v watchpost_watcher-state:/d -v $PWD:/o alpine tar -C /d -czf /o/watcher-state.tgz .

# 导入（新机器，先 docker compose down）
docker compose down
docker volume create watchpost_api-data
docker run --rm -v watchpost_api-data:/d -v $PWD:/b alpine tar -C /d -xzf /b/api-data.tgz
docker run --rm -v watchpost_gatus-data:/d -v $PWD:/b alpine tar -C /d -xzf /b/gatus-data.tgz
docker compose pull      # 拉取预构建镜像 ghcr.io/balareshe/watchpost-core
docker compose up -d
```

日常备份：容器外跑一条 cron 即可（备份的是业务 JSON，体积几 KB）：

```bash
0 3 * * * root docker exec status-api cat /data/status-data.json > /root/status-$(date +\%Y\%m\%d).json
```

## 许可与版权

**Watchpost 非商业源代码许可协议 1.0**（`LICENSE`），要点：

| 允许 | 要求 | 禁止 |
|---|---|---|
| 个人学习、研究 | 保留版权声明与协议全文 | **商业使用**（销售、收费托管、集成进商业产品等） |
| 内部非营利自用部署 | 分发时署名 **Watchpost** 并附原仓库地址 | 删除或隐藏版权信息 |
| 教学、非营利组织内部使用 | 说明修改版本是否经改动 | 暗示修改版由原作者官方发布 |
| 在非商业范围内修改与分发 | 另行取得书面授权后方可商用 | 使用本项目商标 |

> 这不是 OSI 认可的开源许可，属于「源代码开放（source-available）」。需要商业授权请通过 issue 联系。
> 第三方组件（Gatus、Caddy、Vue 等）遵循其各自许可证，见 `NOTICE`。

版权声明：Copyright (C) 2026 balareshe（摆烂人生），保留所有权利。