"""Pull checkable factual claims out of a transcript."""
from __future__ import annotations

import difflib
import logging

from . import config, llm
from .schemas import CheckedClaim, ExtractedClaim, ExtractionResult

log = logging.getLogger(__name__)


def fmt_time(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def chunk_transcript(utterances: list[dict]) -> list[str]:
    """Group utterances into ~15-minute windows with a small overlap."""
    if not utterances:
        return []
    end = utterances[-1]["end"]
    chunks, start = [], 0
    while start < end:
        stop = start + config.CHUNK_SECONDS
        lines = [
            f"[{fmt_time(u['start'])}] Speaker {u['speaker']}: {u['text']}"
            for u in utterances
            if u["end"] > start - config.CHUNK_OVERLAP_SECONDS and u["start"] < stop
        ]
        if lines:
            chunks.append("\n".join(lines))
        start = stop
    return chunks


def _is_dup(a: ExtractedClaim, b: ExtractedClaim) -> bool:
    if abs(a.start_seconds - b.start_seconds) < 120 and difflib.SequenceMatcher(None, a.claim, b.claim).ratio() > 0.6:
        return True
    return difflib.SequenceMatcher(None, a.claim.lower(), b.claim.lower()).ratio() > 0.85


def select_claims(claims: list[ExtractedClaim], limit: int) -> list[ExtractedClaim]:
    """Drop near-duplicates, keep the most check-worthy, return in episode order."""
    ranked = sorted(claims, key=lambda c: (-c.checkworthiness, c.start_seconds))
    kept: list[ExtractedClaim] = []
    for c in ranked:
        if c.checkworthiness >= 2 and not any(_is_dup(c, k) for k in kept):
            kept.append(c)
        if len(kept) >= limit:
            break
    return sorted(kept, key=lambda c: c.start_seconds)


def extract(episode_title: str, transcript: dict) -> list[CheckedClaim]:
    system = (config.PROMPTS_DIR / "extract.md").read_text()
    chunks = chunk_transcript(transcript["utterances"])
    found: list[ExtractedClaim] = []
    speakers: dict[str, str] = {}
    for i, chunk in enumerate(chunks, 1):
        log.info("Extracting claims: segment %d/%d", i, len(chunks))
        result, _ = llm.structured_call(
            system=system,
            user=f"Episode: {episode_title}\nSegment {i} of {len(chunks)}\n\n<transcript>\n{chunk}\n</transcript>",
            output=ExtractionResult,
            effort=config.EXTRACT_EFFORT,
        )
        found.extend(result.claims)
        for s in result.speakers:
            if s.likely_identity and s.likely_identity != "Unknown":
                speakers.setdefault(s.label, s.likely_identity)

    chosen = select_claims(found, config.MAX_CLAIMS_PER_EPISODE)
    log.info("Kept %d of %d extracted claims", len(chosen), len(found))
    return [
        CheckedClaim(
            id=f"c{n:02d}",
            speaker_name=speakers.get(c.speaker, "Unknown"),
            **c.model_dump(),
        )
        for n, c in enumerate(chosen, 1)
    ]
