#!/bin/sh
# 上线验收：在新机器上执行 sh verify.sh status.example.com
DOMAIN="${1:-status.example.com}"
FAIL=0

check() {
  label="$1"; want="$2"; got="$3"
  if [ "$got" = "$want" ]; then
    printf '  [OK]   %-34s %s\n' "$label" "$got"
  else
    printf '  [FAIL] %-34s 期望 %s，实际 %s\n' "$label" "$want" "$got"
    FAIL=$((FAIL+1))
  fi
}

code() { curl -sk -o /dev/null -w '%{http_code}' --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN$1"; }

echo "== 1. 页面可访问 =="
check "首页" 200 "$(code /)"
check "后台" 200 "$(code /admin/)"
check "事件详情页" 200 "$(code /incident.html)"
check "RSS" 200 "$(code /feed.xml)"

echo "== 2. 敏感路径必须 404 =="
for p in /.env /data/status-data.json /config/gatus/config.yaml /.git/config; do
  check "$p" 404 "$(code "$p")"
done

echo "== 3. 鉴权 =="
check "匿名读用户" 401 "$(code /api/users)"
check "匿名读完整设置" 401 "$(code /api/settings/full)"
anon_post=$(curl -sk -o /dev/null -w '%{http_code}' -X POST --resolve "$DOMAIN:443:127.0.0.1" \
  "https://$DOMAIN/api/incidents" -H 'Content-Type: application/json' -d '{}')
check "匿名建事件" 401 "$anon_post"

echo "== 4. 安全头 =="
for h in strict-transport-security x-content-type-options x-frame-options content-security-policy referrer-policy; do
  if curl -skI --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/" | grep -qi "^$h"; then
    printf '  [OK]   %-34s 存在\n' "$h"
  else
    printf '  [FAIL] %-34s 缺失\n' "$h"; FAIL=$((FAIL+1))
  fi
done

echo "== 5. 容器（应为 5 个：caddy/api/watcher/collector/gatus）=="
cd /opt/status-page || exit 1
running=$(docker compose ps --status running --format '{{.Name}}' | wc -l)
check "运行中的容器数" 5 "$running"
for name in status-caddy status-api status-watcher status-collector status-gatus; do
  if docker compose ps --format '{{.Name}}' | grep -qx "$name"; then
    printf '  [OK]   %s 存在\n' "$name"
  else
    printf '  [FAIL] %s 缺失\n' "$name"; FAIL=$((FAIL+1))
  fi
done
if [ -f /etc/cron.d/status-collector ]; then
  printf '  [WARN] 宿主机仍有 status-collector cron（与容器重复，建议删除）\n'
fi

echo "== 6. 密钥与权限 =="
perm=$(stat -c '%a' /opt/status-page/.env 2>/dev/null)
check ".env 权限" 600 "$perm"
dev=$(grep '^DEV_ECHO_CODE=' /opt/status-page/.env | cut -d= -f2)
check "开发模式已关闭" 0 "$dev"

echo
if [ "$FAIL" -eq 0 ]; then
  echo "全部通过 ✅"
else
  echo "有 $FAIL 项未通过 ❌"
fi
exit "$FAIL"
