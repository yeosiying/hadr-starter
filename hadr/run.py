"""Entrypoint: live poller and replay harness.

    uv run hadr run                 # live USGS poll loop (ADR-0005/0008)
    uv run hadr replay FILE ...     # feed archived payloads through the pipeline

Slice 1 is USGS-only, so the loop is a simple synchronous poll rather than the
asyncio multi-feed scheduler ADR-0008 describes — that arrives with GDACS in
slice 2 (recorded in implementation-notes.md).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .archive import archive_payload
from .config import Config, load_config
from .feeds import usgs
from .notify import Notifier
from .pipeline import process_payload
from .store import Store

STALENESS_FAILURES = 3  # ~N x cadence before a degraded notice (ADR-0010)
BACKOFF_CAP_SECONDS = 600


def _open(config: Config) -> tuple[Store, Notifier]:
    store = Store(config.db_path)
    return store, Notifier(store, config)


def cmd_replay(config: Config, files: list[str]) -> int:
    store, notifier = _open(config)
    total = 0
    for f in files:
        payload = Path(f).read_bytes()
        sent = process_payload(store, notifier, config, payload, raw_ref=f)
        print(f"[replay] {f}: {len(sent)} notification(s)")
        total += len(sent)
    print(f"[replay] done — {total} notification(s) across {len(files)} file(s)")
    store.close()
    return 0


def cmd_run(config: Config) -> int:
    store, notifier = _open(config)
    feed = usgs.SOURCE
    print(
        f"[run] polling USGS every {config.usgs_poll_seconds}s "
        f"(dry_run={config.dry_run}); Ctrl-C to stop"
    )
    # Cold start: on a first-ever boot, absorb the 24h window store-only so we
    # don't blast alerts for events that already happened (ADR-0009, simplified
    # — see implementation-notes.md).
    first_poll_alerts = store.event_count() > 0
    failures = 0
    try:
        while True:
            state = store.get_feed_state(feed)
            ims = state["last_modified"] if state else None
            result = usgs.fetch(config.usgs_feed_url, if_modified_since=ims)

            if result.status == "error":
                failures += 1
                store.save_feed_state(feed, success=False)
                state = store.get_feed_state(feed)
                if failures >= STALENESS_FAILURES and not state["degraded_notified"]:
                    notifier.send_feed_health(feed, degraded=True)
                    store.save_feed_state(feed, success=False, degraded_notified=True)
                sleep = min(config.usgs_poll_seconds * (2**failures), BACKOFF_CAP_SECONDS)
                print(f"[run] fetch error: {result.error}; backing off {sleep}s")
                time.sleep(sleep)
                continue

            # Success (200 or 304). Announce recovery if we were degraded.
            if state and state["degraded_notified"]:
                notifier.send_feed_health(feed, degraded=False)
            failures = 0

            if result.status == "ok":
                raw = archive_payload(config.archive_dir, feed, result.payload)
                sent = process_payload(
                    store, notifier, config, result.payload,
                    raw_ref=str(raw), alert=first_poll_alerts,
                )
                if not first_poll_alerts:
                    print(f"[run] cold-start backfill absorbed {feed} window (store-only)")
                elif sent:
                    print(f"[run] {len(sent)} alert(s) sent")
            store.save_feed_state(
                feed, success=True, last_modified=result.last_modified, degraded_notified=False
            )
            first_poll_alerts = True
            time.sleep(config.usgs_poll_seconds)
    except KeyboardInterrupt:
        print("\n[run] stopped")
    finally:
        store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hadr", description="HADR monitoring agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="live USGS poll loop")
    replay = sub.add_parser("replay", help="feed archived payloads through the pipeline")
    replay.add_argument("files", nargs="+", help="payload file(s) to replay")

    args = parser.parse_args(argv)
    config = load_config()

    if args.command == "run":
        return cmd_run(config)
    if args.command == "replay":
        return cmd_replay(config, args.files)
    return 1


if __name__ == "__main__":
    sys.exit(main())
