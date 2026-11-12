#!/bin/sh
# 更新状态页（拉取代码 → 备份数据 → 重建容器 → 健康检查）
#   sh deploy/update.sh            # 从 git 拉取最新
#   sh deploy/update.sh v0.2.0     # 切到指定 tag/commit
set -e
cd "$(dirname "$0")/.." || exit 1
DIR=$(pwd)
TARGET="$1"

echo "==> 1/5 备份数据"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p /root/dsh-backups
docker run --rm -v status-page_api-data:/d -v /root/dsh-backups:/b alpine \
  tar -C /d -czf "/b/api-data-$STAMP.tgz" . 2>/dev/null || echo "   (跳过：卷尚不存在)"
echo "   备份文件: /root/dsh-backups/api-data-$STAMP.tgz"

echo "==> 2/5 拉取代码"
if [ -d .git ]; then
  git fetch --tags --prune
  if [ -n "$TARGET" ]; then
    git checkout "$TARGET"
  else
    git pull --ff-only
  fi
  echo "   当前版本: $(git describe --tags --always 2>/dev/null || echo unknown)"
else
  echo "   非 git 目录，跳过拉取（请手动替换文件）"
fi

echo "==> 3/5 重建容器"
docker compose pull --quiet 2>/dev/null || true
docker compose up -d

echo "==> 4/5 等待服务就绪"
sleep 8

echo "==> 5/5 健康检查"
DOMAIN=$(grep '^DOMAIN=' .env 2>/dev/null | cut -d= -f2)
DOMAIN=${DOMAIN:-status.example.com}
if sh deploy/verify.sh "$DOMAIN"; then
  echo
  echo "✅ 更新完成（$STAMP）"
  echo "   如需回滚数据：docker run --rm -v status-page_api-data:/d -v /root/dsh-backups:/b alpine sh -c 'rm -rf /d/* && tar -C /d -xzf /b/api-data-$STAMP.tgz'"
else
  echo
  echo "⚠️ 健康检查未全部通过，请查看：docker compose logs --tail 50"
  exit 1
fi
