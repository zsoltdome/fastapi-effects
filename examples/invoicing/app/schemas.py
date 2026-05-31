"""Typed application and event contracts for the invoicing example."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InvoiceIn(BaseModel):
    customer_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class InvoiceOut(InvoiceIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID


class InvoiceCreated(BaseModel):
    invoice_id: UUID
    customer_id: UUID
    amount: Decimal
    currency: str
