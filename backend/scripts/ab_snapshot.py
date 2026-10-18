"""Manual tool: save the current database state to a plain-text results file, so two pipeline runs
can be compared side by side — not part of the app, not imported by anything. Strictly read-only.

Why it exists: wiping the database destroys a run's results, so each run is written to a text
file (tables inside, written in plain English) first. `reset_test_data.py` does this
automatically before a wipe.

The run label defaults to the current COMPANY_DATA_SOURCE setting ("scraper" or
"scraper_with_contextdev_fallback"), so a run is labelled by how it was actually configured.
Once both of those runs are saved, the comparison is printed automatically.

Usage (from backend/, venv active):
    python scripts/ab_snapshot.py                 # save the current DB state (+ compare if both)
    python scripts/ab_snapshot.py --compare       # just re-print the comparison

Output file: backend/logs/ab_runs.txt (open it in any editor).
"""

import argparse
import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.modules.companies.models import ENRICHMENT_STATUS_ENRICHED, Company
from app.modules.contacts.models import Contact
from app.modules.draft.models import DRAFT_STATUS_DISCARDED, Draft
from app.modules.enrichment.models import ENTITY_TYPE_COMPANY, EnrichmentRecord
from app.modules.qualification.models import QualificationResult

LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "ab_runs.txt"
COMPARE_A = "scraper"
COMPARE_B = "scraper_with_contextdev_fallback"
_FRIENDLY = {COMPARE_A: "Scraper only", COMPARE_B: "With context.dev"}

_BAR = "=" * 100
_RUN_START = re.compile(r"^RUN SAVED: (?P<label>\S+)")
_RUN_END = "=== END OF RUN ==="
# "  Industry known .......... 12" -> label + value, parsed back for the comparison.
_TOTAL_LINE = re.compile(r"^  (?P<label>.+?) \.{2,} (?P<val>-?\d+)$")

# (key, plain-English label, which direction is "better" for the rep: up / down / neither)
METRICS: list[tuple[str, str, str | None]] = [
    ("companies", "Companies found", None),
    ("enriched", "Companies enriched OK", "up"),
    ("failed", "Companies that FAILED to enrich", "down"),
    ("data_from_contextdev", "Companies whose data came from context.dev", None),
    ("description_filled", "Companies with a description", "up"),
    ("industry_filled", "Companies with industry known", "up"),
    ("employees_filled", "Companies with employee range known", "up"),
    ("signals", "News / job items collected", "up"),
    ("contacts", "Contacts found (total)", "up"),
    ("companies_with_contact", "Companies with at least 1 contact", "up"),
    ("qualified", "Companies judged Qualified", None),
    ("not_qualified", "Companies judged Not qualified", None),
    ("could_not_determine", "Companies that could not be verified", None),
    ("needs_review", "Companies flagged Needs review", None),
    ("drafts", "Outreach drafts ready", "up"),
    ("contextdev_brand_lookups", "context.dev company lookups (about 10 credits each)", None),
]
_LABEL_TO_KEY = {label: key for key, label, _ in METRICS}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", help="run name (default: current COMPANY_DATA_SOURCE)")
    parser.add_argument(
        "--compare",
        nargs="*",
        metavar="LABEL",
        help=f"compare two saved runs (default: {COMPARE_A} vs {COMPARE_B}); saves nothing",
    )
    return parser.parse_args()


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [
        max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
        for i, h in enumerate(headers)
    ]

    def fmt(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)) + " |"

    rule = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    return "\n".join([rule, fmt(headers), rule, *(fmt(r) for r in rows), rule])


def _verdict_text(verdict: str) -> str:
    return {
        "qualified": "Qualified",
        "not_qualified": "Not qualified",
        "could_not_determine": "Could not verify",
    }.get(verdict, "Not judged")


