"""Read-only report of what the tool has spent: calls, tokens, search queries and context.dev
credits, grouped by provider and task, with an estimated cost. Changes nothing.

Costs are estimates from published prices (see app/modules/usage/pricing.py); free tiers cost
nothing but are shown at their paid-equivalent so the budget is visible before it is needed.

Usage (from backend/, venv active):
    python scripts/usage_report.py             # last 7 days
    python scripts/usage_report.py --days 30
    python scripts/usage_report.py --review    # also compare with the plan's estimates
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from app.db import models as _models  # noqa: F401 - registers all models with SQLAlchemy
from app.db.session import SessionLocal
from app.modules.usage.service import cost_per_company, error_breakdown, summarize_usage

# What the plan estimated, for the review. Measured figures should land in the same range; a
# much higher one means a step is doing more than expected (retries, repeated judging).
PLAN_ESTIMATES = [
    ("researching one area (collect, assess)", "$0.02 to $0.04 per area"),
    ("judging offering fit for one company", "about $0.005"),
    ("a full Quick Check brief", "$0.03 to $0.05"),
    ("everything for one company, if all paid", "about $0.02 to $0.05"),
]


async def main(days: int, review: bool) -> None:
    since = datetime.now(UTC) - timedelta(days=days)
    async with SessionLocal() as session:
        lines = await summarize_usage(session, since)
        failures = await error_breakdown(session, since)
        per_company = await cost_per_company(session, since) if review else None
    if not lines:
        print(f"No usage recorded in the last {days} days.")
        return
    print(f"Usage in the last {days} days (estimated cost, not a bill)\n")
    print(f"{'provider':<11}{'task':<22}{'calls':>6}{'errors':>7}{'tok in':>10}{'tok out':>9}"
          f"{'cached':>8}{'think':>8}{'units':>7}{'est $':>9}")
    for line in lines:
        print(f"{line.provider:<11}{line.task:<22}{line.calls:>6}{line.errors:>7}"
              f"{line.tokens_in:>10}{line.tokens_out:>9}{line.cached_tokens:>8}"
              f"{line.thinking_tokens:>8}{line.units:>7}{line.est_cost_usd:>9.4f}")
    print(f"\nTotal estimated: ${sum(line.est_cost_usd for line in lines):.4f}")
    if failures:
        print("\nFailed calls by reason")
        for failure in failures:
            print(f"  {failure.count:>4}  {failure.provider:<8} {failure.error}")
    if per_company is not None:
        _print_review(lines, per_company)


def _print_review(lines, per_company) -> None:
    print("\nCost review")
    print(f"  companies researched: {per_company.companies}")
    print(f"  average per company:  ${per_company.average_est_cost_usd:.4f}")
    for company_id, cost in per_company.most_expensive:
        print(f"    most expensive: {company_id}  ${cost:.4f}")
    calls = sum(line.calls for line in lines)
    errors = sum(line.errors for line in lines)
    rate = f"{100 * errors / calls:.1f}%" if calls else "n/a"
    print(f"  failed calls: {errors} of {calls} ({rate}); free-tier throttling shows up here")
    for line in sorted(lines, key=lambda x: -x.est_cost_usd)[:3]:
        print(f"  top cost: {line.provider}/{line.task} ${line.est_cost_usd:.4f}")
    print("  the plan estimated:")
    for what, estimate in PLAN_ESTIMATES:
        print(f"    {what}: {estimate}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--review", action="store_true", help="compare with the plan's estimates")
    args = parser.parse_args()
    asyncio.run(main(args.days, args.review))
