from contextlib import asynccontextmanager
from csv import DictReader
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
import csv
import logging

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import Select, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.ai_clients import get_ai_client
from app.config import cors_origin_list, settings
from app.database import get_db, init_db
from app.models import Campaign, CampaignResult, Customer, Draft, Purchase
from app.schemas import (
    CampaignResultDetailOut,
    CampaignCreate,
    CampaignOut,
    CampaignRunOut,
    CustomerOut,
    DraftActionOut,
    DraftDetailOut,
    DraftRegenerateRequest,
    DraftUpdate,
    DemoSeedResult,
    PurchaseSummary,
    RankedCustomerSummary,
    ResultCustomerOut,
    UploadResult,
)
from app.seed import DEMO_CUSTOMERS
from app.workflow import (
    MAX_COMPLIANCE_RETRIES,
    campaign_to_state,
    customer_to_candidate,
    hydrate_missing_purchase_embeddings,
    run_campaign_workflow,
)


logger = logging.getLogger(__name__)


CSV_COLUMNS = {
    "first_name",
    "last_name",
    "email",
    "phone",
    "email_opt_in",
    "sms_opt_in",
    "unsubscribed",
    "lifetime_value",
    "engagement_score",
    "product_name",
    "product_category",
    "product_description",
    "amount",
    "purchase_date",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Customer Re-Engagement AI Copilot", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(),
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
    return {"status": "ok", "database": "ok"}


@app.post("/customers/upload", response_model=UploadResult)
async def upload_customers(file: UploadFile = File(...), db: Session = Depends(get_db)) -> UploadResult:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload must be a CSV file.")

    raw = await file.read()
    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.") from exc

    reader = DictReader(StringIO(csv_text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV is empty or missing a header row.")

    missing_columns = CSV_COLUMNS.difference(reader.fieldnames)
    if missing_columns:
        raise HTTPException(status_code=400, detail=f"CSV is missing columns: {sorted(missing_columns)}")

    customers_created = 0
    purchases_created = 0

    try:
        for row_number, row in enumerate(reader, start=2):
            email = required_text(row, "email", row_number).lower()
            customer = db.scalar(select(Customer).where(Customer.email == email))

            if customer is None:
                customer = Customer(
                    first_name=required_text(row, "first_name", row_number),
                    last_name=required_text(row, "last_name", row_number),
                    email=email,
                    phone=optional_text(row, "phone"),
                    email_opt_in=parse_bool(row.get("email_opt_in"), "email_opt_in", row_number),
                    sms_opt_in=parse_bool(row.get("sms_opt_in"), "sms_opt_in", row_number),
                    unsubscribed=parse_bool(row.get("unsubscribed"), "unsubscribed", row_number),
                    lifetime_value=parse_decimal(row.get("lifetime_value"), "lifetime_value", row_number),
                    engagement_score=parse_decimal(row.get("engagement_score"), "engagement_score", row_number),
                )
                db.add(customer)
                db.flush()
                customers_created += 1

            purchase = Purchase(
                customer_id=customer.id,
                product_name=required_text(row, "product_name", row_number),
                product_category=required_text(row, "product_category", row_number),
                product_description=required_text(row, "product_description", row_number),
                amount=parse_decimal(row.get("amount"), "amount", row_number),
                purchase_date=parse_date(row.get("purchase_date"), "purchase_date", row_number),
            )
            db.add(purchase)
            purchases_created += 1

        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="CSV conflicts with an existing unique value.") from exc

    return UploadResult(customers_created=customers_created, purchases_created=purchases_created)


@app.post("/demo/seed", response_model=DemoSeedResult)
def seed_demo(db: Session = Depends(get_db)) -> DemoSeedResult:
    inserted_customers = 0
    skipped_existing_customers = 0

    for item in DEMO_CUSTOMERS:
        existing = db.scalar(select(Customer).where(Customer.email == item["email"]))
        if existing is not None:
            skipped_existing_customers += 1
            continue

        customer = Customer(
            first_name=item["first_name"],
            last_name=item["last_name"],
            email=item["email"],
            phone=item["phone"],
            email_opt_in=item["email_opt_in"],
            sms_opt_in=item["sms_opt_in"],
            unsubscribed=item["unsubscribed"],
            lifetime_value=item["lifetime_value"],
            engagement_score=item["engagement_score"],
        )
        db.add(customer)
        db.flush()

        for purchase_item in item["purchases"]:
            db.add(Purchase(customer_id=customer.id, **purchase_item))

        inserted_customers += 1

    db.commit()
    demo_emails = [item["email"] for item in DEMO_CUSTOMERS]
    demo_customers_total = db.scalar(select(func.count()).select_from(Customer).where(Customer.email.in_(demo_emails))) or 0
    return DemoSeedResult(
        inserted_customers=inserted_customers,
        skipped_existing_customers=skipped_existing_customers,
        demo_customers_total=demo_customers_total,
    )


@app.get("/customers", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)) -> list[CustomerOut]:
    customers = db.scalars(
        select(Customer)
        .options(selectinload(Customer.purchases))
        .order_by(Customer.created_at.asc(), Customer.id.asc())
    ).all()
    return [customer_to_out(customer) for customer in customers]


@app.post("/campaigns", response_model=CampaignRunOut, status_code=201)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db)) -> CampaignRunOut:
    campaign = Campaign(**payload.model_dump(), status="draft")
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    customer_count = db.scalar(select(func.count()).select_from(Customer)) or 0
    if customer_count == 0:
        campaign.status = "failed"
        campaign.error_message = "No customers found. Seed demo data or upload a CSV before running a campaign."
        db.commit()
        return CampaignRunOut(campaign_id=campaign.id, status=campaign.status, error_message=campaign.error_message, results=[])

    try:
        campaign.status = "running"
        campaign.error_message = None
        db.commit()

        run_campaign_workflow(campaign.id)

        db.refresh(campaign)
        campaign.status = "completed"
        campaign.error_message = None
        db.commit()
    except Exception as exc:
        db.rollback()
        failed_campaign = db.get(Campaign, campaign.id)
        if failed_campaign is not None:
            failed_campaign.status = "failed"
            failed_campaign.error_message = str(exc)
            db.commit()
        return CampaignRunOut(campaign_id=campaign.id, status="failed", error_message=str(exc), results=[])

    return CampaignRunOut(
        campaign_id=campaign.id,
        status=campaign.status,
        error_message=campaign.error_message,
        results=result_summaries_for_campaign(db, campaign.id),
    )