async def _collect() -> tuple[list[list[str]], dict[str, int]]:
    async with SessionLocal() as session:
        companies = list((await session.execute(select(Company).order_by(Company.name))).scalars())
        verdicts: dict[object, str] = {}
        for q in (
            await session.execute(
                select(QualificationResult).order_by(QualificationResult.created_at.asc())
            )
        ).scalars():
            verdicts[q.company_id] = q.overall_verdict
        contact_counts: dict[object, int] = {
            cid: n
            for cid, n in (
                await session.execute(
                    select(Contact.company_id, func.count()).group_by(Contact.company_id)
                )
            ).all()
        }
        draft_counts: dict[object, int] = {
            cid: n
            for cid, n in (
                await session.execute(
                    select(Draft.company_id, func.count())
                    .where(Draft.status != DRAFT_STATUS_DISCARDED)
                    .group_by(Draft.company_id)
                )
            ).all()
        }
        sources: dict[object, set[str]] = {}
        signal_counts: dict[object, int] = {}
        brand_lookups = 0
        for entity_id, source in (
            await session.execute(
                select(EnrichmentRecord.entity_id, EnrichmentRecord.source).where(
                    EnrichmentRecord.entity_type == ENTITY_TYPE_COMPANY
                )
            )
        ).all():
            sources.setdefault(entity_id, set()).add(source)
            if ":signals:" in source:
                signal_counts[entity_id] = signal_counts.get(entity_id, 0) + 1
            if source.startswith("contextdev:brand"):
                brand_lookups += 1

    rows: list[list[str]] = []
    totals = {key: 0 for key, _, _ in METRICS}
    totals["companies"] = len(companies)
    totals["contextdev_brand_lookups"] = brand_lookups
    for c in companies:
        srcs = sources.get(c.id, set())
        origin = (
            "context.dev"
            if any(s.startswith("contextdev:") for s in srcs)
            else "our scraper"
            if srcs
            else "nothing"
        )
        verdict = verdicts.get(c.id, "")
        n_contacts = contact_counts.get(c.id, 0)
        n_signals = signal_counts.get(c.id, 0)
        n_drafts = draft_counts.get(c.id, 0)
        failed = c.enrichment_status == "failed"
        rows.append(
            [
                c.name[:34],
                "FAILED" if failed else "OK" if c.enrichment_status == "enriched" else "not done",
                origin,
                c.industry or "-",
                c.employee_count_range or "-",
                str(n_signals),
                str(n_contacts),
                _verdict_text(verdict),
                str(n_drafts),
            ]
        )
        totals["enriched"] += c.enrichment_status == ENRICHMENT_STATUS_ENRICHED
        totals["failed"] += failed
        totals["data_from_contextdev"] += origin == "context.dev"
        totals["industry_filled"] += bool(c.industry)
        totals["employees_filled"] += bool(c.employee_count_range)
        totals["description_filled"] += bool(c.description)
        totals["contacts"] += n_contacts
        totals["companies_with_contact"] += n_contacts > 0
        totals["signals"] += n_signals
        totals["qualified"] += verdict == "qualified"
        totals["not_qualified"] += verdict == "not_qualified"
        totals["could_not_determine"] += verdict == "could_not_determine"
        totals["needs_review"] += bool(c.needs_review)
        totals["drafts"] += n_drafts
    return rows, totals


def _render_run(label: str, rows: list[list[str]], totals: dict[str, int]) -> str:
    headers = [
        "Company", "Enrichment", "Data came from", "Industry", "Employees",
        "News items", "Contacts", "Verdict", "Drafts",
    ]
    width = max(len(label_) for _, label_, _ in METRICS) + 2
    totals_lines = [
        f"  {text} {'.' * (width - len(text))} {totals[key]}" for key, text, _ in METRICS
    ]
    return "\n".join(
        [
            _BAR,
            f"RUN SAVED: {label}    ({datetime.now():%d %b %Y, %H:%M})",
            f"Setting when saved: COMPANY_DATA_SOURCE = {get_settings().company_data_source}",
            _BAR,
            "HOW TO READ THIS: one row per company found in this run.",
            "  Enrichment     = did we manage to build a profile for the company (OK / FAILED).",
            "  Data came from = which source filled the profile: 'our scraper' or 'context.dev'.",
            "  News items     = news / job-posting items collected as buying signals.",
            "  Verdict        = Qualified / Not qualified / Could not verify (from your criteria).",
            "  Drafts         = outreach emails written and waiting for review.",
            "",
            _table(headers, rows),
            "",
            "TOTALS FOR THIS RUN",
            *totals_lines,
            _RUN_END,
            "",
        ]
    )


