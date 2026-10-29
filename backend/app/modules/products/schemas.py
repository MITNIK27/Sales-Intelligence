import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Kind = Literal["service", "product"]


class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    kind: Kind = "product"


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    kind: Kind | None = None
    # Imported offerings are archived rather than deleted (drafts reference them).
    status: Literal["active", "archived"] | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    kind: str
    source: str
    source_url: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ProductList(BaseModel):
    items: list[ProductOut]
    total: int
    limit: int
    offset: int
