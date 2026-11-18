"""Settings. Everything can be overridden with environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EPISODES_DIR = DATA / "episodes"
TRANSCRIPTS_DIR = DATA / "transcripts"
STATE_FILE = DATA / "state.json"
SITE_DIR = ROOT / "site"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Podcast feed. `or` so an empty FEED_URL variable in CI still falls back to the default.
FEED_URL = os.environ.get("FEED_URL") or "https://feeds.megaphone.fm/candace"
SHOW_NAME = os.environ.get("SHOW_NAME", "Candace")
# Safety check: the feed's title must contain this text, so a wrong feed fails loudly.
EXPECTED_FEED_TITLE = os.environ.get("EXPECTED_FEED_TITLE", "Candace")

# Claude
MODEL = os.environ.get("FACTCHECK_MODEL") or "claude-opus-5-5"
EXTRACT_EFFORT = os.environ.get("EXTRACT_EFFORT") or "medium"
VERIFY_EFFORT = os.environ.get("VERIFY_EFFORT") or "high"
MAX_SEARCHES_PER_CLAIM = int(os.environ.get("MAX_SEARCHES_PER_CLAIM") or "8")
MAX_CLAIMS_PER_EPISODE = int(os.environ.get("MAX_CLAIMS_PER_EPISODE") or "25")
VERIFY_CONCURRENCY = int(os.environ.get("VERIFY_CONCURRENCY") or "4")

# Transcript chunking for claim extraction (seconds)
CHUNK_SECONDS = 15 * 60
CHUNK_OVERLAP_SECONDS = 60

# Site
SITE_TITLE = os.environ.get("SITE_TITLE", "Candace Podcast Fact Check")
CORRECTIONS_URL = os.environ.get("CORRECTIONS_URL", "")  # e.g. https://github.com/<you>/<repo>/issues/new
