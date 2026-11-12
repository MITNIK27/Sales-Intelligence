"""G9: every row an AI writes records which model and which prompt version wrote it, so a bad
answer can be traced and a prompt change can be told apart from a model change.

TODO: import your AI-written models and list them in AI_TABLES. Add a table here when you create
one. KNOWN_GAPS starts empty; a table that cannot have the columns yet goes there with a reason."""

from sqlalchemy.orm import DeclarativeBase

REQUIRED = {"model_used", "prompt_version"}

AI_TABLES: list[type[DeclarativeBase]] = []  # TODO: [Draft, Recommendation, Verdict, ...]
KNOWN_GAPS: dict[str, set[str]] = {}  # {"ClassName": {"missing", "columns"}}


def _missing(model: type[DeclarativeBase]) -> set[str]:
    return REQUIRED - {column.name for column in model.__table__.columns}


def test_ai_tables_record_model_and_prompt_except_known_gaps() -> None:
    actual = {m.__name__: _missing(m) for m in AI_TABLES if _missing(m)}
    assert actual == KNOWN_GAPS, (
        f"AI-written tables must record model_used and prompt_version (G9). Missing now: {actual}. "
        f"Known gaps: {KNOWN_GAPS}. Fix the table, or remove a fixed one from KNOWN_GAPS."
    )
