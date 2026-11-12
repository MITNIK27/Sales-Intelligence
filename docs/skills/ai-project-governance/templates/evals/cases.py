"""Eval cases: one JSON object per line in `evals/cases/*.jsonl`.

A case is a frozen input plus what a good answer must (or must not) do. Inputs are frozen so a
failure means the model or the prompt changed, not that the web did.

TODO: list your task names in KNOWN_TASKS as you add them (each needs a runner and graders)."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CASES_DIR = Path(__file__).resolve().parent / "cases"
KNOWN_TASKS: tuple[str, ...] = ()  # TODO

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
        raise CaseError(f"{where}: unknown key(s) {sorted(extra)}")
    for key in ("id", "task", "tags", "input", "expect"):
        if key not in raw:
            raise CaseError(f"{where}: missing '{key}'")
    if raw["task"] not in KNOWN_TASKS:
        raise CaseError(f"{where}: unknown task {raw['task']!r}")
    tags = raw["tags"]
    if not isinstance(tags, list) or not tags or not set(tags) <= set(KNOWN_TAGS):
        raise CaseError(f"{where}: 'tags' must be a non-empty list from {list(KNOWN_TAGS)}")
    if not raw["expect"]:
        raise CaseError(f"{where}: 'expect' is empty, so the case could never fail")
    return Case(raw["id"], raw["task"], tuple(tags), raw["input"], raw["expect"], str(raw.get("note", "")))


def load_cases(directory: Path = CASES_DIR, task: str | None = None) -> list[Case]:
    """Every case, checked as it is read. A duplicate id is an error: reports compare by id."""
    cases: list[Case] = []
    seen: dict[str, str] = {}
    for path in sorted(directory.glob("*.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            where = f"{path.name}:{number}"
            case = _parse(json.loads(line), where)
            if case.id in seen:
                raise CaseError(f"{where}: duplicate id {case.id!r} (first at {seen[case.id]})")
            seen[case.id] = where
            if task is None or case.task == task:
                cases.append(case)
    return cases
