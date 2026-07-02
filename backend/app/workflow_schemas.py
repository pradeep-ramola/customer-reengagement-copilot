from pydantic import BaseModel, Field


class ProductAnalysis(BaseModel):
    category: str
    key_benefits: list[str]
    likely_customer_traits: list[str]
    related_categories: list[str]
    messaging_angle: str


class CustomerScore(BaseModel):
    customer_id: int
    customer_name: str
    buyer_score: float = Field(ge=0, le=100)
    score_breakdown: dict[str, float]
    ranking_reason: str


class DraftOutput(BaseModel):
    customer_id: int
    email_subject: str | None = None
    email_body: str | None = None
    sms_body: str | None = None


class ComplianceResult(BaseModel):
    customer_id: int
    passed: bool
    compliance_status: str
    issues: list[str] = Field(default_factory=list)
    correction_instructions: str | None = None