@app.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return campaign


@app.get("/campaigns/{campaign_id}/results", response_model=list[CampaignResultDetailOut])
def get_campaign_results(campaign_id: int, db: Session = Depends(get_db)) -> list[CampaignResultDetailOut]:
    campaign_exists = db.scalar(select(Campaign.id).where(Campaign.id == campaign_id))
    if campaign_exists is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    statement: Select[tuple[CampaignResult]] = (
        select(CampaignResult)
        .options(selectinload(CampaignResult.customer), selectinload(CampaignResult.draft))
        .where(CampaignResult.campaign_id == campaign_id)
        .order_by(CampaignResult.buyer_score.desc(), CampaignResult.id.asc())
    )
    return [campaign_result_to_detail(result) for result in db.scalars(statement).all()]


@app.post("/drafts/{draft_id}/regenerate", response_model=DraftDetailOut)
def regenerate_draft(
    draft_id: int,
    payload: DraftRegenerateRequest,
    db: Session = Depends(get_db),
) -> DraftDetailOut:
    draft = get_draft_with_context(db, draft_id)
    result = draft.campaign_result
    campaign = result.campaign
    customer = result.customer
    ai_client = get_ai_client()

    campaign_dict = campaign_to_state(campaign)
    product_analysis = ai_client.analyze_product(campaign_dict)
    product_embedding = ai_client.embed_text(
        " ".join(
            [
                campaign.product_name,
                campaign.product_category,
                campaign.product_description,
                campaign.launch_offer or "",
            ]
        )
    )
    hydrate_missing_purchase_embeddings(db, ai_client)
    top_match = top_purchase_match(db, customer.id, product_embedding)
    customer_payload = customer_to_candidate(customer)

    correction_instructions: str | None = None
    compliance_status = "needs_manual_review"
    generated = None
    for _attempt in range(MAX_COMPLIANCE_RETRIES + 1):
        generated = ai_client.generate_draft(
            customer=customer_payload,
            campaign=campaign_dict,
            product_analysis=product_analysis,
            top_match=top_match,
            ranking_reason=result.ranking_reason,
            channel=result.recommended_channel,
            correction_instructions=correction_instructions,
            tone=payload.tone,
            instruction=payload.instruction,
        )
        compliance = ai_client.check_compliance(customer_payload, generated, result.recommended_channel)
        compliance_status = compliance.compliance_status if compliance.passed else "needs_manual_review"
        if compliance.passed:
            break
        correction_instructions = compliance.correction_instructions

    if generated is None:
        raise HTTPException(status_code=500, detail="Draft regeneration failed.")

    draft.email_subject = generated.email_subject
    draft.email_body = generated.email_body
    draft.sms_body = generated.sms_body
    draft.status = "regenerated"
    result.compliance_status = compliance_status
    db.commit()
    db.refresh(draft)
    return DraftDetailOut.model_validate(draft)


