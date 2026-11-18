import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from factcheck import config, discover, extract, llm, site, storage, verify
from factcheck.schemas import (CheckedClaim, Episode, EpisodeRecord, ExtractedClaim,
                               ExtractionResult, Source, VerificationResult)

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(config, "TRANSCRIPTS_DIR", tmp_path / "transcripts")
    monkeypatch.setattr(config, "SITE_DIR", tmp_path / "site")
    return tmp_path


def test_parse_feed_and_discover_is_idempotent(monkeypatch):
    monkeypatch.setattr(config, "EXPECTED_FEED_TITLE", "test show")
    eps = discover.parse_feed(str(FIX / "feed.xml"))
    assert [e.title for e in eps] == ["Episode Two: The Sequel", "Episode One"]
    assert eps[0].duration_seconds == 3723 and eps[1].duration_seconds == 3600
    assert eps[0].id.startswith("2026-11-11-episode-two-the-sequel-")
    assert len(discover.discover(5, str(FIX / "feed.xml"))) == 2
    assert discover.discover(5, str(FIX / "feed.xml")) == []


def test_json_schema_is_strict_and_inlined():
    s = llm.json_schema(ExtractionResult)
    text = json.dumps(s)
    assert "$ref" not in text and "$defs" not in text
    claim = s["properties"]["claims"]["items"]
    assert claim["additionalProperties"] is False
    assert set(claim["required"]) == set(ExtractedClaim.model_fields)
    assert "Disputed" in json.dumps(llm.json_schema(VerificationResult))


def test_chunking_and_selection():
    utts = [{"speaker": "A", "start": t, "end": t + 50, "text": f"line {t}"} for t in range(0, 2400, 60)]
    chunks = extract.chunk_transcript(utts)
    assert len(chunks) == 3 and chunks[0].startswith("[0:00] Speaker A")
    mk = lambda claim, t, w: ExtractedClaim(quote="q", claim=claim, speaker="A", start_seconds=t,
                                            category="history", checkworthiness=w)
    picked = extract.select_claims([
        mk("The treaty was signed in 1919 in Versailles.", 500, 5),
        mk("The treaty was signed in 1919 at Versailles.", 520, 4),   # duplicate
        mk("Unemployment was 3.4% in January 2023.", 100, 3),
        mk("Minor aside", 50, 1),                                      # too minor
    ], limit=10)
    assert [c.start_seconds for c in picked] == [100, 500]


def _verification(urls, verdict="False"):
    return VerificationResult(verdict=verdict, confidence="high", explanation="e", what_is_true="t",
                              sources=[Source(url=u, title="t", publisher="p", excerpt="x") for u in urls])


def test_invented_sources_are_dropped_and_verdict_downgraded():
    v = verify.enforce_rules(_verification(["https://real.org/a/", "https://made-up.com/x"]), {"https://real.org/a"})
    assert [s.url for s in v.sources] == ["https://real.org/a/"] and v.verdict == "False"
    v = verify.enforce_rules(_verification(["https://made-up.com/x"]), set())
    assert v.verdict == "Unsupported" and v.confidence == "low" and v.sources == []


class FakeStream:
    def __init__(self, resp): self.resp = resp
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_final_message(self): return self.resp


def test_structured_call_handles_pause_turn_and_collects_search_urls(monkeypatch):
    final = _verification(["https://src.gov/report"]).model_dump_json()
    search = NS(type="web_search_tool_result", content=[NS(url="https://src.gov/report")])
    responses = [
        NS(stop_reason="pause_turn", content=[search], model="m"),
        NS(stop_reason="end_turn", content=[NS(type="text", text=final)], model="m", stop_details=None),
    ]
    calls = []

    def stream(**kw):
        calls.append(kw)
        return FakeStream(responses.pop(0))

    monkeypatch.setattr(llm, "_client", NS(beta=NS(messages=NS(stream=stream))))
    ep = Episode(id="e1", title="T", published="2026-11-10", audio_url="https://x/a.mp3")
    claim = CheckedClaim(id="c01", quote="q", claim="c", speaker="A", start_seconds=10,
                         category="history", checkworthiness=5)
    out = verify.verify_claim(ep, claim, {"utterances": [{"speaker": "A", "start": 5, "end": 20, "text": "q"}]})
    assert out.error is None and out.verification.verdict == "False"
    assert len(calls) == 2 and calls[1]["messages"][1]["role"] == "assistant"
    assert calls[0]["fallbacks"] == "default" and calls[0]["output_config"]["format"]["type"] == "json_schema"
    assert {t["type"] for t in calls[0]["tools"]} == {"web_search_20260209", "web_fetch_20260209"}


def test_refusal_is_recorded_as_error_not_crash(monkeypatch):
    resp = NS(stop_reason="refusal", content=[], model="m", stop_details=NS(category="cyber"))
    monkeypatch.setattr(llm, "_client", NS(beta=NS(messages=NS(stream=lambda **kw: FakeStream(resp)))))
    ep = Episode(id="e1", title="T", published="2026-11-10", audio_url="https://x/a.mp3")
    claim = CheckedClaim(id="c01", quote="q", claim="c", speaker="A", start_seconds=10,
                         category="history", checkworthiness=5)
    out = verify.verify_claim(ep, claim, {"utterances": []})
    assert out.verification is None and "ClaudeRefusal" in out.error


def test_site_build(tmp_data):
    ep = Episode(id="2026-11-10-test", title="A <script> title", published="2026-11-10", audio_url="https://x/a.mp3")
    claims = [CheckedClaim(id="c01", quote="q1", claim="c1", speaker="A", speaker_name="Candace Owens (host)",
                           start_seconds=75, category="history", checkworthiness=5,
                           verification=_verification(["https://src.gov/r"], "Accurate")),
              CheckedClaim(id="c02", quote="q2", claim="c2", speaker="B", start_seconds=90,
                           category="statistics", checkworthiness=4)]
    storage.save_record(EpisodeRecord(episode=ep, status="extracted", claims=claims))
    site.build()
    index = (tmp_data / "site" / "index.html").read_text()
    page = (tmp_data / "site" / "episodes" / "2026-11-10-test.html").read_text()
    assert "A &lt;script&gt; title" in index and "<script> title" not in index
    assert "▶ 1:15" in page and "1 more claim(s) still being checked" in page
    assert 'href="../static/style.css"' in page


def test_wrong_feed_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "EXPECTED_FEED_TITLE", "Candace")
    with pytest.raises(RuntimeError, match="wrong podcast"):
        discover.discover(5, str(FIX / "feed.xml"))
    assert storage.all_records() == []


def test_sources_missing_title_or_extra_keys_are_accepted():
    v = VerificationResult.model_validate({
        "verdict": "Accurate", "confidence": "high", "explanation": "e", "what_is_true": "t", "surprise": 1,
        "sources": [{"url": "https://a.org/x", "excerpt": "x"}],
    })
    assert v.sources[0].title == "" and v.sources[0].publisher == ""


def test_run_summary_and_exit_code(tmp_data, monkeypatch):
    summary = tmp_data / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_REPOSITORY", "DiscoInfernoz/Fact-Check")
    from factcheck import __main__ as cli
    monkeypatch.setattr(config, "EXPECTED_FEED_TITLE", "Candace")
    assert cli.main(["discover", "--feed", str(FIX / "feed.xml")]) == 1
    text = summary.read_text()
    assert "https://discoinfernoz.github.io/Fact-Check/" in text and "wrong podcast" in text
