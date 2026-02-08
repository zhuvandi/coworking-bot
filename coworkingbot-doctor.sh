#!/usr/bin/env bash

set -u

VENV_PY="/home/coworkingbot/venv/bin/python"

MAIN_PY="/home/coworkingbot/coworkingbot/working_bot_fixed.py"
BASE_DIR="/home/coworkingbot"
STATUS=0

ok() {
  echo "OK: $*"
}

warn() {
  echo "WARN: $*"
}

err() {
  echo "ERR: $*"
  STATUS=1
}

check_exists() {
  local target="$1"
  local label="$2"

  if [[ -e "$target" ]]; then
    ok "$label exists ($target)"
  else
    err "$label missing ($target)"
  fi
}

py_compile_check() {
  if "$VENV_PY" -m py_compile "$MAIN_PY"; then
    ok "py_compile $MAIN_PY"
  else
    err "py_compile failed for $MAIN_PY"
  fi
}

py_import_check_systemd() {
  local unit_output
  unit_output=$(systemctl cat coworking-bot.service 2>/dev/null || true)

  if [[ -z "$unit_output" ]]; then
    err "systemd unit coworking-bot.service not found"
    return
  fi

  echo "$unit_output"

  if echo "$unit_output" | rg -q "override.conf"; then
    ok "systemd override.conf detected in unit output"
  fi

  if echo "$unit_output" | rg -q "^WorkingDirectory=/home/coworkingbot"; then
    ok "WorkingDirectory is /home/coworkingbot"
  else
    err "WorkingDirectory is not /home/coworkingbot"
  fi

  if echo "$unit_output" | rg -q "PYTHONPATH=/home/coworkingbot"; then
    ok "PYTHONPATH is /home/coworkingbot"
  else
    err "PYTHONPATH is not /home/coworkingbot"
  fi

  if PYTHONPATH="/home/coworkingbot" "$VENV_PY" - <<'PY'
import importlib
modules = [
    "coworkingbot.config",
    "coworkingbot.handlers",
    "coworkingbot.utils",
    "coworkingbot.utils.gas",
]
for name in modules:
    importlib.import_module(name)
print("imports ok")
PY
  then
    ok "systemd import check"
  else
    err "systemd import check failed"
  fi
}

smoke() {
  check_exists "$MAIN_PY" "Main module"
  check_exists "$BASE_DIR/coworkingbot/config.py" "coworkingbot/config.py"
  check_exists "$BASE_DIR/coworkingbot/handlers" "coworkingbot/handlers"
  check_exists "$BASE_DIR/coworkingbot/utils" "coworkingbot/utils"

  py_compile_check
  py_import_check_systemd

  if systemctl is-active --quiet coworking-bot.service; then
    ok "coworking-bot.service is active"
  else
    err "coworking-bot.service is not active"
    journalctl -u coworking-bot.service -n 120 --no-pager
  fi

  return "$STATUS"
}

case "${1:-}" in
  --smoke)
    smoke
    exit "$STATUS"
    ;;
  *)
    echo "Usage: $0 --smoke"
    exit 1
    ;;
esac
