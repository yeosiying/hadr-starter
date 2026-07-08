"""Web app (ADR-0013): a read-only page users visit to see current alerts.

Pull delivery — a small stdlib http.server queries the SQLite store on each
request and renders a self-contained HTML page: a feed-health banner (so
silence stays trustworthy, ADR-0010), the current active alerts, and a recent
updates feed. No framework, no external assets. `render_page` is a pure
function so it can be tested without a socket.
"""

from __future__ import annotations

import html
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import Config
from .models import AlertLevel, Transition, now_utc
from .notify import HAZARD_EMOJI
from .store import Store

STALENESS_FACTOR = 3  # a feed is "degraded" past this many cadences without success

_LEVEL_COLOR = {
    AlertLevel.RED: "#c0392b",
    AlertLevel.ORANGE: "#d35400",
    AlertLevel.YELLOW: "#c29d0b",
    AlertLevel.PROVISIONAL: "#2c6fbb",
    AlertLevel.GREEN: "#2e7d32",
    AlertLevel.NONE: "#666",
}
_TRANSITION_VERB = {
    Transition.NEW: "ALERT",
    Transition.ESCALATION: "ESCALATION",
    Transition.CONFIRMATION: "CONFIRMED",
    Transition.RETRACTION: "STAND-DOWN",
}


def _fmt(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return ts


def _feed_health(store: Store, config: Config) -> list[dict]:
    cadence = {"usgs": config.usgs_poll_seconds, "gdacs": config.gdacs_poll_seconds}
    now = now_utc()
    out = []
    for row in store.all_feed_state():
        feed = row["feed"]
        last = row["last_success_at"]
        stale_after = cadence.get(feed, 600) * STALENESS_FACTOR
        degraded = True
        if last:
            age = (now - datetime.fromisoformat(last)).total_seconds()
            degraded = age > stale_after
        out.append({"feed": feed, "degraded": degraded, "last_success": last})
    return out


def render_page(store: Store, config: Config) -> str:
    health = _feed_health(store, config)
    active = store.active_events()
    updates = store.recent_notifications(limit=50)

    degraded = [h for h in health if h["degraded"]]
    if not health:
        banner = ('<div class="banner warn">No feed activity yet — start the poller '
                  "with <code>hadr run</code>.</div>")
    elif degraded:
        names = ", ".join(h["feed"] for h in degraded)
        banner = f'<div class="banner bad">⚠ Feed degraded: {html.escape(names)} — alerts may be stale.</div>'
    else:
        times = " · ".join(f"{h['feed']}: {_fmt(h['last_success'])}" for h in health)
        banner = f'<div class="banner ok">✓ All feeds healthy — last success {html.escape(times)}</div>'

    if active:
        cards = "\n".join(_event_card(e) for e in active)
    else:
        cards = '<p class="empty">No active alerts. All monitored hazards are below threshold.</p>'

    rows = "\n".join(_update_row(u) for u in updates) or (
        '<tr><td colspan="3" class="empty">No updates recorded yet.</td></tr>'
    )

    return _PAGE.format(
        banner=banner,
        count=len(active),
        cards=cards,
        rows=rows,
        generated=_fmt(now_utc().isoformat()),
    )


def _event_card(e) -> str:
    level = AlertLevel(e["alert_level"])
    color = _LEVEL_COLOR.get(level, "#666")
    emoji = HAZARD_EMOJI.get(e["hazard_type"], "⚠️")
    title = html.escape(e["title"] or "(unnamed event)")
    country = html.escape(e["country"] or "")
    return f"""<div class="card" style="border-left-color:{color}">
      <div class="lvl" style="background:{color}">{level.label}</div>
      <div class="body">
        <div class="ttl">{emoji} {e["hazard_type"]} — {title}</div>
        <div class="meta">{country}{' · ' if country else ''}updated {_fmt(e["updated_at"])}</div>
      </div>
    </div>"""


def _update_row(u) -> str:
    level = AlertLevel(u["level"])
    verb = _TRANSITION_VERB.get(Transition(u["transition"]), "UPDATE")
    color = _LEVEL_COLOR.get(level, "#666")
    title = html.escape(u["title"] or "")
    return (
        f'<tr><td class="ts">{_fmt(u["sent_at"])}</td>'
        f'<td><span class="tag" style="background:{color}">{verb}</span> '
        f'{u["hazard_type"]} · {level.label}</td>'
        f"<td>{title}</td></tr>"
    )


class _Handler(BaseHTTPRequestHandler):
    config: Config
    db_path: str

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path in ("/", "/index.html"):
            store = Store(self.db_path)
            try:
                page = render_page(store, self.config)
            finally:
                store.close()
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args) -> None:  # quieter default logging
        print(f"[web] {self.address_string()} {fmt % args}")


