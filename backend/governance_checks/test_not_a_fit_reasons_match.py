"""G4: the reasons a person can give for marking a company "not a fit" are one list. The backend
validates against NOT_A_FIT_REASONS and the screen offers the same values, so a reason added in
only one place would either be refused by the server or never offered. This keeps them identical."""

import re
from pathlib import Path

import pytest

from app.modules.companies.service import MAX_NOTE_CHARS
from app.modules.review.service import NOT_A_FIT_REASONS

REASONS_TS = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "features"
    / "companies"
    / "notAFit"
    / "reasons.ts"
)


def _frontend_source() -> str:
    if not REASONS_TS.exists():
        pytest.skip("the frontend is not part of this checkout")
    return REASONS_TS.read_text(encoding="utf-8")


def test_the_screen_offers_exactly_the_reasons_the_server_accepts() -> None:
    offered = re.findall(r'value:\s*"([a-z_]+)"', _frontend_source())
    assert offered == list(NOT_A_FIT_REASONS), (
        "frontend/src/features/companies/notAFit/reasons.ts and NOT_A_FIT_REASONS in "
        "backend/app/modules/review/service.py must list the same reasons in the same order "
        "(docs/ai-governance.md, G4)."
    )


def test_the_screen_and_the_server_agree_on_the_longest_note() -> None:
    found = re.search(r"NOTE_MAX_CHARS\s*=\s*(\d+)", _frontend_source())
    assert found is not None and int(found.group(1)) == MAX_NOTE_CHARS
