"""JSON file storage. One file per episode, so every stage can be re-run safely."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from . import config
from .schemas import EpisodeRecord


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "episode"


def episode_path(episode_id: str):
    return config.EPISODES_DIR / f"{episode_id}.json"


def transcript_path(episode_id: str):
    return config.TRANSCRIPTS_DIR / f"{episode_id}.json"


def load_record(episode_id: str) -> EpisodeRecord | None:
    p = episode_path(episode_id)
    if not p.exists():
        return None
    return EpisodeRecord.model_validate_json(p.read_text())


def save_record(rec: EpisodeRecord) -> None:
    config.EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    rec.updated_at = now_iso()
    tmp = episode_path(rec.episode.id).with_suffix(".tmp")
    tmp.write_text(rec.model_dump_json(indent=2))
    tmp.replace(episode_path(rec.episode.id))


def all_records() -> list[EpisodeRecord]:
    if not config.EPISODES_DIR.exists():
        return []
    recs = [EpisodeRecord.model_validate_json(p.read_text()) for p in config.EPISODES_DIR.glob("*.json")]
    return sorted(recs, key=lambda r: r.episode.published, reverse=True)


def load_transcript(episode_id: str) -> dict | None:
    p = transcript_path(episode_id)
    return json.loads(p.read_text()) if p.exists() else None


def save_transcript(episode_id: str, data: dict) -> None:
    config.TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    transcript_path(episode_id).write_text(json.dumps(data))
