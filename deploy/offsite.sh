#!/bin/sh
# Copies data/backups to the rclone remote once a day (after the 3 am backup).
# Set up the remote once with: scripts/setup-offsite.sh
while true; do
  if [ -f /config/rclone/rclone.conf ]; then
    rclone copy /backups "$RCLONE_REMOTE/backups" --max-age 3d --log-level NOTICE \
      && echo "$(date) off-site copy OK" || echo "$(date) off-site copy FAILED"
  else
    echo "No rclone config yet; run scripts/setup-offsite.sh"
  fi
  sleep 21600
done
