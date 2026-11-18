"""Speaker-labelled transcription with AssemblyAI (it fetches the audio URL itself)."""
from __future__ import annotations

import logging
import os

import assemblyai as aai

from . import storage
from .schemas import EpisodeRecord

log = logging.getLogger(__name__)


def transcribe(rec: EpisodeRecord) -> dict:
    existing = storage.load_transcript(rec.episode.id)
    if existing:
        return existing

    key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not set")
    aai.settings.api_key = key

    log.info("Transcribing %s", rec.episode.title)
    cfg = aai.TranscriptionConfig(speaker_labels=True, punctuate=True, format_text=True)
    t = aai.Transcriber(config=cfg).transcribe(rec.episode.audio_url)
    if t.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"Transcription failed: {t.error}")

    data = {
        "episode_id": rec.episode.id,
        "utterances": [
            {"speaker": u.speaker, "start": u.start // 1000, "end": u.end // 1000, "text": u.text}
            for u in (t.utterances or [])
        ],
    }
    storage.save_transcript(rec.episode.id, data)
    return data
