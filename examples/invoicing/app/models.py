"""Application-owned SQLAlchemy models used by the runtime vertical slice."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Invoice(Base):
    __tablename__ = "invoice"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class InvoiceRender(Base):
    __tablename__ = "invoice_renders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_id", name="uq_invoice_render_tenant_invoice"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    delivery_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
