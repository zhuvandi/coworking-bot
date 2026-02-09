gh auth login
git push
cd /home/coworkingbot && git status -sb && git log -1 --oneline
cd /home/coworkingbot && git remote -v
cd /home/coworkingbot && git push
cd /home/coworkingbot && sudo -u coworkingbot -H bash -lc 'gh run list --workflow ci.yml --limit 20'
cd /home/coworkingbot && sudo -u coworkingbot -H bash -lc 'gh run view <RUN_ID> --log-failed'
cd /home/coworkingbot && git remote -v
cd /home/coworkingbot && git remote set-url origin https://github.com/zhuvandi/coworking-bot.git
cd /home/coworkingbot
gh auth status
gh run list --workflow ci.yml --limit 20
gh run view 21801333776 --log-failed
gh pr list --head fix/ci-ruff-imports
gh run view 21805960045 --log-failed
gh pr list --head fix/ci-ruff-imports
cd /home/coworkingbot
gh run view 21801333776 --summary
GH_PAGER=cat gh run view 21805960045 --log
GH_PAGER=cat gh run view 21805960045 --log-failed
GH_PAGER=cat gh run view 21805960045 --repo zhuvandi/coworking-bot --log-failed
gh pr create --head fix/ci-ruff-imports --base master --title "Fix ruff import order" --body "Fix ruff import order (I rules)."
cd /home/coworkingbot && gh pr view 11 --json number,headRefName,baseRefName,state,url
cd /home/coworkingbot && gh pr checks 11
cd /home/coworkingbot && gh pr merge 11 --merge --delete-branch
cd /home/coworkingbot && git switch master && git pull --ff-only
cd /home/coworkingbot && gh pr checks 11
cd /home/coworkingbot && gh pr merge 11 --merge --delete-branch
cd /home/coworkingbot && git switch master
cd /home/coworkingbot && git pull --ff-only
cd /home/coworkingbot && make ci
systemctl restart coworking-bot.service
systemctl status coworking-bot.service --no-pager
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && make smoke; echo "RC=$?"'
systemctl restart coworking-bot.service
systemctl status coworking-bot.service --no-pager -l
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && make smoke; echo "RC=$?"'
cd /home/coworkingbot && make smoke; echo "RC=$?"
sudo systemctl restart coworking-bot.service
sudo systemctl status coworking-bot.service --no-pager -l
sudo -u coworkingbot -H bash -lc 'cd /home/coworkingbot && make smoke; echo "RC=$?"'
sudo systemctl restart coworking-bot.service
exit
