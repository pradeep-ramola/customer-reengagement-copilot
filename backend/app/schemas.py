from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PurchaseOut(BaseModel):
    id: int
    product_name: str
    product_category: str
    product_description: str
    amount: float
    purchase_date: date

    model_config = ConfigDict(from_attributes=True)


class PurchaseSummary(BaseModel):
    purchase_count: int
    total_spend: float
    last_purchase_date: date | None
    latest_products: list[str]


class CustomerOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None
    email_opt_in: bool
    sms_opt_in: bool
    unsubscribed: bool
    lifetime_value: float
    engagement_score: float
    created_at: datetime
    purchase_summary: PurchaseSummary
    purchases: list[PurchaseOut]

    model_config = ConfigDict(from_attributes=True)


class UploadResult(BaseModel):
    customers_created: int
    purchases_created: int


class DemoSeedResult(BaseModel):
    inserted_customers: int
    skipped_existing_customers: int
    demo_customers_total: int


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    product_name: str = Field(min_length=1, max_length=255)
    product_description: str = Field(min_length=1)
    product_category: str = Field(min_length=1, max_length=120)
    launch_offer: str | None = None


class CampaignOut(BaseModel):
    id: int
    name: str
    product_name: str
    product_description: str
    product_category: str
    launch_offer: str | None
    status: str
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignResultOut(BaseModel):
    id: int
    campaign_id: int
    customer_id: int
    buyer_score: float
    score_breakdown_json: dict
    ranking_reason: str
    recommended_channel: str
    compliance_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RankedCustomerSummary(BaseModel):
    result_id: int
    customer_id: int
    customer_name: str
    buyer_score: float
    recommended_channel: str
    compliance_status: str
    draft_status: str | None
    ranking_reason: str


class CampaignRunOut(BaseModel):
    campaign_id: int
    status: str
    error_message: str | None = None
    results: list[RankedCustomerSummary]


class ResultCustomerOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None
    email_opt_in: bool
    sms_opt_in: bool
    unsubscribed: bool
    lifetime_value: float
    engagement_score: float


class DraftDetailOut(BaseModel):
    id: int
    campaign_result_id: int
    email_subject: str | None
    email_body: str | None
    sms_body: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignResultDetailOut(BaseModel):
    id: int
    campaign_id: int
    customer: ResultCustomerOut
    buyer_score: float
    score_breakdown_json: dict[str, float]
    ranking_reason: str
    recommended_channel: str
    compliance_status: str
    created_at: datetime
    draft: DraftDetailOut | None


class DraftUpdate(BaseModel):
    email_subject: str | None = None
    email_body: str | None = None
    sms_body: str | None = None


class DraftRegenerateRequest(BaseModel):
    tone: Literal["professional", "friendly", "short-direct", "promotional", "warm"] = "professional"
    instruction: str | None = None


class DraftActionOut(BaseModel):
    draft: DraftDetailOut
    message: str
