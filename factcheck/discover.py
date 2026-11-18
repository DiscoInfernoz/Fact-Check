"""Find episodes in the podcast's RSS feed."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.request

import feedparser

from . import config, storage
from .schemas import Episode, EpisodeRecord

log = logging.getLogger(__name__)
UA = "podcast-factcheck/0.1 (+https://github.com)"


def resolve_feed_url() -> str:
    if config.FEED_URL:
        return config.FEED_URL
    url = f"https://itunes.apple.com/lookup?id={config.APPLE_PODCAST_ID}&entity=podcast"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        results = json.load(resp).get("results", [])
    if not results or not results[0].get("feedUrl"):
        raise RuntimeError(f"No feed URL found for Apple Podcasts id {config.APPLE_PODCAST_ID}; set FEED_URL.")
    log.info("Resolved feed for %r: %s", results[0].get("collectionName"), results[0]["feedUrl"])
    return results[0]["feedUrl"]


def _duration(entry) -> int | None:
    raw = entry.get("itunes_duration")
    if not raw:
        return None
    try:
        parts = [int(float(p)) for p in str(raw).split(":")]
    except ValueError:
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs


def parse_feed(source: str) -> list[Episode]:
    """`source` is a URL or a local path / raw XML string (used by tests)."""
    feed = feedparser.parse(source, agent=UA)
    episodes: list[Episode] = []
    for e in feed.entries:
        audio = next((l.href for l in e.get("links", []) if l.get("rel") == "enclosure"), None)
        if not audio and e.get("enclosures"):
            audio = e.enclosures[0].get("href")
        if not audio:
            continue
        guid = e.get("id") or audio
        t = e.get("published_parsed") or e.get("updated_parsed")
        date = time.strftime("%Y-%m-%d", t) if t else "0000-00-00"
        short = hashlib.sha1(guid.encode()).hexdigest()[:6]
        episodes.append(Episode(
            id=f"{date}-{storage.slugify(e.get('title', ''))[:50]}-{short}",
            title=e.get("title", "Untitled"),
            published=date,
            audio_url=audio,
            link=e.get("link", ""),
            duration_seconds=_duration(e),
            description=(e.get("summary") or "")[:2000],
        ))
    episodes.sort(key=lambda ep: ep.published, reverse=True)
    return episodes


def discover(backfill: int, feed_source: str | None = None) -> list[EpisodeRecord]:
    """Register the newest `backfill` episodes that aren't stored yet. Returns new records."""
    episodes = parse_feed(feed_source or resolve_feed_url())
    log.info("Feed has %d episodes", len(episodes))
    new: list[EpisodeRecord] = []
    for ep in episodes[:backfill]:
        if storage.load_record(ep.id) is None:
            rec = EpisodeRecord(episode=ep)
            storage.save_record(rec)
            new.append(rec)
    log.info("Registered %d new episode(s)", len(new))
    return new
