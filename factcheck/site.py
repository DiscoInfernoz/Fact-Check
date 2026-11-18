"""Render the static website from data/episodes/*.json."""
from __future__ import annotations

import shutil
from collections import Counter
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader

from . import config, storage
from .extract import fmt_time
from .schemas import VERDICT_ORDER

VERDICT_CLASS = {
    "Accurate": "v-accurate", "Mostly accurate": "v-mostly", "Missing context": "v-context",
    "Disputed": "v-disputed", "Misleading": "v-misleading", "Unsupported": "v-unsupported", "False": "v-false",
}
CATEGORY_LABEL = {
    "history": "History", "science_health": "Science & health", "law_courts": "Law & courts",
    "statistics": "Statistics", "current_events": "Current events", "quote_attribution": "Quotes",
    "biography": "Biography", "economics": "Economics", "other": "Other",
}


def _counts(rec) -> list[tuple[str, int]]:
    c = Counter(cl.verification.verdict for cl in rec.claims if cl.verification)
    return [(v, c[v]) for v in VERDICT_ORDER if c[v]]


def build(out_dir=None) -> None:
    out = out_dir or config.SITE_DIR
    if out.exists():
        shutil.rmtree(out)
    (out / "episodes").mkdir(parents=True)
    shutil.copytree(config.STATIC_DIR, out / "static")

    env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR), autoescape=True)
    env.filters["ts"] = fmt_time
    env.filters["domain"] = lambda u: urlparse(u).netloc.removeprefix("www.")
    env.globals.update(
        site_title=config.SITE_TITLE, show_name=config.SHOW_NAME, verdict_class=VERDICT_CLASS,
        verdict_order=VERDICT_ORDER, category_label=CATEGORY_LABEL, corrections_url=config.CORRECTIONS_URL,
    )

    records = [r for r in storage.all_records() if any(c.verification for c in r.claims)]
    total = Counter(c.verification.verdict for r in records for c in r.claims if c.verification)
    episodes = [{"rec": r, "counts": _counts(r), "checked": sum(n for _, n in _counts(r))} for r in records]

    def render(tpl, path, depth, **ctx):
        html = env.get_template(tpl).render(root="../" * depth, **ctx)
        (out / path).write_text(html)

    render("index.html.j2", "index.html", 0, episodes=episodes,
           totals=[(v, total[v]) for v in VERDICT_ORDER if total[v]], total_claims=sum(total.values()),
           updated=max((r.updated_at for r in records), default="")[:10])
    render("methodology.html.j2", "methodology.html", 0, model=config.MODEL)
    for e in episodes:
        r = e["rec"]
        claims = [c for c in r.claims if c.verification]
        render("episode.html.j2", f"episodes/{r.episode.id}.html", 1, ep=r.episode, counts=e["counts"],
               claims=claims, speakers=sorted({c.speaker_name for c in claims}),
               categories=sorted({c.category for c in claims}), pending=len(r.claims) - len(claims))
