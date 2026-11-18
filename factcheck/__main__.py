"""CLI.

  python -m factcheck run [--backfill N] [--episode ID]   discover + process + build
  python -m factcheck discover --backfill N
  python -m factcheck process [--episode ID]              transcribe/extract/verify pending episodes
  python -m factcheck build                               regenerate site/
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import discover, extract, site, storage, transcribe, verify

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
    errors = 0
    for rec in pending:
        try:
            process_episode(rec)
        except Exception:
            errors += 1
            log.exception("Episode failed: %s", rec.episode.id)
    return 1 if errors and errors == len(pending) else 0


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
        discover.discover(args.backfill, args.feed)
    if args.cmd in ("run", "process"):
        code = process(args.episode, args.max_episodes)
    if args.cmd in ("run", "build"):
        site.build()
        log.info("Site written to site/")
    return code


if __name__ == "__main__":
    sys.exit(main())
