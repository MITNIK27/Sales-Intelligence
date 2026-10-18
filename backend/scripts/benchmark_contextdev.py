"""Manual benchmark: in-house scraper vs context.dev on the same companies — not part of the app,
not imported by anything. Writes nothing to the database (read-only sampling with --from-db) and
spends real context.dev credits, capped by --max-credits.

For each company both sides are measured on the same questions the pipeline cares about: did the
fetch work, is description / industry / employee range / HQ / socials filled, how many news
signals and decision-maker contacts came back, how long it took, and (context.dev only) what it
cost. Companies the scraper already failed on are prioritised in --from-db sampling on purpose:
the question is whether context.dev recovers what we currently lose, not only whether it matches
us on easy sites.

Usage (from backend/, venv active, CONTEXT_DEV_API_KEY set in .env):
    python scripts/benchmark_contextdev.py --domains acme.com globex.com
    python scripts/benchmark_contextdev.py --from-db 8 --max-credits 150

Output is a plain-text log, backend/logs/contextdev_benchmark_<timestamp>.txt: one table row is
appended per company as it finishes (so Ctrl+C loses nothing), then a summary table and a KEY
FINDINGS block are written at the end — also when interrupted.
Rough cost per company: brand 10 + up to 3 scrapes + news 1 = ~14 credits; people enrich is 20
per match and needs a paid plan (reported as plan_gated otherwise).
"""

import argparse
import asyncio
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.modules.companies.models import ENRICHMENT_STATUS_FAILED, Company
from app.modules.contacts.models import Contact
from app.modules.enrichment.providers.base import ScrapedCompanyData
from app.modules.enrichment.providers.context_dev import ContextDevProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider

logger = logging.getLogger(__name__)

_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
# brand (10) + homepage and two about/team scrapes (3) + news (1)
_CREDITS_PER_COMPANY_ESTIMATE = 14
# A hung site must not stall the whole benchmark (dhl.com did).
_SIDE_TIMEOUT_SECONDS = 75.0


@dataclass
class SideResult:
    ok: bool = False
    error: str | None = None
    description_len: int = 0
    industry: str | None = None
    employee_range: str | None = None
    hq: str | None = None
    socials: int = 0
    signals: int = 0
    contacts: int = 0
    pages: int = 0
    latency_s: float = 0.0
    credits: int = 0


@dataclass
class CompanyResult:
    domain: str
    prior_status: str | None = None
    scraper: SideResult = field(default_factory=SideResult)
    contextdev: SideResult = field(default_factory=SideResult)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains", nargs="+", default=[], help="domains to benchmark")
    parser.add_argument("--from-db", type=int, default=8, help="sample N companies from the DB")
    parser.add_argument("--max-credits", type=int, default=150)
    parser.add_argument("--people", type=int, default=5, help="max people-enrich lookups (20cr)")
    parser.add_argument("--out", type=Path, default=None, help="output .txt path (auto-named)")
    return parser.parse_args()


async def _sample_from_db(limit: int) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """(domain, enrichment_status) pairs — scraper-failed first — plus (domain, name, role)
    for contacts on those companies, for the people-enrich step."""
    async with SessionLocal() as session:
        failed = (
            await session.execute(
                select(Company.domain, Company.enrichment_status)
                .where(Company.domain.is_not(None))
                .where(Company.enrichment_status == ENRICHMENT_STATUS_FAILED)
                .limit(limit)
            )
        ).all()
        rest = (
            await session.execute(
                select(Company.domain, Company.enrichment_status)
                .where(Company.domain.is_not(None))
                .where(Company.enrichment_status != ENRICHMENT_STATUS_FAILED)
                .order_by(Company.created_at.desc())
                .limit(max(limit - len(failed), 0))
            )
        ).all()
        sample = [(d, s) for d, s in [*failed, *rest] if d]
        domains = [d for d, _ in sample]
        contacts = (
            await session.execute(
                select(Company.domain, Contact.full_name, Contact.role_title)
                .join(Contact, Contact.company_id == Company.id)
                .where(Company.domain.in_(domains), Contact.full_name.is_not(None))
            )
        ).all()
    return sample, [(d, n, r or "") for d, n, r in contacts if d and n]


