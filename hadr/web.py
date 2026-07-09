"""Web app (ADR-0013): a read-only site users visit to see current alerts.

Pull delivery — a small stdlib http.server queries the SQLite store on each
request. Two views, both self-contained HTML (no framework, no external
assets):
- `/`            index: feed-health banner (ADR-0010), active alerts, updates
- `/event/<id>`  detail: every source's claim + full timeline + outbound links

`render_page` and `render_event_page` are pure functions so they can be tested
without a socket.
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
_SOURCE_LABEL = {"usgs": "USGS", "gdacs": "GDACS", "reliefweb": "ReliefWeb"}


def _fmt(ts) -> str:
    if not ts:
        return "—"
    s = ts if isinstance(ts, str) else ts.isoformat()
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return s


def _source_url(source: str, source_id: str) -> str:
    if source == "gdacs":
        return f"https://www.gdacs.org/report.aspx?eventid={source_id}"
    if source == "reliefweb":
        return f"https://reliefweb.int/disaster/{source_id}"
    return f"https://earthquake.usgs.gov/earthquakes/eventpage/{source_id}"


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


# --- index ('/') -----------------------------------------------------------

def render_page(store: Store, config: Config, *, live: bool = True) -> str:
    """Render the index. `live=True` (the served page) auto-refreshes; `live=False`
    (the committed dashboard.html snapshot) does not and is labelled as of its
    generation time."""
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
        cards = "\n".join(_event_card(e, _reliefweb_links(store, e["id"])) for e in active)
    else:
        cards = '<p class="empty">No active alerts. All monitored hazards are below threshold.</p>'

    ended = store.recently_ended_alerts(config.recent_alert_days)
    ended_html = ""
    if ended:
        ecards = "\n".join(_event_card(e, _reliefweb_links(store, e["id"])) for e in ended)
        ended_html = (
            f'<h2>Earlier this week — ended ({len(ended)})</h2>\n{ecards}'
        )

    notable = store.notable_events(config.notable_mag_min, config.recent_alert_days)
    notable_html = ""
    if notable:
        nrows = "\n".join(_notable_row(e) for e in notable)
        notable_html = (
            f"<h2>Notable seismic activity — M{config.notable_mag_min:g}+ this week "
            f"({len(notable)})</h2>"
            '<p class="hint">Significant earthquakes for awareness — includes ones assessed '
            "low-impact, which do not raise a humanitarian alert.</p>"
            "<table><thead><tr><th>Mag</th><th>Location</th><th>Impact</th><th>When</th></tr></thead>"
            f"<tbody>{nrows}</tbody></table>"
        )

    rows = "\n".join(_update_row(u) for u in updates) or (
        '<tr><td colspan="3" class="empty">No updates recorded yet.</td></tr>'
    )

    refresh = '<meta http-equiv="refresh" content="30">' if live else ""
    footer = (
        "Auto-refreshes every 30s · generated " if live else "Snapshot generated "
    ) + _fmt(now_utc().isoformat())
    return _PAGE.format(
        style=_STYLE, refresh=refresh, banner=banner, count=len(active),
        cards=cards, ended=ended_html, notable=notable_html, rows=rows, footer=footer,
    )


def write_dashboard(store: Store, config: Config) -> str:
    """Render a static snapshot to config.dashboard_path (the README product
    artifact) and return the path written. Reuses the live renderer so the
    committed dashboard and the served page never drift."""
    html_text = render_page(store, config, live=False)
    path = config.dashboard_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
    return str(path)


def _reliefweb_links(store: Store, event_id: int) -> list[str]:
    return [
        _source_url("reliefweb", r["source_id"])
        for r in store.source_records_for_event(event_id)
        if r["source"] == "reliefweb"
    ]


def _event_card(e, reliefweb_links: list[str]) -> str:
    level = AlertLevel(e["alert_level"])
    color = _LEVEL_COLOR.get(level, "#666")
    emoji = HAZARD_EMOJI.get(e["hazard_type"], "⚠️")
    title = html.escape(e["title"] or "(unnamed event)")
    ended = '<span class="flag">ended</span>' if e["retracted"] else ""
    meta_parts = []
    if e["country"]:
        meta_parts.append(html.escape(e["country"]))
    if e["occurred_at"]:
        meta_parts.append(f"occurred {_fmt(e['occurred_at'])}")
    meta_parts.append(f"updated {_fmt(e['updated_at'])}")
    enrich = '<div class="enrich">📰 ReliefWeb — confirmed</div>' if reliefweb_links else ""
    return f"""<a class="cardlink" href="/event/{e["id"]}">
    <div class="card" style="border-left-color:{color}">
      <div class="lvl" style="background:{color}">{level.label}</div>
      <div class="body">
        <div class="ttl">{emoji} {e["hazard_type"]} — {title}{ended}</div>
        <div class="meta">{" · ".join(meta_parts)}</div>
        {enrich}
      </div>
      <div class="chev">›</div>
    </div></a>"""


def _notable_row(e) -> str:
    level = AlertLevel(e["alert_level"])
    color = _LEVEL_COLOR.get(level, "#666")
    place = html.escape(e["title"] or e["country"] or "—")
    return (
        f'<tr><td><strong>M{e["peak_mag"]:.1f}</strong></td>'
        f'<td><a href="/event/{e["id"]}">{place}</a></td>'
        f'<td><span class="tag" style="background:{color}">{level.label}</span></td>'
        f'<td class="ts">{_fmt(e["occurred_at"])}</td></tr>'
    )


def _update_row(u) -> str:
    level = AlertLevel(u["level"])
    verb = _TRANSITION_VERB.get(Transition(u["transition"]), "UPDATE")
    color = _LEVEL_COLOR.get(level, "#666")
    title = html.escape(u["title"] or "")
    return (
        f'<tr><td class="ts">{_fmt(u["sent_at"])}</td>'
        f'<td><span class="tag" style="background:{color}">{verb}</span> '
        f'{u["hazard_type"]} · {level.label}</td>'
        f'<td><a href="/event/{u["event_id"]}">{title}</a></td></tr>'
    )


# --- detail ('/event/<id>') ------------------------------------------------

def render_event_page(store: Store, config: Config, event_id: int) -> str | None:
    """Full detail for one canonical event, or None if it doesn't exist (404)."""
    ev = store.get_event(event_id)
    if ev is None:
        return None
    sources = store.source_records_for_event(event_id)
    notifs = store.notifications_for_event(event_id)

    level = ev.alert_level
    color = _LEVEL_COLOR.get(level, "#666")
    emoji = HAZARD_EMOJI.get(ev.hazard_type, "⚠️")
    title = html.escape(ev.title or "(unnamed event)")

    flags = ""
    if ev.provisional:
        flags += '<span class="flag">unassessed</span>'
    if ev.retracted:
        flags += '<span class="flag">retracted</span>'

    facts = [("Country", html.escape(ev.country or "—")),
             ("GLIDE", html.escape(ev.glide or "—"))]
    if ev.lat is not None and ev.lon is not None:
        osm = f"https://www.openstreetmap.org/?mlat={ev.lat}&mlon={ev.lon}#map=6/{ev.lat}/{ev.lon}"
        facts.append(("Location", f'{ev.lat:.3f}, {ev.lon:.3f} '
                                   f'<a href="{osm}" target="_blank" rel="noopener">map ↗</a>'))
    facts.append(("Occurred", _fmt(ev.occurred_at)))
    facts.append(("Last updated", _fmt(ev.updated_at)))
    facts_html = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in facts)

    src_rows = "\n".join(
        f"<tr><td>{_SOURCE_LABEL.get(r['source'], r['source'])}</td>"
        f"<td>{AlertLevel(r['claim_level']).label}</td>"
        f"<td>{('M%.1f' % r['mag']) if r['mag'] is not None else '—'}</td>"
        f"<td>{html.escape(r['status'] or '—')}</td>"
        f"<td class='ts'>{_fmt(r['source_updated_at'] or r['last_seen'])}</td>"
        f"<td><a href=\"{_source_url(r['source'], r['source_id'])}\" "
        f"target=\"_blank\" rel=\"noopener\">{html.escape(r['source_id'])} ↗</a></td></tr>"
        for r in sources
    ) or '<tr><td colspan="6" class="empty">No source records.</td></tr>'

    timeline = "\n".join(
        f'<tr><td class="ts">{_fmt(n["sent_at"])}</td>'
        f'<td><span class="tag" style="background:'
        f'{_LEVEL_COLOR.get(AlertLevel(n["level"]), "#666")}">'
        f'{_TRANSITION_VERB.get(Transition(n["transition"]), "UPDATE")}</span></td>'
        f'<td>{AlertLevel(n["level"]).label}</td></tr>'
        for n in notifs
    ) or '<tr><td colspan="3" class="empty">No updates recorded — stored on first sighting (ADR-0009).</td></tr>'

    return _EVENT_PAGE.format(
        style=_STYLE, title=title, emoji=emoji, hazard=ev.hazard_type,
        level=level.label, color=color, flags=flags, facts=facts_html,
        source_count=len(sources), sources=src_rows, timeline=timeline,
    )