@app.patch("/drafts/{draft_id}", response_model=DraftDetailOut)
def update_draft(draft_id: int, payload: DraftUpdate, db: Session = Depends(get_db)) -> DraftDetailOut:
    draft = get_draft_with_context(db, draft_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(draft, field, value)
    draft.status = "pending_review"
    draft.campaign_result.compliance_status = "needs_review_after_edit"
    db.commit()
    db.refresh(draft)
    return DraftDetailOut.model_validate(draft)


@app.post("/drafts/{draft_id}/approve", response_model=DraftActionOut)
def approve_draft(draft_id: int, db: Session = Depends(get_db)) -> DraftActionOut:
    draft = get_draft_with_context(db, draft_id)
    draft.status = "approved"
    if draft.campaign_result.compliance_status == "needs_review_after_edit":
        draft.campaign_result.compliance_status = "manual_review_approved"
    db.commit()
    db.refresh(draft)
    return DraftActionOut(draft=DraftDetailOut.model_validate(draft), message="Draft approved.")


@app.post("/drafts/{draft_id}/reject", response_model=DraftActionOut)
def reject_draft(draft_id: int, db: Session = Depends(get_db)) -> DraftActionOut:
    draft = get_draft_with_context(db, draft_id)
    draft.status = "rejected"
    db.commit()
    db.refresh(draft)
    return DraftActionOut(draft=DraftDetailOut.model_validate(draft), message="Draft rejected.")


@app.post("/drafts/{draft_id}/send-mock", response_model=DraftActionOut)
def send_mock_draft(draft_id: int, db: Session = Depends(get_db)) -> DraftActionOut:
    draft = get_draft_with_context(db, draft_id)
    if draft.status != "approved":
        raise HTTPException(status_code=400, detail="Approve the draft before mock sending it.")
    draft.status = "sent_mock"
    logger.info("Mock send completed for draft_id=%s", draft_id)
    db.commit()
    db.refresh(draft)
    return DraftActionOut(draft=DraftDetailOut.model_validate(draft), message="Mock send logged.")


@app.get("/campaigns/{campaign_id}/export")
def export_campaign_results(campaign_id: int, db: Session = Depends(get_db)) -> Response:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    results = db.scalars(
        select(CampaignResult)
        .options(selectinload(CampaignResult.customer), selectinload(CampaignResult.draft))
        .where(CampaignResult.campaign_id == campaign_id)
        .order_by(CampaignResult.buyer_score.desc(), CampaignResult.id.asc())
    ).all()
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "rank",
            "customer_name",
            "email",
            "phone",
            "buyer_score",
            "recommended_channel",
            "compliance_status",
            "draft_status",
            "ranking_reason",
            "email_subject",
            "email_body",
            "sms_body",
        ]
    )
    for index, result in enumerate(results, start=1):
        draft = result.draft
        writer.writerow(
            [
                index,
                f"{result.customer.first_name} {result.customer.last_name}",
                result.customer.email,
                result.customer.phone,
                float(result.buyer_score),
                result.recommended_channel,
                result.compliance_status,
                draft.status if draft else "",
                result.ranking_reason,
                draft.email_subject if draft else "",
                draft.email_body if draft else "",
                draft.sms_body if draft else "",
            ]
        )
    headers = {"Content-Disposition": f'attachment; filename="campaign-{campaign_id}-results.csv"'}
    return Response(content=buffer.getvalue(), media_type="text/csv", headers=headers)


def customer_to_out(customer: Customer) -> CustomerOut:
    purchases = list(customer.purchases)
    total_spend = sum((purchase.amount for purchase in purchases), Decimal("0.00"))
    last_purchase_date = max((purchase.purchase_date for purchase in purchases), default=None)
    latest_products = [purchase.product_name for purchase in purchases[:3]]

    return CustomerOut(
        id=customer.id,
        first_name=customer.first_name,
        last_name=customer.last_name,
        email=customer.email,
        phone=customer.phone,
        email_opt_in=customer.email_opt_in,
        sms_opt_in=customer.sms_opt_in,
        unsubscribed=customer.unsubscribed,
        lifetime_value=float(customer.lifetime_value),
        engagement_score=float(customer.engagement_score),
        created_at=customer.created_at,
        purchase_summary=PurchaseSummary(
            purchase_count=len(purchases),
            total_spend=float(total_spend),
            last_purchase_date=last_purchase_date,
            latest_products=latest_products,
        ),
        purchases=purchases,
    )