def _fill(side: SideResult, data: ScrapedCompanyData) -> None:
    side.description_len = len(data.description or "")
    side.industry = data.industry
    side.employee_range = data.employee_count_range
    side.pages = len(data.pages_fetched)
    brand = data.raw_brand or {}
    address = brand.get("address")
    if isinstance(address, dict):
        parts = [address.get("city"), address.get("country")]
        side.hq = ", ".join(str(p) for p in parts if p) or None
    socials = brand.get("socials")
    side.socials = len(socials) if isinstance(socials, list) else 0


async def _measure_scraper(scraper: WebsiteScraperProvider, domain: str) -> SideResult:
    side = SideResult()
    start = time.monotonic()
    try:
        data = await scraper.fetch_company_data(domain)
        side.ok = True
        _fill(side, data)
        side.contacts = len(await scraper.fetch_contacts(domain, data.pages_fetched))
    except Exception as exc:  # noqa: BLE001 - the failure *is* the measurement
        side.error = str(exc)[:200]
    try:
        side.signals = len(await scraper.fetch_signals(domain))
    except Exception as exc:  # noqa: BLE001
        side.error = side.error or str(exc)[:200]
    side.latency_s = round(time.monotonic() - start, 2)
    return side


async def _measure_contextdev(
    contextdev: ContextDevProvider, scraper: WebsiteScraperProvider, domain: str
) -> SideResult:
    side = SideResult()
    credits_before = contextdev.credits_used
    start = time.monotonic()
    try:
        data = await contextdev.fetch_company_data(domain)
        side.ok = bool(data.raw_brand or data.pages_fetched)
        _fill(side, data)
        # Same heading-based extractor as the pipeline uses, fed context.dev's rendered HTML.
        side.contacts = len(await scraper.fetch_contacts(domain, data.pages_fetched))
    except Exception as exc:  # noqa: BLE001
        side.error = str(exc)[:200]
    side.signals = len(await contextdev.fetch_signals(domain))
    side.latency_s = round(time.monotonic() - start, 2)
    side.credits = contextdev.credits_used - credits_before
    return side


async def _guarded(coro: Awaitable[SideResult]) -> SideResult:
    try:
        return await asyncio.wait_for(coro, timeout=_SIDE_TIMEOUT_SECONDS)
    except TimeoutError:
        return SideResult(
            error=f"timed out after {_SIDE_TIMEOUT_SECONDS:.0f}s", latency_s=_SIDE_TIMEOUT_SECONDS
        )


async def _run_people(
    contextdev: ContextDevProvider, contacts: list[tuple[str, str, str]], limit: int, budget: int
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for domain, name, role in contacts[:limit]:
        if contextdev.credits_used + 20 > budget:
            results.append({"domain": domain, "name": name, "outcome": "skipped_budget"})
            continue
        try:
            found = await contextdev.enrich_person(name, domain)
        except Exception as exc:  # noqa: BLE001
            results.append({"domain": domain, "name": name, "outcome": f"error: {exc}"[:120]})
            continue
        if found == "plan_gated":
            results.append({"domain": domain, "name": name, "outcome": "plan_gated"})
        elif isinstance(found, dict):
            results.append(
                {
                    "domain": domain,
                    "name": name,
                    "known_role": role,
                    "outcome": "matched",
                    "match_score": found.get("match_score", found.get("score")),
                }
            )
        else:
            results.append({"domain": domain, "name": name, "outcome": "no_match"})
    return results


# -- log rendering (plain English, built to be read by a person) ------------------------------

_BAR = "=" * 118
# Fixed column widths so a row can be appended the moment a company finishes.
_COLS = (
    ("Company", 24),
    ("Previously", 10),
    ("Scraper", 8),
    ("context.dev", 11),
    ("Industry (context.dev)", 26),
    ("Employees", 10),
    ("News: scr vs ctx", 16),
    ("Contacts: scr vs ctx", 20),
    ("Seconds: scr vs ctx", 19),
    ("Credits", 7),
)


def _rule() -> str:
    return "+-" + "-+-".join("-" * w for _, w in _COLS) + "-+"


def _line(cells: list[str]) -> str:
    padded = (c[:w].ljust(w) for c, (_, w) in zip(cells, _COLS, strict=True))
    return "| " + " | ".join(padded) + " |"


def _head() -> str:
    return "\n".join([_rule(), _line([name for name, _ in _COLS]), _rule()])


def _worked(x: SideResult) -> str:
    return "worked" if x.ok else "FAILED"


def _row(r: CompanyResult) -> str:
    s, c = r.scraper, r.contextdev
    return _line(
        [
            r.domain,
            r.prior_status or "-",
            _worked(s),
            _worked(c),
            c.industry or s.industry or "-",
            c.employee_range or s.employee_range or "-",
            f"{s.signals} vs {c.signals}",
            f"{s.contacts} vs {c.contacts}",
            f"{s.latency_s:.0f}s vs {c.latency_s:.0f}s",
            str(c.credits),
        ]
    )


def _append(path: Path, text_: str) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text_ + "\n")


