# Deploy — always-on host (ADR-0008)

Three long-lived pieces on one box: the **poller**, the **web page**, and a
timer that writes the **08:30 morning snapshot**. Everything shares one SQLite
file; `hadr run` writes, the others read.

## systemd (recommended)

Assumes the repo is at `/opt/hadr-monitor`, run by user `hadr`, with `uv`
installed. Adjust the `WorkingDirectory` / `User` in the unit files if not.

```sh
sudo cp deploy/systemd/hadr-*.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload

# Poller + web page (always on):
sudo systemctl enable --now hadr-monitor.service hadr-web.service

# Morning snapshot at 08:30 Asia/Singapore:
sudo systemctl enable --now hadr-dashboard.timer
```

Check it:

```sh
systemctl status hadr-monitor hadr-web
systemctl list-timers hadr-dashboard.timer     # next 08:30 SGT run
journalctl -u hadr-monitor -f                   # live poller log
```

The page is then at `http://127.0.0.1:8000` (localhost only, ADR-0013).
`dashboard.html` is rewritten each morning and on demand via
`uv run hadr dashboard`.

## cron alternative (snapshot only)

If you'd rather not use a timer for the morning snapshot:

```cron
# 08:30 Asia/Singapore — set CRON_TZ so the host timezone doesn't matter.
CRON_TZ=Asia/Singapore
30 8 * * *  cd /opt/hadr-monitor && /usr/bin/env uv run hadr dashboard
```

You still need the poller (`hadr run`) and page (`hadr web`) running —
under systemd, a process manager, or `tmux`/`nohup` for a quick setup.

## Notes

- No delivery secrets are required (web delivery, ADR-0013). If you later
  enable the ReliefWeb JSON API, put `HADR_RELIEFWEB_APPNAME` in a
  `.env` / `EnvironmentFile`.
- `data/` (SQLite + raw archive) lives under `WorkingDirectory`; back it up by
  copying the directory.
- On restart, cold-start backfill absorbs each feed's current window
  store-only so a reboot doesn't replay old alerts (ADR-0009).
