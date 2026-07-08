"""Entrypoint: live poller and replay harness.

    uv run hadr run                       # concurrent USGS + GDACS poll loops
    uv run hadr web                        # serve the updates page (ADR-0013)
    uv run hadr replay [--feed F] FILE...  # feed archived payloads through the pipeline

The live loop runs one asyncio task per feed (ADR-0008), each on its own cadence
(ADR-0005). All DB access stays on the single event-loop thread, so the shared
SQLite connection needs no locking.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from .archive import archive_payload
from .config import Config, load_config
from .feeds import gdacs, usgs
from .feeds.usgs import FetchResult
from .notify import Notifier
from .pipeline import process_payload
from .store import Store

STALENESS_FAILURES = 3  # ~N x cadence before a degraded notice (ADR-0010)
BACKOFF_CAP_SECONDS = 600

PARSERS: dict[str, Callable] = {"usgs": usgs.parse, "gdacs": gdacs.parse}


@dataclass
class FeedSpec:
    name: str
    url: str
    interval: int
    parse: Callable
    conditional: bool  # send If-Modified-Since (USGS yes, GDACS has no caching hdrs)


def _specs(config: Config) -> list[FeedSpec]:
    return [
        FeedSpec("usgs", config.usgs_feed_url, config.usgs_poll_seconds, usgs.parse, True),
        FeedSpec("gdacs", config.gdacs_feed_url, config.gdacs_poll_seconds, gdacs.parse, False),
    ]


async def _afetch(
    client: httpx.AsyncClient, spec: FeedSpec, ims: str | None
) -> FetchResult:
    headers = {"Accept": "application/json"}
    if spec.conditional and ims:
        headers["If-Modified-Since"] = ims
    try:
        resp = await client.get(spec.url, headers=headers)
        if resp.status_code == 304:
            return FetchResult(status="not_modified")
        if resp.status_code >= 400:
            return FetchResult(status="error", error=f"HTTP {resp.status_code}")
        return FetchResult(
            status="ok", payload=resp.content, last_modified=resp.headers.get("Last-Modified")
        )
    except httpx.HTTPError as exc:
        return FetchResult(status="error", error=str(exc))


async def _poll_loop(
    client: httpx.AsyncClient,
    store: Store,
    notifier: Notifier,
    config: Config,
    spec: FeedSpec,
    alert_from_start: bool,
) -> None:
    first_alerts = alert_from_start
    failures = 0
    while True:
        state = store.get_feed_state(spec.name)
        ims = state["last_modified"] if state else None
        result = await _afetch(client, spec, ims)

        if result.status == "error":
            failures += 1
            store.save_feed_state(spec.name, success=False)
            state = store.get_feed_state(spec.name)
            if failures >= STALENESS_FAILURES and not state["degraded_notified"]:
                notifier.send_feed_health(spec.name, degraded=True)
                store.save_feed_state(spec.name, success=False, degraded_notified=True)
            sleep = min(spec.interval * (2**failures), BACKOFF_CAP_SECONDS)
            print(f"[{spec.name}] fetch error: {result.error}; backing off {sleep}s")
            await asyncio.sleep(sleep)
            continue

        if state and state["degraded_notified"]:
            notifier.send_feed_health(spec.name, degraded=False)
        failures = 0

        if result.status == "ok":
            raw = archive_payload(config.archive_dir, spec.name, result.payload)
            sent = process_payload(
                store, notifier, config, result.payload,
                parse=spec.parse, raw_ref=str(raw), alert=first_alerts,
            )
            if not first_alerts:
                print(f"[{spec.name}] cold-start backfill absorbed (store-only)")
            elif sent:
                print(f"[{spec.name}] {len(sent)} alert(s) sent")
        store.save_feed_state(
            spec.name, success=True, last_modified=result.last_modified, degraded_notified=False
        )
        first_alerts = True
        await asyncio.sleep(spec.interval)


async def _run_async(config: Config) -> None:
    store = Store(config.db_path)
    notifier = Notifier(store, config)
    # Cold start (ADR-0009): on a first-ever boot absorb each feed's current
    # window store-only so we don't alert on events that already happened.
    alert_from_start = store.event_count() > 0
    specs = _specs(config)
    print(
        f"[run] polling {', '.join(s.name for s in specs)}; "
        f"view updates at http://{config.web_host}:{config.web_port} (hadr web); Ctrl-C to stop"
    )
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            await asyncio.gather(
                *(
                    _poll_loop(client, store, notifier, config, spec, alert_from_start)
                    for spec in specs
                )
            )
        finally:
            store.close()


def cmd_run(config: Config) -> int:
    try:
        asyncio.run(_run_async(config))
    except KeyboardInterrupt:
        print("\n[run] stopped")
    return 0


def cmd_web(config: Config) -> int:
    from .web import serve

    serve(config)
    return 0


def cmd_dashboard(config: Config) -> int:
    from .web import write_dashboard

    store = Store(config.db_path)
    try:
        path = write_dashboard(store, config)
    finally:
        store.close()
    print(f"[dashboard] wrote {path}")
    return 0


def cmd_replay(config: Config, feed: str, files: list[str]) -> int:
    parse = PARSERS[feed]
    store = Store(config.db_path)
    notifier = Notifier(store, config)
    total = 0
    for f in files:
        payload = Path(f).read_bytes()
        sent = process_payload(store, notifier, config, payload, parse=parse, raw_ref=f)
        print(f"[replay:{feed}] {f}: {len(sent)} notification(s)")
        total += len(sent)
    print(f"[replay] done — {total} notification(s) across {len(files)} file(s)")
    store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hadr", description="HADR monitoring agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="live concurrent poll loops (USGS + GDACS)")
    sub.add_parser("web", help="serve the read-only updates page")
    sub.add_parser("dashboard", help="write a static dashboard.html snapshot")
    replay = sub.add_parser("replay", help="feed archived payloads through the pipeline")
    replay.add_argument("--feed", choices=sorted(PARSERS), default="usgs")
    replay.add_argument("files", nargs="+", help="payload file(s) to replay")

    args = parser.parse_args(argv)
    config = load_config()

    if args.command == "run":
        return cmd_run(config)
    if args.command == "web":
        return cmd_web(config)
    if args.command == "dashboard":
        return cmd_dashboard(config)
    if args.command == "replay":
        return cmd_replay(config, args.feed, args.files)
    return 1


if __name__ == "__main__":
    sys.exit(main())
