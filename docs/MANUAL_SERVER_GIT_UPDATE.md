# QuantBot server manual Git update

This project is intentionally updated by a human-triggered server command.
There is no Git polling service, cron job, systemd timer, webhook, or automatic
restart.

## One-time server setup

Run these commands in the server terminal. Do not run them from the local
Windows machine.

```bash
cd /www/wwwroot/QuantBot
git init
git remote add origin https://github.com/dinolik2099-cell/bot.git
git fetch origin main
```

Before checking out `main`, record the server's current state. The initial
checkout must not overwrite server-only data or secrets.

```bash
git status --short
git ls-tree -r --name-only origin/main | sed -n '1,80p'
```

If the server directory is confirmed to contain the same code snapshot and only
the intended server-only files differ, create a backup outside the project and
then attempt the safe initial checkout. Do not use `git reset --hard`.

```bash
git switch --track -c main origin/main
```

If `git switch` reports that an untracked file would be overwritten, it stops
without replacing that file. Compare or relocate that individual file before
trying again. Preserve `.env`, `data/`, `reports/`, `logs/`, and `venv/` outside
Git.

## Routine manual update

After a local change has been committed and pushed to GitHub, connect to the
server and run:

```bash
cd /www/wwwroot/QuantBot
bash scripts/manual_git_update.sh
```

The script fetches `origin/main` and only accepts a fast-forward update. It
refuses to act if tracked local edits exist or Git history has diverged. It does
not restart a process or run any research/backtest workload.

## Failure handling

The script does not roll back automatically. If it reports a refusal or a
Python compilation failure, stop and inspect the message before making another
change. Do not resolve the condition with `git reset --hard`.
