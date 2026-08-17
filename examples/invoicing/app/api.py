"""FastAPI routes that exercise the explicit UoW shape."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from fastapi_mergen import Event, MergenUnitOfWork

from .db import get_async_session
from .mergen_config import mergen
from .models import Invoice
from .schemas import InvoiceCreated, InvoiceIn, InvoiceOut

router = APIRouter()
get_uow = mergen.uow_dependency(get_async_session)


@router.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "milestone": "8"}


@router.post(
    "/invoices",
    response_model=InvoiceOut,
    status_code=status.HTTP_201_CREATED,
    tags=["invoices"],
)
async def create_invoice(
    data: InvoiceIn,
    uow: MergenUnitOfWork = Depends(get_uow),
) -> InvoiceOut:
    """Commit the invoice and its immutable effect intent in one transaction."""
    async with uow:
        invoice = Invoice(
            tenant_id=uow.principal.tenant_id,
            **data.model_dump(),
        )
        uow.session.add(invoice)
        await uow.session.flush()
        await uow.emit(
            Event(
                type="invoice.created",
                version=1,
                data=InvoiceCreated(
                    invoice_id=invoice.id,
                    customer_id=invoice.customer_id,
                    amount=invoice.amount,
                    currency=invoice.currency,
                ),
            ),
            dedupe_namespace="invoice-create",
            dedupe_key=str(invoice.id),
        )
    return InvoiceOut.model_validate(invoice)
