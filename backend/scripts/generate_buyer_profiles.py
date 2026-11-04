"""Write a buyer profile for every active offering that does not have one yet, from the
offering's own name and description. Offerings that already have a profile (generated or edited by
a person) are never touched, and nothing else about an offering changes.

Dry run by default: lists what would be generated and changes nothing. A real run needs --yes. It
uses the structured language-model chain (Groq first, Gemini as fallback); an offering's own
description contains no personal data. About 40 offerings cost well under $0.10.

Usage (from backend/, venv active):
    python scripts/generate_buyer_profiles.py          # dry run
    python scripts/generate_buyer_profiles.py --yes    # generate and save
"""

import argparse
import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import models as _models  # noqa: F401 - registers all models with SQLAlchemy
from app.db.session import SessionLocal
from app.modules.llm.structured import LLMError, build_structured_llm
from app.modules.offerings.profile import PROFILE_GENERATED, apply_profile, generate_buyer_profile
from app.modules.products.models import STATUS_ACTIVE, Product
from app.modules.usage.context import usage_scope


async def main(apply: bool) -> None:
    configure_logging()
    async with SessionLocal() as session:
        products = (
            (
                await session.execute(
                    select(Product)
                    .where(Product.status == STATUS_ACTIVE, Product.buyer_profile.is_(None))
                    .order_by(Product.name)
                )
            )
            .scalars()
            .all()
        )
        if not products:
            print("Every active offering already has a buyer profile.")
            return
        print(f"{len(products)} offering(s) without a buyer profile:")
        for product in products:
            print(f"  - {product.name} ({product.kind})")
        if not apply:
            print("\nDry run: nothing was changed. Run again with --yes to generate them.")
            return

        llm = build_structured_llm(get_settings())
        done = failed = 0
        for product in products:
            try:
                with usage_scope(task="generate_buyer_profiles"):  # so the cost report names it
                    profile = await generate_buyer_profile(llm, product)
            except LLMError as exc:
                failed += 1
                print(f"  could not generate for {product.name}: {exc}")
                continue
            apply_profile(product, profile, PROFILE_GENERATED)
            await session.commit()  # saved one by one, so a later failure loses nothing
            done += 1
            print(f"  generated: {product.name}")
        print(f"\nDone: {done} generated, {failed} failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="generate and save the profiles")
    asyncio.run(main(parser.parse_args().yes))
