"""Data models. The Claude-facing ones are also used as JSON schemas for structured output."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal[
    "history", "science_health", "law_courts", "statistics", "current_events",
    "quote_attribution", "biography", "economics", "other",
]

Verdict = Literal[
    "Accurate", "Mostly accurate", "Missing context", "Misleading",
    "False", "Unsupported", "Disputed",
]

VERDICT_ORDER: list[str] = [
    "Accurate", "Mostly accurate", "Missing context", "Disputed",
    "Misleading", "Unsupported", "False",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- Claude structured outputs ----------

class ExtractedClaim(_Strict):
    quote: str = Field(description="Exact words from the transcript, trimmed to the claim itself.")
    claim: str = Field(description="The claim restated as one neutral, self-contained, checkable sentence.")
    speaker: str = Field(description="Speaker label as it appears in the transcript, e.g. 'A' or 'B'.")
    start_seconds: int = Field(description="Start time of the quote, in seconds from episode start.")
    category: Category
    checkworthiness: int = Field(description="1-5. 5 = specific, consequential, and verifiable.")


class ExtractionResult(_Strict):
    speakers: list[SpeakerGuess]
    claims: list[ExtractedClaim]


class SpeakerGuess(_Strict):
    label: str
    likely_identity: str = Field(description="'Candace Owens (host)', a guest's name if stated, or 'Unknown'.")


ExtractionResult.model_rebuild()


class Source(_Strict):
    url: str
    title: str
    publisher: str
    excerpt: str = Field(description="Short relevant excerpt from the source (under 50 words).")


class VerificationResult(_Strict):
    verdict: Verdict
    confidence: Literal["high", "medium", "low"]
    explanation: str = Field(description="At most 120 words, neutral tone.")
    what_is_true: str = Field(description="One or two sentences stating what the evidence does support.")
    sources: list[Source]


# ---------- Stored records ----------

class Episode(BaseModel):
    id: str
    title: str
    published: str  # ISO date
    audio_url: str
    link: str = ""
    duration_seconds: int | None = None
    description: str = ""


class CheckedClaim(BaseModel):
    id: str
    quote: str
    claim: str
    speaker: str
    speaker_name: str = "Unknown"
    start_seconds: int
    category: str
    checkworthiness: int
    verification: VerificationResult | None = None
    error: str | None = None
    model: str | None = None
    checked_at: str | None = None


class EpisodeRecord(BaseModel):
    episode: Episode
    status: Literal["discovered", "transcribed", "extracted", "verified"] = "discovered"
    claims: list[CheckedClaim] = []
    updated_at: str = ""