class _Handler(BaseHTTPRequestHandler):
    config: Config
    db_path: str

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            store = Store(self.db_path)
            try:
                self._send(200, render_page(store, self.config).encode("utf-8"))
            finally:
                store.close()
        elif path.startswith("/event/"):
            self._render_event(path)
        elif path == "/healthz":
            self._send(200, b"ok", "text/plain")
        else:
            self._send(404, b"Not found", "text/plain")

    def _render_event(self, path: str) -> None:
        raw = path[len("/event/"):]
        if not raw.isdigit():
            self._send(404, b"Not found", "text/plain")
            return
        store = Store(self.db_path)
        try:
            page = render_event_page(store, self.config, int(raw))
        finally:
            store.close()
        if page is None:
            self._send(404, b"Event not found", "text/plain")
        else:
            self._send(200, page.encode("utf-8"))

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


_STYLE = """
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
         background: #f6f7f9; color: #1a1a1a; }
  @media (prefers-color-scheme: dark) { body { background:#14161a; color:#e8e8e8; }
    .card { background:#1e2127 !important; } th { color:#aaa !important; } }
  header { padding: 1rem 1.25rem; background:#0b3d66; color:#fff; }
  header h1 { margin:0; font-size:1.15rem; }
  header .sub { opacity:.85; font-size:.8rem; }
  header a { color:#cde3ff; text-decoration:none; font-size:.85rem; }
  main { max-width: 52rem; margin: 0 auto; padding: 1rem 1.25rem 3rem; }
  .banner { padding:.6rem .9rem; border-radius:8px; margin:1rem 0; font-size:.9rem; }
  .banner.ok { background:#e6f4ea; color:#1e4620; }
  .banner.bad { background:#fdecea; color:#611a15; font-weight:600; }
  .banner.warn { background:#fff4e5; color:#663c00; }
  h2 { font-size:.95rem; text-transform:uppercase; letter-spacing:.04em; opacity:.7; margin:1.5rem 0 .5rem; }
  .cardlink { text-decoration:none; color:inherit; display:block; }
  .card { display:flex; align-items:stretch; background:#fff; border-radius:10px; margin:.5rem 0;
          border-left:6px solid; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.08);
          transition:box-shadow .12s, transform .12s; }
  .cardlink:hover .card { box-shadow:0 3px 10px rgba(0,0,0,.16); transform:translateY(-1px); }
  .card .lvl { color:#fff; font-weight:700; font-size:.72rem; padding:.75rem .6rem; display:flex; align-items:center; }
  .card .body { padding:.6rem .8rem; flex:1; }
  .card .ttl { font-weight:600; }
  .card .meta { font-size:.82rem; opacity:.7; margin-top:.15rem; }
  .card .enrich { font-size:.8rem; margin-top:.3rem; color:#0b6; }
  .card .chev { display:flex; align-items:center; padding:0 .8rem; font-size:1.4rem; opacity:.35; }
  .lvlchip { display:inline-block; color:#fff; font-weight:700; font-size:.8rem;
             padding:.15rem .55rem; border-radius:5px; vertical-align:middle; }
  .flag { display:inline-block; font-size:.7rem; text-transform:uppercase; letter-spacing:.03em;
          border:1px solid currentColor; border-radius:4px; padding:.05rem .35rem; margin-left:.4rem; opacity:.7; }
  table { width:100%; border-collapse:collapse; font-size:.85rem; margin:.3rem 0; }
  th, td { text-align:left; padding:.4rem .5rem; border-bottom:1px solid rgba(128,128,128,.2); vertical-align:top; }
  table.facts th { width:9rem; opacity:.7; font-weight:600; }
  .ts { white-space:nowrap; opacity:.7; }
  .tag { color:#fff; font-size:.68rem; font-weight:700; padding:.1rem .4rem; border-radius:4px; }
  a { color:#2c6fbb; }
  .empty { opacity:.6; font-style:italic; }
  .hint { font-size:.8rem; opacity:.65; margin:.2rem 0 .4rem; }
  footer { text-align:center; font-size:.75rem; opacity:.5; padding:1rem; }
"""

