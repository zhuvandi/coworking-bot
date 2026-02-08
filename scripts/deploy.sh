#!/usr/bin/env bash

set -euo pipefail

report_failure() {
  echo "Deploy failed. Service status/logs:"
  systemctl status coworking-bot.service --no-pager || true
  journalctl -u coworking-bot.service -n 200 --no-pager || true
}

trap report_failure ERR

git pull --ff-only
make ci
sudo systemctl restart coworking-bot.service
make smoke
