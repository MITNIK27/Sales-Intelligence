"""G2: web content is data, never instructions. Prompt builders that include scraped pages, search
snippets, news or job posts must fence that text with `wrap_untrusted()` and tell the model to
ignore instructions inside it.

Skipped until Phase 2 creates `wrap_untrusted()`. When enabling: scan the prompt modules (draft,
opportunity, qualification, quicklook, offerings) and fail any that format evidence into a prompt
without calling it, with a ratchet list like the other checks."""

import pytest


@pytest.mark.skip(reason="Phase 2: enable once wrap_untrusted() exists (docs/ai-governance.md, G2)")
def test_prompt_builders_fence_web_content() -> None:
    raise NotImplementedError
