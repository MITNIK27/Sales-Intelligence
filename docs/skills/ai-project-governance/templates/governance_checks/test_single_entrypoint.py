"""G6: model calls go through one place, so temperature, output cap, retries and metering are set
once. No other file may build a provider client, and the helper must still be the one that does.

TODO: set ENTRYPOINT to the helper's path (relative to APP) and CLIENT_MARKERS to the text that
constructs a provider client in your SDK ("genai.Client(", "OpenAI(", "Anthropic(", ...)."""

from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"  # TODO: your source folder

ENTRYPOINT = "llm/call.py"  # TODO
CLIENT_MARKERS = ("genai.Client(",)  # TODO

# Start empty. If an existing project has files that still build their own client, list them here
# with a plan to move them; the second test fails when one is fixed but still listed.
KNOWN_DIRECT_CALLERS: set[str] = set()


def _files_creating_a_client() -> set[str]:
    found = set()
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in CLIENT_MARKERS):
            found.add(path.relative_to(APP).as_posix())
    return found


def test_only_the_shared_helper_creates_a_client() -> None:
    others = _files_creating_a_client() - {ENTRYPOINT} - KNOWN_DIRECT_CALLERS
    assert not others, f"{sorted(others)} build their own client; call the shared helper (G6)."


def test_the_helper_is_where_the_client_is_created() -> None:
    assert ENTRYPOINT in _files_creating_a_client(), f"{ENTRYPOINT} no longer builds the client"


def test_fixed_files_leave_the_known_gaps_list() -> None:
    fixed = KNOWN_DIRECT_CALLERS - _files_creating_a_client()
    assert not fixed, f"{sorted(fixed)} are fixed; remove them from KNOWN_DIRECT_CALLERS"
