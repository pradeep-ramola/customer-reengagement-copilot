from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("email", name="uq_customers_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    email_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    unsubscribed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    lifetime_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    engagement_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    purchases: Mapped[list["Purchase"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        order_by="desc(Purchase.purchase_date)",
    )
    campaign_results: Mapped[list["CampaignResult"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_category: Mapped[str] = mapped_column(String(120), nullable=False)
    product_description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))

    customer: Mapped[Customer] = relationship(back_populates="purchases")


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("status in ('draft', 'running', 'completed', 'failed')", name="campaign_status_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_description: Mapped[str] = mapped_column(Text, nullable=False)
    product_category: Mapped[str] = mapped_column(String(120), nullable=False)
    launch_offer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    results: Mapped[list["CampaignResult"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class CampaignResult(Base):
    __tablename__ = "campaign_results"
    __table_args__ = (
        UniqueConstraint("campaign_id", "customer_id", name="uq_campaign_results_campaign_customer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    buyer_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    score_breakdown_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    ranking_reason: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_channel: Mapped[str] = mapped_column(String(40), nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    campaign: Mapped[Campaign] = relationship(back_populates="results")
    customer: Mapped[Customer] = relationship(back_populates="campaign_results")
    draft: Mapped["Draft | None"] = relationship(back_populates="campaign_result", cascade="all, delete-orphan")


class Draft(Base):
    __tablename__ = "drafts"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending_review', 'approved', 'rejected', 'regenerated', 'sent_mock')",
            name="draft_status_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_result_id: Mapped[int] = mapped_column(
        ForeignKey("campaign_results.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    email_subject: Mapped[str | None] = mapped_column(String(255))
    email_body: Mapped[str | None] = mapped_column(Text)
    sms_body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_review", server_default="pending_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    campaign_result: Mapped[CampaignResult] = relationship(back_populates="draft")
