"""Manual tool: delete the companies first saved BEFORE a date, with everything that hangs off
them, and keep newer companies untouched. Not part of the app, not imported by anything.

"Discovered" is `companies.created_at`, compared in UTC: `--before 2026-10-25` removes companies
created before 2026-10-25 00:00 UTC (any status, including "not a fit" and confirmed ones).

What goes: the selected companies and every row that depends on them, found from the database's
own foreign keys (contacts, drafts, outreach, enrichment, opportunities and so on), so a table
added later is not missed. What stays: everything else, in particular the InfoBeans setup
(offerings, criteria, role categories), jobs and ingestion runs, the cost log (`api_usage`) and the
decision log (`review_decisions`). Those last two hold a company id with no foreign key, so they
survive with an id that no longer points anywhere; that is intended (labels and spend history).

Dry run by default: prints, per table, how many rows would go and where the cut falls. A real
delete needs --yes AND typing the number of companies. Stop the job worker first.

Usage (from backend/, venv active):
    python scripts/delete_companies_before.py --before 2026-10-25          # dry run
    python scripts/delete_companies_before.py --before 2026-10-25 --yes    # asks, then deletes
"""

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime

from sqlalchemy import Table, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.logging import configure_logging
from app.db import models as _models  # noqa: F401 - registers every table on the metadata
from app.db.base import Base
from app.db.session import SessionLocal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--before",
        required=True,
        type=date.fromisoformat,
        help="delete companies created before this date (YYYY-MM-DD, UTC)",
    )
    parser.add_argument(
        "--yes", action="store_true", help="actually delete (still asks to confirm)"
    )
    return parser.parse_args()


def dependants(root: str) -> list[Table]:
    """Tables that depend on `root` through foreign keys, parents before children (so the reverse
    order is safe to delete in)."""
    reachable = {root}
    changed = True
    while changed:
        changed = False
        for table in Base.metadata.sorted_tables:
            if table.name in reachable:
                continue
            if any(fk.column.table.name in reachable for fk in table.foreign_keys):
                reachable.add(table.name)
                changed = True
    return [table for table in Base.metadata.sorted_tables if table.name in reachable]


def doomed_rows(
    table: Table, root: str, root_condition: ColumnElement[bool]
) -> ColumnElement[bool]:
    """The rows of `table` that depend, directly or through other tables, on the selected roots."""
    if table.name == root:
        return root_condition
    conditions = []
    for fk in table.foreign_keys:
        parent = fk.column.table
        if parent.name == root or any(t.name == parent.name for t in dependants(root)):
            parent_pk = fk.column
            conditions.append(
                table.c[fk.parent.name].in_(
                    select(parent_pk).where(doomed_rows(parent, root, root_condition))
                )
            )
    if not conditions:
        raise ValueError(f"{table.name} does not depend on {root}")
    return or_(*conditions)


async def _active_jobs(session: AsyncSession) -> int:
    result = await session.execute(
        text("SELECT count(*) FROM jobs WHERE status IN ('pending', 'running')")
    )
    count: int = result.scalar_one()
    return count


async def _main() -> int:
    configure_logging()
    args = _parse_args()
    cutoff = datetime(args.before.year, args.before.month, args.before.day, tzinfo=UTC)
    companies = Base.metadata.tables["companies"]
    condition = companies.c.created_at < cutoff
    tables = dependants("companies")

    async with SessionLocal() as session:
        total = (await session.execute(select(func.count()).select_from(companies))).scalar_one()
        doomed = (
            await session.execute(select(func.count()).select_from(companies).where(condition))
        ).scalar_one()
        newest_doomed, oldest_kept = (
            await session.execute(
                select(
                    func.max(companies.c.created_at).filter(condition),
                    func.min(companies.c.created_at).filter(~condition),
                )
            )
        ).one()
        print(f"Cut line: created before {cutoff.isoformat()}")
        print(f"Companies: {total} in all, {doomed} to delete, {total - doomed} kept")
        print(f"  newest company deleted: {newest_doomed}")
        print(f"  oldest company kept:    {oldest_kept}")
        print("\nRows that would be deleted (children first):" if not args.yes else "\nDeleting:")
        counts: dict[str, int] = {}
        for table in reversed(tables):
            counts[table.name] = (
                await session.execute(
                    select(func.count())
                    .select_from(table)
                    .where(doomed_rows(table, "companies", condition))
                )
            ).scalar_one()
            print(f"  {table.name:<34}{counts[table.name]:>8}")

        active = await _active_jobs(session)
        if active:
            print(f"\nWARNING: {active} job(s) are pending/running. Stop the worker first.")
        if not args.yes:
            print("\nDry run only. Re-run with --yes to delete.")
            return 0
        if doomed == 0:
            print("\nNothing to delete.")
            return 0
        if input(
            f"\nType {doomed} to delete these {doomed} companies and their rows: "
        ).strip() != str(doomed):
            print("Aborted, nothing changed.")
            return 1
        for table in reversed(tables):
            await session.execute(delete(table).where(doomed_rows(table, "companies", condition)))
        await session.commit()

    async with SessionLocal() as session:
        left = (await session.execute(select(func.count()).select_from(companies))).scalar_one()
    print(f"\nDone. {left} companies remain.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.exit(asyncio.run(_main()))
