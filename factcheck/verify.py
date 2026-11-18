"""Research each claim with web search and give a sourced verdict."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from . import config, llm, storage
from .extract import fmt_time
from .schemas import CheckedClaim, Episode, VerificationResult

log = logging.getLogger(__name__)


def _context(transcript: dict, at: int, window: int = 45) -> str:
    return "\n".join(
        f"[{fmt_time(u['start'])}] Speaker {u['speaker']}: {u['text']}"
        for u in transcript["utterances"]
        if u["end"] >= at - window and u["start"] <= at + window
    )


def _tools() -> list[dict]:
    return [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": config.MAX_SEARCHES_PER_CLAIM},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": config.MAX_SEARCHES_PER_CLAIM},
    ]


def enforce_rules(v: VerificationResult, seen: set[str]) -> VerificationResult:
    """Drop citations that never appeared in tool results; a verdict with no sources becomes Unsupported."""
    def norm(u: str) -> str:
        return u.split("#")[0].rstrip("/").lower()

    seen_n = {norm(u) for u in seen}
    v.sources = [s for s in v.sources if norm(s.url) in seen_n]
    if not v.sources and v.verdict != "Unsupported":
        v.explanation = f"[Original verdict: {v.verdict}, downgraded because no verifiable source was cited.] {v.explanation}"
        v.verdict = "Unsupported"
        v.confidence = "low"
    return v


def verify_claim(episode: Episode, claim: CheckedClaim, transcript: dict) -> CheckedClaim:
    user = (
        f"Podcast: {config.SHOW_NAME} — episode \"{episode.title}\" (published {episode.published}).\n"
        f"Speaker: {claim.speaker_name}\n\n"
        f"Claim to check: {claim.claim}\n\n"
        f"Exact quote: \"{claim.quote}\"\n\n"
        f"Surrounding transcript (automatic transcription, may contain errors):\n<context>\n"
        f"{_context(transcript, claim.start_seconds)}\n</context>\n\n"
        f"Check the claim as of today, but judge it against what was known on the publication date where that matters."
    )
    try:
        result, resp = llm.structured_call(
            system=(config.PROMPTS_DIR / "verify.md").read_text(),
            user=user,
            output=VerificationResult,
            effort=config.VERIFY_EFFORT,
            tools=_tools(),
        )
        llm.web_search_failures(resp)
        claim.verification = enforce_rules(result, llm.seen_urls(resp))
        claim.model = resp.model
        claim.error = None
    except Exception as e:  # keep going; the claim is retried on the next run
        if llm.is_out_of_credits(e):
            raise llm.OutOfCredits(str(e)) from e
        log.exception("Verification failed for %s/%s", episode.id, claim.id)
        claim.error = f"{type(e).__name__}: {e}"[:300]
    claim.checked_at = storage.now_iso()
    return claim


def verify_all(episode: Episode, claims: list[CheckedClaim], transcript: dict, on_done=None) -> list[CheckedClaim]:
    todo = [c for c in claims if c.verification is None]
    log.info("Verifying %d claim(s) for %s", len(todo), episode.title)
    with ThreadPoolExecutor(max_workers=config.VERIFY_CONCURRENCY) as pool:
        futures = [pool.submit(verify_claim, episode, c, transcript) for c in todo]
        try:
            for f in futures:
                c = f.result()
                if on_done:
                    on_done(c)
        except llm.OutOfCredits:
            for f in futures:
                f.cancel()  # don't start the rest; in-flight ones finish and are saved by the caller
            raise
    return claims
