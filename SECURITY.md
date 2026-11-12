# 安全策略

## 报告漏洞

请**不要**在公开 issue 里贴出可直接利用的细节。通过以下任一方式私下联系维护者：

- GitHub Security Advisories（仓库 Security 标签页 → Report a vulnerability）
- 邮件：见仓库维护者公开邮箱

我们会在 72 小时内确认，并尽快给出修复版本。

## 部署侧安全基线

本项目默认已包含：

- 后台登录走邮箱一次性验证码（10 分钟有效、错 5 次作废、同邮箱 60 秒冷却）
- 会话 Cookie：`HttpOnly; Secure; SameSite=Lax`
- 写接口全部需要登录或服务令牌，匿名请求返回 401
- `/data/*`、`/config/*`、`/.env`、`/.git/*` 一律 404
- 安全响应头：HSTS、`X-Content-Type-Options`、`X-Frame-Options`、`CSP frame-ancestors`、`Referrer-Policy`
- 邮件密码在设置接口中打码返回

部署者仍需自行确认：

1. **必须修改** `.env` 中的 `ADMIN_TOKEN`（至少 24 位随机串）
2. 生产环境关闭 `DEV_ECHO_CODE`（默认已是 0），确保验证码只通过邮件送达
3. 若使用自签证书，反向代理/CDN 需允许不校验证书（Cloudflare `Full`），推荐改用可信证书
4. 关闭 SSH 密码登录，仅保留密钥
5. 定期轮换 `ADMIN_TOKEN` 与邮件账号授权码
6. 不要把 `.env`、`web/data/`、`docker volume` 导出的数据提交进仓库
