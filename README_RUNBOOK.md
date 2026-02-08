# Runbook (coworking-bot)

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
