"""Manual debug tool for the Company Discovery Agent (Phase A1) — not part of the app, not
imported by anything. Runs `CompanyDiscoveryAgent.discover()` directly against real APIs (no
Postgres, no job worker, no frontend needed) so extraction/resolution quality can be eyeballed
quickly, whenever there's a reason to (a bad-looking run, a prompt change, etc.) — see the
"Manual end-to-end verification" section of the Phase A1 plan.

Usage (from backend/, with GEMINI_API_KEY and SERPER_API_KEY set in .env):
    .venv/Scripts/python.exe scripts/verify_discovery_agent.py
    .venv/Scripts/python.exe scripts/verify_discovery_agent.py \\
        --industry SaaS fintech --location Bangalore --size 50-200
"""

import argparse
import asyncio
import logging
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules.discovery_agent.agent import DiscoveryAgentError, get_default_discovery_agent
from app.modules.discovery_agent.schemas import MarketCriteria

logger = logging.getLogger(__name__)

# Same criteria used live in the meeting this fix is verifying against.
_DEFAULT_INDUSTRY = ["postal", "parcel"]
_DEFAULT_LOCATION = "Europe"
_DEFAULT_SIZE = "1000-1500"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--industry", nargs="+", default=_DEFAULT_INDUSTRY)
    parser.add_argument("--location", default=_DEFAULT_LOCATION)
    parser.add_argument("--size", default=_DEFAULT_SIZE)
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


async def _main() -> int:
    configure_logging()
    args = _parse_args()
    settings = get_settings()

    required_settings = [
        ("GEMINI_API_KEY", settings.gemini_api_key),
        ("SERPER_API_KEY", settings.serper_api_key),
    ]
    missing = [name for name, value in required_settings if not value]
    if missing:
        print(f"Missing required settings: {', '.join(missing)} — check backend/.env")
        return 1

    criteria = MarketCriteria(
        industry_keywords=args.industry, location=args.location, employee_size_range=args.size
    )
    print(f"Discovering companies for: {criteria}\n")

    agent = get_default_discovery_agent(settings)
    try:
        result = await agent.discover(criteria, limit=args.limit)
    except DiscoveryAgentError as exc:
        print(f"DISCOVERY FAILED: {exc}")
        return 1

    print(
        f"Stage counts: raw_results={result.raw_results_count} "
        f"extracted={result.extracted_count} accepted={result.accepted_count} "
        f"resolved={result.resolved_count}\n"
    )

    print(f"=== Accepted companies ({len(result.companies)}) ===")
    for company in result.companies:
        print(f"  - {company.name}  ({company.domain})")
        print(f"      source: {company.source_snippet!r}")

    print(f"\n=== Rejected extractions ({len(result.rejected)}) ===")
    for rejected in result.rejected:
        print(
            f"  - {rejected.name!r}  grounded={rejected.grounded_in_source} "
            f"matches_criteria={rejected.matches_criteria}"
        )
        print(f"      reasoning: {rejected.reasoning}")

    if not result.companies:
        print("\nNo companies returned — see rejected list above and raw_results/extracted "
              "counts to diagnose which stage lost everything.")

    return 0


if __name__ == "__main__":
    # Search snippets/company names can contain non-ASCII characters (accents, diacritics); the
    # default Windows console codepage (cp1252) can't encode all of them, so force UTF-8 stdout
    # rather than crash mid-report on an otherwise-successful run.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.exit(asyncio.run(_main()))
