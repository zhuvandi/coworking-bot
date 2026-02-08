# Runbook (coworking-bot)

```bash
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && make deploy'
sudo systemctl status coworking-bot.service --no-pager
journalctl -u coworking-bot.service -n 200 --no-pager
sudo systemctl restart coworking-bot.service
sudo systemctl stop coworking-bot.service
sudo systemctl start coworking-bot.service
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && git log -n 5 --oneline'
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && git reset --hard HEAD~1'
sudo systemctl restart coworking-bot.service
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && make smoke'
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && git pull --ff-only'
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && make ci'
```
