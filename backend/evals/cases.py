"""Eval cases: one JSON object per line in `evals/cases/*.jsonl`.

A case is a frozen input plus what a good answer must (or must not) do. Inputs are frozen so a
failure means the model or the prompt changed, not that the web did. See evals/README.md."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CASES_DIR = Path(__file__).resolve().parent / "cases"

# Add a task here when its runner lands (evals/tasks.py).
KNOWN_TASKS = (
    "quicklook",
    "qualification",
    "draft",
    "offering_extraction",
    "recommendation",
    "opportunity_assessment",
    "offering_fit",
    "contact_relevance",
    "role_relevance",
)

# injection: hostile text in the input must not steer the answer.
# grounding: the answer may only claim what the input supports.
# accuracy: the answer is compared with a label a person decided.
KNOWN_TAGS = ("injection", "grounding", "accuracy")

_KEYS = {"id", "task", "tags", "input", "expect", "note"}


class CaseError(ValueError):
    """A case file is malformed. The message names the file and line."""


@dataclass(frozen=True)
class Case:
    id: str
    task: str
    tags: tuple[str, ...]
    input: dict[str, Any]
    expect: dict[str, Any]
    note: str = field(default="")


def _parse(raw: dict[str, Any], where: str) -> Case:
    extra = set(raw) - _KEYS
    if extra:
        raise CaseError(f"{where}: unknown key(s) {sorted(extra)} (allowed: {sorted(_KEYS)})")
    for key in ("id", "task", "tags", "input", "expect"):
        if key not in raw:
            raise CaseError(f"{where}: missing '{key}'")
    if not isinstance(raw["id"], str) or not raw["id"].strip():
        raise CaseError(f"{where}: 'id' must be a non-empty string")
    if raw["task"] not in KNOWN_TASKS:
        raise CaseError(f"{where}: unknown task {raw['task']!r} (known: {list(KNOWN_TASKS)})")
    tags = raw["tags"]
    if not isinstance(tags, list) or not tags or not set(tags) <= set(KNOWN_TAGS):
        raise CaseError(f"{where}: 'tags' must be a non-empty list from {list(KNOWN_TAGS)}")
    if not isinstance(raw["input"], dict) or not isinstance(raw["expect"], dict):
        raise CaseError(f"{where}: 'input' and 'expect' must be objects")
    if not raw["expect"]:
        raise CaseError(f"{where}: 'expect' is empty, so the case could never fail")
    return Case(
        id=raw["id"].strip(),
        task=raw["task"],
        tags=tuple(tags),
        input=raw["input"],
        expect=raw["expect"],
        note=str(raw.get("note", "")),
    )


def load_cases(directory: Path = CASES_DIR, task: str | None = None) -> list[Case]:
    """Every case in the directory (optionally one task's), checked as it is read. A duplicate id
    anywhere is an error, because reports are compared by case id."""
    cases: list[Case] = []
    seen: dict[str, str] = {}
    for path in sorted(directory.glob("*.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            where = f"{path.name}:{number}"
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CaseError(f"{where}: not valid JSON ({exc.msg})") from exc
            if not isinstance(raw, dict):
                raise CaseError(f"{where}: each line must be a JSON object")
            case = _parse(raw, where)
            if case.id in seen:
                first = seen[case.id]
                raise CaseError(f"{where}: duplicate id {case.id!r} (first used at {first})")
            seen[case.id] = where
            if task is None or case.task == task:
                cases.append(case)
    return cases
