"""FastAPIEffects runtime configuration for the invoicing vertical slice."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fastapi_effects import AuthorizationMode, EffectContext, FastAPIEffects, Principal, RetryPolicy
from fastapi_effects.postgres import PostgresStore

from .auth import DemoPrincipalProvider
from .db import get_handler_session
from .models import Invoice, InvoiceRender
from .schemas import InvoiceCreated


class DemoAuthorizationResolver:
    async def resolve(
        self,
        principal: Principal,
        required_scopes: frozenset[str],
        mode: AuthorizationMode,
        service_policy: str | None,
    ) -> frozenset[str]:
        del mode, service_policy
        return principal.scopes & required_scopes


async def render_invoice_pdf(context: EffectContext[InvoiceCreated]) -> None:
    """Record one rendered invoice through a fresh tenant-bound app session."""
    payload = InvoiceCreated.model_validate(context.event.data)
    async with context.application_session() as session:
        invoice = await session.scalar(
            select(Invoice).where(
                Invoice.tenant_id == context.principal.tenant_id,
                Invoice.id == payload.invoice_id,
            )
        )
        if invoice is None:
            raise RuntimeError("Invoice is unavailable to its tenant-bound handler.")
        await session.execute(
            pg_insert(InvoiceRender)
            .values(
                tenant_id=context.principal.tenant_id,
                invoice_id=payload.invoice_id,
                delivery_id=context.delivery_id,
            )
            .on_conflict_do_nothing(
                index_elements=(InvoiceRender.tenant_id, InvoiceRender.invoice_id)
            )
        )
        existing = await session.scalar(
            select(InvoiceRender).where(
                InvoiceRender.tenant_id == context.principal.tenant_id,
                InvoiceRender.invoice_id == payload.invoice_id,
            )
        )
        if existing is None:
            raise RuntimeError("An equivalent invoice render could not be verified.")


fastapi_effects = FastAPIEffects(
    principal_provider=DemoPrincipalProvider(),
    store=PostgresStore(),
    authorization_resolver=DemoAuthorizationResolver(),
    handler_session_provider=get_handler_session,
)

fastapi_effects.route(
    event_type="invoice.created",
    route_key="invoice.render_pdf",
    version=1,
).to_handler(
    render_invoice_pdf,
    required_scopes={"invoices:read"},
    authorization=AuthorizationMode.REVALIDATE,
    retry_policy=RetryPolicy(
        name="invoice-handler",
        max_attempts=5,
        handler_timeout_seconds=30,
        lease_duration_seconds=90,
    ),
)
