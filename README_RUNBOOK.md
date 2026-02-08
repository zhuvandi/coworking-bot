# Runbook (coworking-bot)

```bash
# обновить сервер одной командой
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && make deploy'

# посмотреть логи
journalctl -u coworking-bot.service -n 200 --no-pager

# проверить smoke (doctor)
/root/coworkingbot-doctor.sh --smoke

# быстрый rollback на tag
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && git fetch --tags && git checkout tags/<TAG> && make deploy'

# env-файл (секреты не коммитим)
sudo install -m 600 /home/coworkingbot/coworkingbot.env.example /etc/default/coworking-bot
sudo systemctl edit coworking-bot.service
```

Systemd override (пример в `systemd/coworking-bot.override.conf.example`):

```ini
[Service]
EnvironmentFile=/etc/default/coworking-bot
WorkingDirectory=/home/coworkingbot
Environment=PYTHONPATH=/home/coworkingbot
ExecStart=
ExecStart=/home/coworkingbot/venv/bin/python -m coworkingbot.working_bot_fixed
```
