"""Turns offering proposals a person already approved into eval cases, so past reviews become
labels at no extra cost. Read-only: it only reads the database and writes a file.

An approved proposal means a person agreed the page IS an offering, so the case expects the model
to say so, with the approved kind and a name that starts the same way. A rejected proposal is
skipped on purpose: it does not say why (not an offering, or a wrong name or description), so it
cannot be a reliable label.

Only the saved excerpt of each page (its first ~600 characters) is available, not the whole page,
so the case is a fair test of the start of a page, which is what the model weighs most.

Dry run by default. Usage (from backend/, venv active):
    python -m evals.export_offering_cases              # shows what would be written
    python -m evals.export_offering_cases --yes        # writes evals/cases/offering_approved.jsonl
    python -m evals.export_offering_cases --yes --limit 60

Look at the file before committing it: it contains text from the website pages."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from evals.cases import CASES_DIR

OUT_FILE = CASES_DIR / "offering_approved.jsonl"


def case_from_proposal(
    proposal_id: str, name: str, kind: str, url: str, excerpt: str
) -> dict[str, Any]:
    """One eval case from one approved proposal. Pure, so it can be tested without a database."""
    words = name.split()
    return {
        "id": f"offering-approved-{proposal_id[:8]}",
        "task": "offering_extraction",
        "tags": ["accuracy"],
        "input": {"url": url, "text": excerpt},
        "expect": {"is_offering": True, "kind": kind, "name_contains": " ".join(words[:2])},
        "note": "Approved by a person; the text is only the saved excerpt of the page.",
    }


async def main(write: bool, limit: int) -> None:
    from sqlalchemy import select

    from app.db import models as _models  # noqa: F401 - registers all models with SQLAlchemy
    from app.db.session import SessionLocal
    from app.modules.offerings.models import PROPOSAL_APPROVED, PROPOSAL_REJECTED, OfferingProposal

    async with SessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(OfferingProposal)
                    .where(
                        OfferingProposal.status == PROPOSAL_APPROVED,
                        OfferingProposal.source_excerpt.is_not(None),
                    )
                    .order_by(OfferingProposal.decided_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        rejected = len(
            (
                await session.execute(
                    select(OfferingProposal.id).where(OfferingProposal.status == PROPOSAL_REJECTED)
                )
            ).all()
        )
    cases = [
        case_from_proposal(
            str(p.id), p.name, p.kind, p.source_url, p.source_excerpt or ""
        )
        for p in rows
    ]
    print(f"{len(cases)} approved proposal(s) with a saved excerpt; {rejected} rejected skipped.")
    if not cases:
        return
    for case in cases[:5]:
        print(f"  {case['id']}: {case['expect']['name_contains']} ({case['expect']['kind']})")
    if not write:
        print(f"\nDry run: nothing written. Run again with --yes to write {OUT_FILE.name}.")
        return
    OUT_FILE.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {len(cases)} case(s) to {Path(OUT_FILE)}. Review it before committing.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="write the file")
    parser.add_argument("--limit", type=int, default=40, help="newest N approvals (default 40)")
    args = parser.parse_args()
    asyncio.run(main(args.yes, args.limit))
