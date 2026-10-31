#!/usr/bin/env bash
# Pull the latest version and restart what changed.
#   bash /opt/hawksroost/scripts/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."
before=$(git rev-parse --short HEAD)
git pull --ff-only
after=$(git rev-parse --short HEAD)
echo "Version: $before -> $after"
docker compose up -d --build --remove-orphans
docker image prune -f >/dev/null
docker compose ps --format '  {{.Service}}: {{.Status}}'
