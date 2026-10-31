#!/usr/bin/env bash
# One-time: connect rclone to OneDrive for off-site backup copies.
#   cd /opt/hawksroost && bash scripts/setup-offsite.sh
# rclone asks questions; answers are in docs/DEPLOY.md ("Off-site backups").
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/rclone
docker run --rm -it -v "$PWD/data/rclone:/config/rclone" rclone/rclone:1.71 config
if [ -f data/rclone/rclone.conf ]; then
  if grep -q '^COMPOSE_PROFILES=.*offsite' .env; then
    echo "offsite already enabled in .env"
  else
    sed -i 's/^COMPOSE_PROFILES=\(.*\)$/COMPOSE_PROFILES=\1,offsite/; s/^COMPOSE_PROFILES=,/COMPOSE_PROFILES=/' .env
    echo "Turned on offsite in .env"
  fi
  docker compose up -d
  echo "Off-site copies start within a few minutes. Check: docker compose logs --tail=5 offsite"
fi
