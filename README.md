# Podcast Fact Check

Automatically fact-checks each episode of the *Candace* podcast and publishes the results as a static website.

```
RSS feed → transcribe (AssemblyAI, speaker labels) → extract factual claims (Claude)
        → verify each claim with web search (Claude) → data/episodes/*.json → static site (GitHub Pages)
```

Each claim on the site shows the exact quote, a timestamp link into the audio, the speaker, a verdict (Accurate, Mostly accurate, Missing context, Disputed, Misleading, Unsupported, False), a short explanation and the sources. Opinions and predictions aren't rated. Citations that didn't come from the model's actual search results are removed, and a verdict with no sources is changed to *Unsupported*.

## Setup

1. **Create a GitHub repo** and push this folder to it.
2. **Add repository secrets** (Settings → Secrets and variables → Actions):
   - `ANTHROPIC_API_KEY`: from console.anthropic.com
   - `ASSEMBLYAI_API_KEY`: from assemblyai.com
3. **Turn on Pages**: Settings → Pages → Source: *GitHub Actions*.
4. **Feed:** the default feed is `https://feeds.megaphone.fm/candace`. To use a different one, set a repository *variable* `FEED_URL`. A run stops with an error if the feed's title doesn't contain "Candace", so a wrong feed can't be checked by mistake.
5. Actions → *Fact-check episodes* → **Run workflow** with `backfill: 3`, `max_episodes: 3` for a first test.

**Where to see results:** each run's page in the Actions tab starts with a summary: the site link, each episode, how many claims were checked, and any errors. A red ❌ run means something failed; work finished before the failure is still saved and published, and the rest is retried the next day. The site is at `https://<your-username>.github.io/<repo-name>/` (for this repo, https://discoinfernoz.github.io/Fact-Check/).

After that it runs every day, checks new episodes and redeploys the site. For a bigger backfill, run it manually with e.g. `backfill: 50`. Each run processes at most `max_episodes` and the daily runs work through the rest, so no single run hits the 6-hour job limit.

## Running locally

```bash
python -m venv .venv && . .venv/bin/activate && pip install -e .
export ANTHROPIC_API_KEY=... ASSEMBLYAI_API_KEY=...
python -m factcheck run --backfill 1        # newest episode only
python -m factcheck build && python -m http.server -d site 8000
```

Other commands: `discover --backfill N`, `process [--episode ID] [--max-episodes N]`, `build`.
Every stage saves its progress, so re-running only does unfinished work. Failed claims are retried on the next run.

## Settings

Set these as repository *variables* (Settings → Secrets and variables → Actions → Variables) to change them without editing code. Leave a variable unset to use the default.

| Variable | Default | |
|---|---|---|
| `FACTCHECK_MODEL` | `claude-opus-5-5` | Model for extraction and verification |
| `MAX_CLAIMS_PER_EPISODE` | `12` | The biggest cost lever |
| `MAX_SEARCHES_PER_CLAIM` | `4` | Web searches allowed per claim |
| `MAX_FETCHES_PER_CLAIM` | `3` | Full-page reads allowed per claim |
| `FETCH_MAX_TOKENS` | `6000` | How much of each fetched page is read |
| `VERIFY_EFFORT` / `EXTRACT_EFFORT` | `high` / `medium` | Claude effort levels |
| `VERIFY_CONCURRENCY` | `4` | Claims checked in parallel |

## Cost

The defaults aim for about $1 per episode on Opus 5.5, plus about $0.15–0.40 for transcription. (The first version, with 25 claims and 8 searches each, cost about $6.) Each run's summary shows the estimated Claude spend per episode, and each episode's total is stored as `cost_usd` in its data file. For lower costs, set `FACTCHECK_MODEL=claude-sonnet-5-5` (about half the price) or reduce `MAX_CLAIMS_PER_EPISODE`.

## Notes

- Transcripts are stored in `data/transcripts/` but **not** published on the site; only short quotes appear.
- The results are AI-generated. Spot-check verdicts, especially the ones marked low confidence, before you share them widely.
