"""Mergen API-spike configuration for the invoicing example."""

from __future__ import annotations

from fastapi_mergen import AuthorizationMode, EffectContext, Mergen, Principal, RetryPolicy

from .auth import DemoPrincipalProvider
from .schemas import InvoiceCreated


class MilestoneOneStore:
    @property
    def name(self) -> str:
        return "milestone-one-safety-stub"


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
    """Future tenant-bound handler; no task queue is implied."""
    del context


mergen = Mergen(
    principal_provider=DemoPrincipalProvider(),
    store=MilestoneOneStore(),
    authorization_resolver=DemoAuthorizationResolver(),
)

mergen.route(
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
