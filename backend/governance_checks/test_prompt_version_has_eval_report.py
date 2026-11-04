"""G5: changing a prompt version or the model comes with an eval report.

Skipped until Phase 3 creates `backend/evals/` and its reports. When enabling: collect every
`*PROMPT_VERSION` constant and the configured model, and fail when one has no matching report file
under `evals/reports/`, with the same kind of known-gaps list as the other checks."""

import pytest


@pytest.mark.skip(reason="Phase 3: enable once backend/evals/ exists (docs/ai-governance.md, G5)")
def test_every_prompt_version_has_an_eval_report() -> None:
    raise NotImplementedError