def result_summaries_for_campaign(db: Session, campaign_id: int) -> list[RankedCustomerSummary]:
    results = db.scalars(
        select(CampaignResult)
        .options(selectinload(CampaignResult.customer), selectinload(CampaignResult.draft))
        .where(CampaignResult.campaign_id == campaign_id)
        .order_by(CampaignResult.buyer_score.desc(), CampaignResult.id.asc())
    ).all()
    return [
        RankedCustomerSummary(
            result_id=result.id,
            customer_id=result.customer_id,
            customer_name=f"{result.customer.first_name} {result.customer.last_name}",
            buyer_score=float(result.buyer_score),
            recommended_channel=result.recommended_channel,
            compliance_status=result.compliance_status,
            draft_status=result.draft.status if result.draft else None,
            ranking_reason=result.ranking_reason,
        )
        for result in results
    ]


def campaign_result_to_detail(result: CampaignResult) -> CampaignResultDetailOut:
    customer = result.customer
    return CampaignResultDetailOut(
        id=result.id,
        campaign_id=result.campaign_id,
        customer=ResultCustomerOut(
            id=customer.id,
            first_name=customer.first_name,
            last_name=customer.last_name,
            email=customer.email,
            phone=customer.phone,
            email_opt_in=customer.email_opt_in,
            sms_opt_in=customer.sms_opt_in,
            unsubscribed=customer.unsubscribed,
            lifetime_value=float(customer.lifetime_value),
            engagement_score=float(customer.engagement_score),
        ),
        buyer_score=float(result.buyer_score),
        score_breakdown_json={key: float(value) for key, value in result.score_breakdown_json.items()},
        ranking_reason=result.ranking_reason,
        recommended_channel=result.recommended_channel,
        compliance_status=result.compliance_status,
        created_at=result.created_at,
        draft=DraftDetailOut.model_validate(result.draft) if result.draft else None,
    )


def get_draft_with_context(db: Session, draft_id: int) -> Draft:
    draft = db.scalar(
        select(Draft)
        .options(
            selectinload(Draft.campaign_result).selectinload(CampaignResult.campaign),
            selectinload(Draft.campaign_result)
            .selectinload(CampaignResult.customer)
            .selectinload(Customer.purchases),
        )
        .where(Draft.id == draft_id)
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return draft


def top_purchase_match(db: Session, customer_id: int, product_embedding: list[float]) -> dict | None:
    distance = Purchase.embedding.cosine_distance(product_embedding).label("distance")
    row = db.execute(
        select(Purchase, distance)
        .where(Purchase.customer_id == customer_id, Purchase.embedding.is_not(None))
        .order_by(distance.asc())
        .limit(1)
    ).first()
    if row is None:
        return None

    purchase, distance_value = row
    return {
        "purchase_id": purchase.id,
        "product_name": purchase.product_name,
        "product_category": purchase.product_category,
        "product_description": purchase.product_description,
        "purchase_date": purchase.purchase_date.isoformat(),
        "similarity": round(max(0.0, min(1.0, 1.0 - float(distance_value))), 4),
    }


def required_text(row: dict[str, str | None], field: str, row_number: int) -> str:
    value = optional_text(row, field)
    if value is None:
        raise ValueError(f"Row {row_number}: {field} is required.")
    return value


def optional_text(row: dict[str, str | None], field: str) -> str | None:
    value = row.get(field)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def parse_bool(value: str | None, field: str, row_number: int) -> bool:
    if value is None:
        raise ValueError(f"Row {row_number}: {field} is required.")
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Row {row_number}: {field} must be true/false, yes/no, or 1/0.")


def parse_decimal(value: str | None, field: str, row_number: int) -> Decimal:
    if value is None or not value.strip():
        raise ValueError(f"Row {row_number}: {field} is required.")
    try:
        return Decimal(value.strip())
    except InvalidOperation as exc:
        raise ValueError(f"Row {row_number}: {field} must be a number.") from exc


def parse_date(value: str | None, field: str, row_number: int) -> date:
    if value is None or not value.strip():
        raise ValueError(f"Row {row_number}: {field} is required.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"Row {row_number}: {field} must be an ISO date like 2026-06-10.") from exc
