"""Who buys an offering. A buyer profile says which business functions decide on and influence an
offering, what problems it addresses and which opportunity areas it belongs to. It is generated
once from the offering's own description, shown and editable on the Our Offerings page, and later
grounds which people at a prospect matter for it and which offerings fit a company.

It describes *functions*, not job titles, because the same function has different titles in
different companies. Nothing in it is personal data, so it is safe to send to any language model.
"""

import hashlib
import json
from typing import Any

from pydantic import BaseModel, field_validator

from app.modules.llm.structured import StructuredLLM
from app.modules.products.models import Product

PROFILE_GENERATED = "generated"
PROFILE_EDITED = "edited"

_MAX_ITEMS = 8
_MAX_ITEM_CHARS = 80


class BuyerProfile(BaseModel):
    buyer_functions: list[str] = []
    influencer_functions: list[str] = []
    problems: list[str] = []
    keywords: list[str] = []
    area_tags: list[str] = []

    @field_validator("buyer_functions", "influencer_functions", "problems", "keywords", "area_tags")
    @classmethod
    def _tidy(cls, values: list[str]) -> list[str]:
        """Trim, drop blanks and repeats, and keep each list short enough to read and to prompt."""
        seen: set[str] = set()
        tidy: list[str] = []
        for value in values:
            text = " ".join(str(value).split())[:_MAX_ITEM_CHARS]
            if text and text.lower() not in seen:
                seen.add(text.lower())
                tidy.append(text)
        return tidy[:_MAX_ITEMS]


def source_hash(name: str, description: str | None, kind: str) -> str:
    """What the profile was generated from; when it no longer matches the offering, the profile is
    flagged as possibly out of date."""
    return hashlib.sha256(f"{name}\n{description or ''}\n{kind}".encode()).hexdigest()


def content_hash(profile: dict[str, Any]) -> str:
    """A fingerprint of the profile itself, used as part of cache keys for anything judged with it
    (a changed profile means earlier judgments are no longer current)."""
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()


def build_profile_prompt(product: Product) -> str:
    return f"""You are describing who inside a company buys and influences one of InfoBeans' \
offerings, so a salesperson can tell which people at a prospect matter for it. Use only the \
information below; do not invent customers, numbers or claims.

Offering: {product.name} ({product.kind})
Description: {product.description or "No description available."}

Return:
- buyer_functions: the business functions that typically decide to buy this (for example "IT \
infrastructure" or "finance operations"). Functions, not job titles, because titles differ between \
companies.
- influencer_functions: functions that shape or evaluate the decision.
- problems: up to 5 plain-language problems or goals this addresses for the buyer.
- keywords: single words or short phrases a prospect's own public text would use when it needs \
this.
- area_tags: 1 to 4 short opportunity areas this offering belongs to (for example "cloud \
migration" or "data platform").

Keep every item short. If the description is too thin to say, return fewer items rather than \
guessing."""


async def generate_buyer_profile(llm: StructuredLLM, product: Product) -> BuyerProfile:
    return await llm.generate(build_profile_prompt(product), BuyerProfile)


def apply_profile(product: Product, profile: BuyerProfile, status: str) -> None:
    """Store a profile on the offering. `status` records whether a model wrote it or a person
    edited it; only the profile fields change, never the offering's own details."""
    data = profile.model_dump()
    product.buyer_profile = data
    product.profile_status = status
    product.profile_hash = content_hash(data)
    product.profile_source_hash = source_hash(product.name, product.description, product.kind)
