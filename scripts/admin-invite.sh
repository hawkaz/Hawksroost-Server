#!/usr/bin/env bash
# Print a one-time link to create an admin account (good for 2 days).
#   bash /opt/hawksroost/scripts/admin-invite.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T api python -m app.cli invite-admin