def _pct(count: int, total: int) -> str:
    return f"{count} of {total} ({round(100 * count / total)}%)" if total else "n/a"


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0.0


def _intro(count: int, max_credits: int) -> str:
    return "\n".join(
        [
            _BAR,
            f"CONTEXT.DEV vs OUR OWN SCRAPER - BENCHMARK    ({datetime.now():%d %b %Y, %H:%M})",
            f"Companies to test: {count}      Credit limit: {max_credits} "
            f"(about {_CREDITS_PER_COMPANY_ESTIMATE} credits per company)",
            _BAR,
            "HOW TO READ THIS: each row tests the same company with both tools.",
            "  Previously   = how our scraper did on this company in an earlier run (- = not run).",
            "  Scraper / context.dev = 'worked' if the tool fetched the company's information,",
            "                          'FAILED' if it could not (e.g. site blocked or timed out).",
            "  Industry, Employees   = what was found (our scraper never finds industry).",
            "  News, Contacts, Seconds are shown as  <our scraper> vs <context.dev>.",
            "  Credits      = what context.dev charged for this company.",
            "A row is added the moment each company finishes, so you can stop any time.",
            "",
            _head(),
        ]
    )


def _summary(
    results: list[CompanyResult], people: list[dict[str, Any]], credits: int, stopped_early: bool
) -> str:
    n = len(results)
    s = [r.scraper for r in results]
    c = [r.contextdev for r in results]

    def count(sides: list[SideResult], pred: Callable[[SideResult], object]) -> int:
        return sum(1 for x in sides if pred(x))

    fields: list[tuple[str, Callable[[SideResult], object]]] = [
        ("Fetched the company OK", lambda x: x.ok),
        ("Has a description", lambda x: x.description_len > 0),
        ("Industry known", lambda x: bool(x.industry)),
        ("Employee range known", lambda x: bool(x.employee_range)),
        ("HQ location known", lambda x: bool(x.hq)),
        ("Social links found", lambda x: x.socials > 0),
        ("At least 1 news/job item", lambda x: x.signals > 0),
        ("At least 1 contact found", lambda x: x.contacts > 0),
    ]
    widths = (28, 18, 18)
    rule = "+-" + "-+-".join("-" * w for w in widths) + "-+"

    def fmt(cells: tuple[str, str, str]) -> str:
        return "| " + " | ".join(x.ljust(w) for x, w in zip(cells, widths, strict=True)) + " |"

    table = [rule, fmt(("How many companies...", "Our scraper", "context.dev")), rule]
    table += [
        fmt((name, _pct(count(s, pred), n), _pct(count(c, pred), n))) for name, pred in fields
    ]
    table.append(rule)

    scraper_failed = [r for r in results if not r.scraper.ok]
    recovered = [r for r in scraper_failed if r.contextdev.ok]
    ok_c = count(c, lambda x: x.ok)
    ct_s, ct_c = count(s, lambda x: x.contacts > 0), count(c, lambda x: x.contacts > 0)
    ind_s, ind_c = count(s, lambda x: bool(x.industry)), count(c, lambda x: bool(x.industry))
    emp_s = count(s, lambda x: bool(x.employee_range))
    emp_c = count(c, lambda x: bool(x.employee_range))
    news_s, news_c = count(s, lambda x: x.signals > 0), count(c, lambda x: x.signals > 0)
    findings = [
        f"Rescue: our scraper failed on {len(scraper_failed)} of {n} companies; "
        f"context.dev managed {len(recovered)} of those.",
        f"Industry: known for {ind_c} companies with context.dev vs {ind_s} with our scraper.",
        f"Employee range: known for {emp_c} with context.dev vs {emp_s} with our scraper.",
        f"News / job items: found for {news_c} companies with context.dev vs {news_s} with ours.",
        f"Contacts: at least one found for {ct_c} companies with context.dev vs {ct_s} with ours"
        + (" - no improvement here." if ct_c <= ct_s else " - context.dev is better here."),
        f"Cost: {credits} credits used"
        + (f" (about {credits / ok_c:.0f} per successful company)" if ok_c else "")
        + f". Typical time per company: ours {_median([x.latency_s for x in s]):.0f}s, "
        f"context.dev {_median([x.latency_s for x in c]):.0f}s.",
    ]
    out = [
        "",
        _BAR,
        "SUMMARY" + ("  (stopped early: credit limit reached)" if stopped_early else ""),
        _BAR,
        f"Companies tested: {n}      Credits spent: {credits}",
        "",
        *table,
        "",
        "KEY FINDINGS",
        *(f"  - {f}" for f in findings),
    ]
    errors = [
        (r.domain, r.scraper.error, r.contextdev.error)
        for r in results
        if r.scraper.error or r.contextdev.error
    ]
    if errors:
        out += ["", "WHAT WENT WRONG (so you can see why a tool failed)"]
        out += [
            f"  {d}: scraper - {se or 'no problem'}; context.dev - {ce or 'no problem'}"
            for d, se, ce in errors
        ]
    if people:
        outcome_text = {
            "plan_gated": "not available on the free plan",
            "no_match": "no match found",
            "matched": "match found",
            "skipped_budget": "skipped (credit limit)",
        }
        out += ["", "PEOPLE LOOKUP (looks up a known contact; 20 credits per match)"]
        out += [
            f"  {p['name']} at {p['domain']}: {outcome_text.get(p['outcome'], p['outcome'])}"
            + (f" (match score {p['match_score']})" if p.get("match_score") is not None else "")
            for p in people
        ]
    out.append("")
    return "\n".join(out)


