"""Deterministic sitrep data dump: current store state as JSON.

Emits everything the situation report needs — feed health, active alerts, and
recent changes — so the prose step never has to touch SQL. Run:

    uv run python skills/sitrep/query.py
"""

from __future__ import annotations

import json

from hadr.config import load_config
from hadr.models import AlertLevel, Transition, now_utc
from hadr.store import Store
from hadr.web import _feed_health


def main() -> None:
    cfg = load_config()
    store = Store(cfg.db_path)
    try:
        health = _feed_health(store, cfg)
        active = []
        for e in store.active_events():
            rw = [
                f"https://reliefweb.int/disaster/{r['source_id']}"
                for r in store.source_records_for_event(e["id"])
                if r["source"] == "reliefweb"
            ]
            active.append({
                "hazard": e["hazard_type"],
                "level": AlertLevel(e["alert_level"]).label,
                "title": e["title"],
                "country": e["country"],
                "provisional": bool(e["provisional"]),
                "updated_at": e["updated_at"],
                "reliefweb": rw,
            })
        updates = [
            {
                "at": n["sent_at"],
                "change": Transition(n["transition"]).name,
                "level": AlertLevel(n["level"]).label,
                "hazard": n["hazard_type"],
                "title": n["title"],
            }
            for n in store.recent_notifications(limit=25)
        ]
    finally:
        store.close()

    print(json.dumps({
        "generated_at": now_utc().isoformat(),
        "feeds": health,
        "active_alerts": active,
        "recent_updates": updates,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