_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{refresh}
<title>HADR Monitor</title>
<style>{style}</style></head><body>
<header><h1>🌐 HADR Monitor</h1>
  <div class="sub">Humanitarian-impact disaster alerts · GDACS + USGS + ReliefWeb</div></header>
<main>
  {banner}
  <h2>Current alerts ({count})</h2>
  {cards}
  {ended}
  {notable}
  <h2>Recent updates</h2>
  <table><thead><tr><th>When</th><th>Change</th><th>Event</th></tr></thead>
  <tbody>
  {rows}
  </tbody></table>
</main>
<footer>{footer}</footer>
</body></html>"""

_EVENT_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{emoji} {hazard} — HADR Monitor</title>
<style>{style}</style></head><body>
<header><a href="/">← All alerts</a>
  <h1>{emoji} {hazard} — {title}</h1>
  <div class="sub"><span class="lvlchip" style="background:{color}">{level}</span>{flags}</div>
</header>
<main>
  <h2>Details</h2>
  <table class="facts">{facts}</table>
  <h2>Sources ({source_count})</h2>
  <table><thead><tr><th>Source</th><th>Claim</th><th>Mag</th><th>Status</th><th>Updated</th><th>Link</th></tr></thead>
  <tbody>
  {sources}
  </tbody></table>
  <h2>Timeline</h2>
  <table><thead><tr><th>When</th><th>Change</th><th>Level</th></tr></thead>
  <tbody>
  {timeline}
  </tbody></table>
</main>
<footer>Each source's claim is preserved separately (ADR-0004); alerts read the merged event.</footer>
</body></html>"""
