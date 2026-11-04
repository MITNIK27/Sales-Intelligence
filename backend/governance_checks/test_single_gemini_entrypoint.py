"""G6: model calls go through one place, so temperature, output cap, thinking and retries are set
once. This is a ratchet: the files below still build their own Gemini client (a known gap), no new
file may, and a file that has been moved onto the shared helper must be removed from the list."""

from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

# Files allowed to create a Gemini client directly today. Phase 1 empties this list.
KNOWN_DIRECT_CALLERS = {
    "modules/ai_recommendation/gemini_client.py",
    "modules/ai_recommendation/recommendation_generator.py",
    "modules/discovery_agent/extractor.py",
    "modules/draft/draft_generator.py",
    "modules/llm/structured.py",
    "modules/qualification/qualification_generator.py",
    "modules/role_relevance/role_relevance_generator.py",
}


def _files_creating_a_gemini_client() -> set[str]:
    found = set()
    for path in APP.rglob("*.py"):
        if "genai.Client(" in path.read_text(encoding="utf-8"):
            found.add(path.relative_to(APP).as_posix())
    return found


def test_no_new_file_creates_its_own_gemini_client() -> None:
    new = _files_creating_a_gemini_client() - KNOWN_DIRECT_CALLERS
    assert not new, (
        f"{sorted(new)} create a Gemini client directly. Use the shared model-call helper so "
        "temperature, output cap and retries are set in one place (docs/ai-governance.md, G6)."
    )


def test_fixed_files_are_removed_from_the_known_gaps_list() -> None:
    fixed = KNOWN_DIRECT_CALLERS - _files_creating_a_gemini_client()
    assert not fixed, (
        f"{sorted(fixed)} no longer create a Gemini client. Remove them from "
        "KNOWN_DIRECT_CALLERS so the list only shrinks."
    )
