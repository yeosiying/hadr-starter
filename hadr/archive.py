"""Raw payload archive (ADR-0006, CLAUDE.md convention 1).

Every fetched payload is written verbatim to disk *before* parsing. The
archive is the audit trail ("why did/didn't this alert?") and the replay-test
corpus (ADR-0012). Layout: <archive_dir>/<source>/<YYYY-MM-DD>/<timestamp>.<ext>
"""

from __future__ import annotations

from pathlib import Path

from .models import datetime, now_utc


def archive_payload(
    archive_dir: Path,
    source: str,
    payload: bytes,
    *,
    ext: str = "json",
    at: datetime | None = None,
) -> Path:
    """Write payload verbatim, return its path. Timestamp is UTC, filename-safe."""
    at = at or now_utc()
    day = at.strftime("%Y-%m-%d")
    stamp = at.strftime("%Y%m%dT%H%M%S_%f")
    dest_dir = archive_dir / source / day
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stamp}.{ext}"
    dest.write_bytes(payload)
    return dest
