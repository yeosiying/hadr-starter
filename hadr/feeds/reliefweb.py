"""ReliefWeb feed: fetch + parse (ADR-0011, ADR-0014, feeds/reliefweb.md).

Uses the public **RSS** feed (`disasters/rss.xml`), which needs no approved
`appname` — so enrichment works today. The appname-gated JSON API is a future
upgrade (ADR-0014); `config.reliefweb_appname` is reserved for it.

ReliefWeb never triggers alerts (ADR-0001): every record's `claim_level` is
NONE. Its value is editorial confirmation and, above all, the **GLIDE** number
that ties a ReliefWeb disaster to the same GDACS/USGS canonical event. Records
attach to existing events only (enrich-only, see pipeline); they never create
standalone canonical events.

RSS shape (feeds/reliefweb.md): <item> has title, link, pubDate, and an
HTML description carrying `Glide: XX-YYYY-NNNNNN-ISO` and `Affected country:`.
No ETag/Last-Modified, so polling is unconditional and the content-hash guards
against reprocessing.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

import httpx

from ..models import AlertLevel, SourceRecord
from .usgs import FetchResult

SOURCE = "reliefweb"
RSS_URL = "https://reliefweb.int/disasters/rss.xml"

_GLIDE_RE = re.compile(r"Glide:\s*([A-Za-z]{2}-\d{4}-\d{6}-[A-Za-z]{3})")
_COUNTRY_RE = re.compile(r"Affected countr(?:y|ies):\s*([^<]+)")

# GLIDE / title hazard hints -> our internal hazard codes.
_TITLE_HAZARD = [
    ("earthquake", "EQ"),
    ("cyclone", "TC"), ("typhoon", "TC"), ("hurricane", "TC"), ("storm", "TC"),
    ("flood", "FL"),
    ("volcan", "VO"),
    ("drought", "DR"),
    ("wild fire", "WF"), ("wildfire", "WF"), ("forest fire", "WF"),
]
_KNOWN = {"EQ", "TC", "FL", "VO", "DR", "WF"}


def fetch(
    url: str = RSS_URL,
    *,
    client: httpx.Client | None = None,
    timeout: float = 30.0,
) -> FetchResult:
    owns = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        resp = client.get(url, headers={"User-Agent": "hadr-monitor/0.1"})
        if resp.status_code >= 400:
            return FetchResult(status="error", error=f"HTTP {resp.status_code}")
        return FetchResult(status="ok", payload=resp.content)
    except httpx.HTTPError as exc:
        return FetchResult(status="error", error=str(exc))
    finally:
        if owns:
            client.close()


def _hazard_of(glide: str | None, title: str) -> str:
    if glide:
        code = glide[:2].upper()
        if code in _KNOWN:
            return code
    low = title.lower()
    for needle, code in _TITLE_HAZARD:
        if needle in low:
            return code
    return "OT"  # other — stored, never alertable (hazard scope, ADR-0002)


def parse(payload: bytes, *, raw_ref: str | None = None) -> list[SourceRecord]:
    """Parse the disasters RSS into SourceRecords. Tolerant of a UTF-8 BOM."""
    root = ET.fromstring(payload.decode("utf-8-sig"))
    records: list[SourceRecord] = []
    for i, item in enumerate(root.findall("./channel/item")):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = item.findtext("description") or ""
        if not link:
            continue
        slug = link.rstrip("/").rsplit("/", 1)[-1]
        gl = _GLIDE_RE.search(desc)
        glide = gl.group(1).upper() if gl else None
        co = _COUNTRY_RE.search(desc)
        country = co.group(1).strip() if co else None
        pub = item.findtext("pubDate")
        occurred = None
        if pub:
            try:
                occurred = parsedate_to_datetime(pub)
                if occurred.tzinfo is None:
                    occurred = occurred.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                occurred = None
        records.append(
            SourceRecord(
                source=SOURCE,
                source_id=slug,
                hazard_type=_hazard_of(glide, title),
                claim_level=AlertLevel.NONE,  # never triggers (ADR-0001)
                place=title,
                country=country,
                glide=glide,
                status="current",
                occurred_at=occurred,
                raw_ref=f"{raw_ref}#{i}" if raw_ref else None,
                content_hash=hashlib.sha256(
                    f"{slug}|{glide}|{title}".encode()
                ).hexdigest(),
            )
        )
    return records
