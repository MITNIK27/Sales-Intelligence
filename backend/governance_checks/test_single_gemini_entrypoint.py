"""G6: model calls go through one place, so temperature, output cap, thinking and retries are set
once. `generate_structured()` in the Gemini client module is that place; no other file may build
a Gemini client, and that file must still be the one that does."""

from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

ENTRYPOINT = "modules/ai_recommendation/gemini_client.py"


def _files_creating_a_gemini_client() -> set[str]:
    found = set()
    for path in APP.rglob("*.py"):
        if "genai.Client(" in path.read_text(encoding="utf-8"):
            found.add(path.relative_to(APP).as_posix())
    return found


def test_only_the_shared_helper_creates_a_gemini_client() -> None:
    others = _files_creating_a_gemini_client() - {ENTRYPOINT}
    assert not others, (
        f"{sorted(others)} create a Gemini client directly. Call generate_structured() so "
        "temperature, output cap and retries are set in one place (docs/ai-governance.md, G6)."
    )


def test_the_shared_helper_is_where_the_client_is_created() -> None:
    assert ENTRYPOINT in _files_creating_a_gemini_client(), (
        f"{ENTRYPOINT} no longer creates the Gemini client. If the helper moved, update ENTRYPOINT "
        "here and in docs/ai-governance.md."
    )
