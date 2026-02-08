# Runbook (coworking-bot)

1) Update code: `sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && git pull --ff-only'`
2) Run CI: `sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && make ci'`
3) Restart: `sudo systemctl restart coworking-bot.service`
4) Smoke: `/root/coworkingbot-doctor.sh --smoke`
5) Logs: `journalctl -u coworking-bot.service -n 200 --no-pager`
6) Rollback: `sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && git fetch --tags && git checkout tags/<TAG> && make deploy'`
7) Env file: `sudo install -m 640 -o root -g coworkingbot /home/coworkingbot/coworkingbot.env.example /etc/default/coworking-bot`
8) Edit env: `sudo nano /etc/default/coworking-bot`
9) Override: `sudo systemctl edit coworking-bot.service`
10) Override contents:

```ini
[Service]
EnvironmentFile=/etc/default/coworking-bot
WorkingDirectory=/home/coworkingbot
Environment=PYTHONPATH=/home/coworkingbot
ExecStart=
ExecStart=/home/coworkingbot/venv/bin/python -m coworkingbot.working_bot_fixed
```