async def _main() -> int:
    configure_logging()
    args = _parse_args()
    settings = get_settings()
    if not settings.context_dev_api_key:
        print("Missing CONTEXT_DEV_API_KEY - check backend/.env")
        return 1

    sample: list[tuple[str, str | None]] = [(d, None) for d in args.domains]
    contacts: list[tuple[str, str, str]] = []
    if args.from_db:
        db_sample, contacts = await _sample_from_db(args.from_db)
        seen = {d for d, _ in sample}
        sample += [(d, s) for d, s in db_sample if d not in seen]
    if not sample:
        print("Nothing to benchmark - pass --domains and/or --from-db N (is the DB empty?)")
        return 1

    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    log_path: Path = args.out or _LOG_DIR / f"contextdev_benchmark_{stamp}.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _append(log_path, _intro(len(sample), args.max_credits))

    scraper = WebsiteScraperProvider(settings)
    contextdev = ContextDevProvider(settings)
    results: list[CompanyResult] = []
    people: list[dict[str, Any]] = []
    stopped_early = False
    try:
        for domain, status in sample:
            if contextdev.credits_used + _CREDITS_PER_COMPANY_ESTIMATE > args.max_credits:
                stopped_early = True
                break
            print(f"[{len(results) + 1}/{len(sample)}] {domain}")
            result = CompanyResult(domain=domain, prior_status=status)
            result.scraper = await _guarded(_measure_scraper(scraper, domain))
            result.contextdev = await _guarded(_measure_contextdev(contextdev, scraper, domain))
            results.append(result)
            _append(log_path, _row(result))  # on disk immediately: Ctrl+C loses nothing
        if args.people:
            people = await _run_people(contextdev, contacts, args.people, args.max_credits)
    finally:
        await scraper.aclose()
        _append(log_path, _rule())
        _append(log_path, _summary(results, people, contextdev.credits_used, stopped_early))
        print(f"\nLog: {log_path} ({contextdev.credits_used} credits)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.exit(asyncio.run(_main()))
