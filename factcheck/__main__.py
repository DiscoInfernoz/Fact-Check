"""CLI.

  python -m factcheck run [--backfill N] [--episode ID]   discover + process + build
  python -m factcheck discover --backfill N
  python -m factcheck process [--episode ID]              transcribe/extract/verify pending episodes
  python -m factcheck build                               regenerate site/
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from . import config, discover, extract, llm, site, storage, transcribe, verify

log = logging.getLogger("factcheck")


def process_episode(rec) -> None:
    ep = rec.episode
    log.info("== %s (%s)", ep.title, ep.id)
    transcript = transcribe.transcribe(rec)
    if rec.status == "discovered":
        rec.status = "transcribed"
        storage.save_record(rec)

    if rec.status == "transcribed":
        rec.claims = extract.extract(ep.title, transcript)
        rec.status = "extracted"
        storage.save_record(rec)

    # Save after every claim so a crash or timeout loses at most the in-flight ones.
    verify.verify_all(ep, rec.claims, transcript, on_done=lambda _c: storage.save_record(rec))
    if all(c.verification for c in rec.claims):
        rec.status = "verified"
    storage.save_record(rec)
    failed = sum(1 for c in rec.claims if c.error)
    log.info("Done: %d claims, %d failed (retried next run)", len(rec.claims), failed)


def process(episode_id: str | None, limit: int | None) -> int:
    recs = storage.all_records()
    if episode_id:
        recs = [r for r in recs if r.episode.id == episode_id]
        if not recs:
            log.error("No stored episode with id %s (run discover first)", episode_id)
            return 1
    pending = [r for r in recs if r.status != "verified"]
    pending.sort(key=lambda r: r.episode.published, reverse=True)  # newest first
    if limit:
        pending = pending[:limit]
    rows, failed_claims, errors = [], 0, 0
    for rec in pending:
        try:
            process_episode(rec)
            ok = sum(1 for c in rec.claims if c.verification)
            bad = sum(1 for c in rec.claims if c.error)
            failed_claims += bad
            rows.append(f"| {rec.episode.published} | {rec.episode.title} | {ok} | {bad} | |")
        except llm.OutOfCredits:
            storage.save_record(rec)
            errors += 1
            log.error("Anthropic API credit balance is too low. Stopping; finished work is saved.")
            rows.append(f"| {rec.episode.published} | {rec.episode.title} | "
                        f"{sum(1 for c in rec.claims if c.verification)} | | **Out of Anthropic API credits.** "
                        "Add credit at console.anthropic.com → Billing; the rest is picked up on the next run. |")
            break
        except Exception as e:
            errors += 1
            log.exception("Episode failed: %s", rec.episode.id)
            rows.append(f"| {rec.episode.published} | {rec.episode.title} | | | {type(e).__name__}: {str(e)[:150]} |")
    write_summary(rows, failed_claims, errors)
    # A red run in the Actions tab means something needs a look; work done so far is still saved.
    return 1 if (errors or failed_claims) else 0


def write_summary(rows: list[str], failed_claims: int, errors: int) -> None:
    """Markdown summary shown on the workflow run's page in GitHub."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    owner, _, name = repo.partition("/")
    lines = ["## Fact-check run", ""]
    if owner:
        lines += [f"**Site:** https://{owner.lower()}.github.io/{name}/", ""]
    lines += [f"Feed: {config.FEED_URL}", ""]
    if rows:
        lines += ["| Published | Episode | Claims checked | Claims failed | Error |", "|---|---|---|---|---|", *rows, ""]
    else:
        lines += ["No new or unfinished episodes this run.", ""]
    if failed_claims or errors:
        lines += ["Failed items are retried automatically on the next run. "
                  "Open the *Discover and check episodes* step's log for details."]
    with open(path, "a") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="factcheck")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "discover"):
        s = sub.add_parser(name)
        s.add_argument("--backfill", type=int, default=3, help="consider the newest N feed episodes")
        s.add_argument("--feed", help="feed URL or local file (overrides FEED_URL)")
    for name in ("run", "process"):
        s = sub.choices[name] if name in sub.choices else sub.add_parser(name)
        s.add_argument("--episode", help="process only this episode id")
        s.add_argument("--max-episodes", type=int, help="process at most N pending episodes this run")
    sub.add_parser("build")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    code = 0
    if args.cmd in ("run", "discover"):
        try:
            discover.discover(args.backfill, args.feed)
        except Exception as e:
            log.error("Could not read the podcast feed: %s", e)
            write_summary([f"| | | | | Feed problem: {str(e)[:300]} |"], 0, 1)
            return 1
    if args.cmd in ("run", "process"):
        code = process(args.episode, args.max_episodes)
    if args.cmd in ("run", "build"):
        site.build()
        log.info("Site written to site/")
    return code


if __name__ == "__main__":
    sys.exit(main())
