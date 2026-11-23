"""G1 for our own documents: passages, knowledge cards, summaries and picture descriptions from the
uploaded library may only be sent to Gemini, never to a fallback vendor that is not cleared for it.

Three ways that could break, each checked here:
- a prompt gets passages (`knowledge.block`) without going through `generate_with_knowledge`, the
  one function that restricts the chain to Gemini (and asks again without them when it cannot);
- the prompts that read whole documents (summary, cards, offering description) are built somewhere
  other than `documents/cards.py`, whose model chain is Gemini only;
- either of those two functions stops restricting the chain.

A new place that hands passages to a model fails until it uses `generate_with_knowledge` or is
listed in ALLOWED with the reason it can only reach Gemini. No model is called, no key is used."""

import re
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from app.core.config import Settings
from app.modules.documents import cards
from app.modules.documents.knowledge import Passage, generate_with_knowledge, pack
from app.modules.llm.structured import FallbackStructuredLLM, LLMError, StructuredLLM

APP = Path(__file__).resolve().parent.parent / "app"

# Files that hand passages to a model without `generate_with_knowledge`, and why that is safe.
ALLOWED = {
    "modules/ai_recommendation/service.py": (
        "passes them to the recommendation generator, whose only implementations are "
        "GeminiRecommendationGenerator (calls gemini_client directly) and the offline mock"
    ),
}

_PASSES_PASSAGES = re.compile(r"knowledge\.block|knowledge_block=")
_DOCUMENT_PROMPTS = re.compile(
    r"\b(build_section_prompt|build_document_summary_prompt|build_offering_update_prompt)\("
)


def _sources() -> dict[str, str]:
    return {
        path.relative_to(APP).as_posix(): path.read_text(encoding="utf-8")
        for path in APP.rglob("*.py")
    }


def test_every_prompt_with_passages_goes_through_the_gemini_only_path() -> None:
    unsafe = sorted(
        name
        for name, text in _sources().items()
        if _PASSES_PASSAGES.search(text)
        and "generate_with_knowledge(" not in text
        and name not in ALLOWED
        and name != "modules/documents/knowledge.py"
    )
    assert not unsafe, (
        f"{unsafe} put passages from our documents into a prompt without "
        "generate_with_knowledge(), so they could reach a vendor other than Gemini "
        "(docs/ai-governance.md, G1)."
    )


def test_the_allowed_list_only_names_files_that_still_pass_passages() -> None:
    sources = _sources()
    stale = [name for name in ALLOWED if not _PASSES_PASSAGES.search(sources.get(name, ""))]
    assert not stale, f"{stale} no longer pass passages: take them off ALLOWED"


def test_whole_document_prompts_are_only_built_where_the_chain_is_gemini_only() -> None:
    callers = sorted(
        name
        for name, text in _sources().items()
        if _DOCUMENT_PROMPTS.search(text) and name != "modules/documents/card_prompts.py"
    )
    assert callers == ["modules/documents/cards.py"], callers


def test_the_card_chain_is_gemini_only_whatever_order_is_configured() -> None:
    settings: Settings = cast(Any, Settings)(
        _env_file=None,  # ignores .env
        gemini_api_key="dummy",
        groq_api_key="dummy",
        offerings_llm_order="groq,gemini",
        opportunity_llm_order="groq,gemini",
    )
    chain = cards.make_card_llm(settings)
    assert isinstance(chain, FallbackStructuredLLM)
    assert [name for name, _ in chain.vendors] == ["gemini"]


class _Answer(BaseModel):
    text: str = "ok"


class _Vendor(StructuredLLM):
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name, self.model, self.fail = name, f"{name}-model", fail
        self.prompts: list[str] = []

    async def generate(self, prompt, schema):  # type: ignore[no-untyped-def]
        self.prompts.append(prompt)
        if self.fail:
            raise LLMError(f"{self.name} is down")
        return schema()


async def test_passages_never_reach_another_vendor_even_when_gemini_fails() -> None:
    knowledge = pack([Passage("Deck", "Slide 1", "We moved 40 plants.")], 1000)
    groq, gemini = _Vendor("groq"), _Vendor("gemini", fail=True)
    _, saw = await generate_with_knowledge(
        FallbackStructuredLLM([groq, gemini]),
        "WITH " + knowledge.block,
        "PLAIN",
        _Answer,
        knowledge,
    )
    assert not saw
    assert all("We moved 40 plants." in p for p in gemini.prompts)
    assert groq.prompts == ["PLAIN"]  # Groq only ever got the question without the passages
