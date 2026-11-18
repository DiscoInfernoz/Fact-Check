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

# Podcast feed. Set FEED_URL directly, or leave it empty and the feed URL is
# looked up from Apple Podcasts using APPLE_PODCAST_ID.
FEED_URL = os.environ.get("FEED_URL", "")
APPLE_PODCAST_ID = os.environ.get("APPLE_PODCAST_ID", "1725552624")
SHOW_NAME = os.environ.get("SHOW_NAME", "Candace")

# Claude
MODEL = os.environ.get("FACTCHECK_MODEL", "claude-opus-5-5")
EXTRACT_EFFORT = os.environ.get("EXTRACT_EFFORT", "medium")
VERIFY_EFFORT = os.environ.get("VERIFY_EFFORT", "high")
MAX_SEARCHES_PER_CLAIM = int(os.environ.get("MAX_SEARCHES_PER_CLAIM", "8"))
MAX_CLAIMS_PER_EPISODE = int(os.environ.get("MAX_CLAIMS_PER_EPISODE", "25"))
VERIFY_CONCURRENCY = int(os.environ.get("VERIFY_CONCURRENCY", "4"))

# Transcript chunking for claim extraction (seconds)
CHUNK_SECONDS = 15 * 60
CHUNK_OVERLAP_SECONDS = 60

# Site
SITE_TITLE = os.environ.get("SITE_TITLE", "Candace Podcast Fact Check")
CORRECTIONS_URL = os.environ.get("CORRECTIONS_URL", "")  # e.g. https://github.com/<you>/<repo>/issues/new