def serve(config: Config) -> None:
    handler = type("Handler", (_Handler,), {"config": config, "db_path": str(config.db_path)})
    httpd = ThreadingHTTPServer((config.web_host, config.web_port), handler)
    print(f"[web] serving on http://{config.web_host}:{config.web_port} (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[web] stopped")
    finally:
        httpd.server_close()


_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>HADR Monitor</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
         background: #f6f7f9; color: #1a1a1a; }}
  @media (prefers-color-scheme: dark) {{ body {{ background:#14161a; color:#e8e8e8; }}
    .card, .feed {{ background:#1e2127 !important; }} th {{ color:#aaa !important; }} }}
  header {{ padding: 1rem 1.25rem; background:#0b3d66; color:#fff; }}
  header h1 {{ margin:0; font-size:1.15rem; }}
  header .sub {{ opacity:.8; font-size:.8rem; }}
  main {{ max-width: 52rem; margin: 0 auto; padding: 1rem 1.25rem 3rem; }}
  .banner {{ padding:.6rem .9rem; border-radius:8px; margin:1rem 0; font-size:.9rem; }}
  .banner.ok {{ background:#e6f4ea; color:#1e4620; }}
  .banner.bad {{ background:#fdecea; color:#611a15; font-weight:600; }}
  .banner.warn {{ background:#fff4e5; color:#663c00; }}
  h2 {{ font-size:.95rem; text-transform:uppercase; letter-spacing:.04em; opacity:.7; margin:1.5rem 0 .5rem; }}
  .card {{ display:flex; background:#fff; border-radius:10px; margin:.5rem 0;
          border-left:6px solid; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .card .lvl {{ color:#fff; font-weight:700; font-size:.72rem; padding:.75rem .6rem; display:flex; align-items:center; }}
  .card .body {{ padding:.6rem .8rem; }}
  .card .ttl {{ font-weight:600; }}
  .card .meta {{ font-size:.82rem; opacity:.7; margin-top:.15rem; }}
  table {{ width:100%; border-collapse:collapse; font-size:.85rem; }}
  th, td {{ text-align:left; padding:.4rem .5rem; border-bottom:1px solid rgba(128,128,128,.2); vertical-align:top; }}
  .ts {{ white-space:nowrap; opacity:.7; }}
  .tag {{ color:#fff; font-size:.68rem; font-weight:700; padding:.1rem .4rem; border-radius:4px; }}
  .empty {{ opacity:.6; font-style:italic; }}
  footer {{ text-align:center; font-size:.75rem; opacity:.5; padding:1rem; }}
</style></head><body>
<header><h1>🌐 HADR Monitor</h1>
  <div class="sub">Humanitarian-impact disaster alerts · GDACS + USGS</div></header>
<main>
  {banner}
  <h2>Current alerts ({count})</h2>
  {cards}
  <h2>Recent updates</h2>
  <table><thead><tr><th>When</th><th>Change</th><th>Event</th></tr></thead>
  <tbody>
  {rows}
  </tbody></table>
</main>
<footer>Auto-refreshes every 30s · generated {generated}</footer>
</body></html>"""