def _latest_totals(label: str) -> dict[str, int] | None:
    if not LOG_PATH.exists():
        return None
    found: dict[str, int] | None = None
    current: dict[str, int] | None = None
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        start = _RUN_START.match(line)
        if start:
            current = {} if start["label"] == label else None
        elif line == _RUN_END:
            if current is not None:
                found = current
            current = None
        elif current is not None and (m := _TOTAL_LINE.match(line)):
            key = _LABEL_TO_KEY.get(m["label"])
            if key:
                current[key] = int(m["val"])
    return found


def _name(label: str) -> str:
    return _FRIENDLY.get(label, label)


def _render_comparison(a: str, b: str) -> str:
    ta, tb = _latest_totals(a), _latest_totals(b)
    if ta is None or tb is None:
        missing = a if ta is None else b
        return f"(Comparison skipped: no saved run labelled '{missing}' yet.)\n"

    rows: list[list[str]] = []
    better_b = better_a = same = 0
    for key, text, direction in METRICS:
        va, vb = ta.get(key, 0), tb.get(key, 0)
        change = f"{vb - va:+d}" if vb != va else "no change"
        verdict = ""
        if direction is not None:
            if va == vb:
                verdict, same = "same", same + 1
            elif (vb > va) == (direction == "up"):
                verdict, better_b = _name(b), better_b + 1
            else:
                verdict, better_a = _name(a), better_a + 1
        rows.append([text, str(va), str(vb), change, verdict])

    def sentence(label: str, key: str, per: str = "") -> str:
        return f"{label}: {ta[key]} with {_name(a)} vs {tb[key]} with {_name(b)}{per}."

    n = max(ta["companies"], 1), max(tb["companies"], 1)
    findings = [
        sentence("Companies that failed to enrich (fewer is better)", "failed"),
        sentence("Companies with industry known", "industry_filled", f" (out of {n[0]} / {n[1]})"),
        sentence(
            "Companies with employee range known", "employees_filled", f" (out of {n[0]} / {n[1]})"
        ),
        sentence("News / job items collected", "signals"),
        sentence("Companies with at least one contact", "companies_with_contact"),
        sentence("Outreach drafts ready", "drafts"),
        sentence("Companies judged Qualified", "qualified")
        + " (this depends on your criteria, not on data quality)",
        f"context.dev company lookups used: {tb['contextdev_brand_lookups']} "
        f"(roughly {tb['contextdev_brand_lookups'] * 10} credits, plus a few for pages and news).",
    ]
    total = better_a + better_b + same
    bottom = (
        f"OVERALL: of {total} data-quality measures, {_name(b)} was better on {better_b}, "
        f"{_name(a)} was better on {better_a}, and {same} were the same."
    )
    return "\n".join(
        [
            _BAR,
            f"COMPARISON: {_name(a)}  vs  {_name(b)}",
            "(Only fair if both runs used the SAME prompt on a freshly wiped database.)",
            _BAR,
            "",
            _table(
                ["What we measured", _name(a), _name(b), "Change", "Better is"],
                rows,
            ),
            "",
            "KEY FINDINGS",
            *(f"  - {f}" for f in findings),
            "",
            bottom,
            "",
        ]
    )


async def snapshot(label: str) -> str:
    """Save the current DB state under `label` and return the rendered block. Used by
    `reset_test_data.py` too, so a wipe can never lose a run's results."""
    rows, totals = await _collect()
    block = _render_run(label, rows, totals)
    _append(block)
    return block


def _append(text: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")


async def _main() -> int:
    configure_logging()
    args = _parse_args()
    out = ""
    if args.compare is None:  # plain snapshot (optionally with --label)
        label = args.label or get_settings().company_data_source
        out += await snapshot(label)
        # Show the comparison as soon as both configurations have been saved.
        if label in (COMPARE_A, COMPARE_B) and all(
            _latest_totals(x) is not None for x in (COMPARE_A, COMPARE_B)
        ):
            comparison = _render_comparison(COMPARE_A, COMPARE_B)
            _append(comparison)
            out += comparison
    else:
        a, b = (list(args.compare) + [COMPARE_A, COMPARE_B])[:2]
        comparison = _render_comparison(a, b)
        _append(comparison)
        out += comparison
    print(out)
    print(f"(saved in {LOG_PATH})")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.exit(asyncio.run(_main()))
