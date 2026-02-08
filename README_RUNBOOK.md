# Runbook (coworking-bot)

## Обновить сервер одной командой

```bash
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && make deploy'
```

## Systemd конфигурация (env + override)

```bash
sudo install -m 600 /home/coworkingbot/coworkingbot.env.example /etc/default/coworking-bot
sudo systemctl edit coworking-bot.service
```

Содержимое override (оставляем текущие WorkingDirectory и PYTHONPATH), пример есть в `systemd/coworking-bot.override.conf.example`:

```ini
[Service]
EnvironmentFile=/etc/default/coworking-bot
WorkingDirectory=/home/coworkingbot
Environment=PYTHONPATH=/home/coworkingbot
ExecStart=
ExecStart=/home/coworkingbot/venv/bin/python -m coworkingbot.working_bot_fixed
```

## Обновить код (git pull)

```bash
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && git pull --ff-only'
```

## Прогнать проверки (make ci)

```bash
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && make ci'
```

## Перезапустить сервис

```bash
systemctl restart coworking-bot.service
```

## Smoke-проверка (doctor)

```bash
/root/coworkingbot-doctor.sh --smoke
```

## Логи сервиса

```bash
journalctl -u coworking-bot.service -n 200 --no-pager
```
