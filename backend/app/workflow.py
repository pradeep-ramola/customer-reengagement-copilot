from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session, selectinload

from app.ai_clients import AIClient, get_ai_client
from app.database import SessionLocal
from app.models import Campaign, CampaignResult, Customer, Draft, Purchase
from app.workflow_schemas import ComplianceResult, CustomerScore, DraftOutput, ProductAnalysis


MAX_DRAFT_CUSTOMERS = 20
MAX_COMPLIANCE_RETRIES = 2


class CampaignWorkflowState(TypedDict, total=False):
    campaign_id: int
    campaign: dict[str, str | None]
    today: date
    force_bad_compliance_once: bool
    product_analysis: ProductAnalysis
    product_embedding: list[float]
    candidates: list[dict[str, Any]]
    rag_context: dict[int, list[dict[str, Any]]]
    scores: list[CustomerScore]
    channel_decisions: dict[int, dict[str, Any]]
    drafts: dict[int, DraftOutput]
    compliance_results: dict[int, ComplianceResult]
    correction_instructions: dict[int, str]
    compliance_retry_count: int
    should_retry_compliance: bool
    saved_result_count: int
    saved_draft_count: int


def build_campaign_graph(ai_client: AIClient | None = None):
    client = ai_client or get_ai_client()
    graph = StateGraph(CampaignWorkflowState)

    graph.add_node("analyze_product_node", lambda state: analyze_product_node(state, client))
    graph.add_node("retrieve_customers_node", retrieve_customers_node)
    graph.add_node("rag_context_node", lambda state: rag_context_node(state, client))
    graph.add_node("score_customers_node", score_customers_node)
    graph.add_node("filter_and_channel_decision_node", filter_and_channel_decision_node)
    graph.add_node("generate_drafts_node", lambda state: generate_drafts_node(state, client))
    graph.add_node("compliance_check_node", lambda state: compliance_check_node(state, client))
    graph.add_node("save_results_node", save_results_node)

    graph.add_edge(START, "analyze_product_node")
    graph.add_edge("analyze_product_node", "retrieve_customers_node")
    graph.add_edge("retrieve_customers_node", "rag_context_node")
    graph.add_edge("rag_context_node", "score_customers_node")
    graph.add_edge("score_customers_node", "filter_and_channel_decision_node")
    graph.add_edge("filter_and_channel_decision_node", "generate_drafts_node")
    graph.add_edge("generate_drafts_node", "compliance_check_node")
    graph.add_conditional_edges(
        "compliance_check_node",
        route_after_compliance,
        {
            "retry": "generate_drafts_node",
            "save": "save_results_node",
        },
    )
    graph.add_edge("save_results_node", END)
    return graph.compile()


def analyze_product_node(state: CampaignWorkflowState, ai_client: AIClient) -> dict[str, Any]:
    campaign = state["campaign"]
    analysis = ai_client.analyze_product(campaign)
    product_text = " ".join(
        [
            campaign["product_name"] or "",
            campaign["product_category"] or "",
            campaign["product_description"] or "",
            campaign.get("launch_offer") or "",
        ]
    )
    product_embedding = ai_client.embed_text(product_text)
    return {
        "product_analysis": analysis,
        "product_embedding": product_embedding,
    }


def retrieve_customers_node(state: CampaignWorkflowState) -> dict[str, Any]:
    with SessionLocal() as db:
        has_purchase = exists(select(Purchase.id).where(Purchase.customer_id == Customer.id))
        customers = db.scalars(
            select(Customer)
            .options(selectinload(Customer.purchases))
            .where(
                Customer.unsubscribed.is_(False),
                (Customer.email_opt_in.is_(True) | Customer.sms_opt_in.is_(True)),
                has_purchase,
            )
            .order_by(Customer.id.asc())
        ).all()
        return {"candidates": [customer_to_candidate(customer) for customer in customers]}


def rag_context_node(state: CampaignWorkflowState, ai_client: AIClient) -> dict[str, Any]:
    product_embedding = state["product_embedding"]
    candidate_ids = [candidate["id"] for candidate in state["candidates"]]
    rag_context: dict[int, list[dict[str, Any]]] = {}

    with SessionLocal() as db:
        hydrate_missing_purchase_embeddings(db, ai_client)
        for customer_id in candidate_ids:
            distance = Purchase.embedding.cosine_distance(product_embedding).label("distance")
            rows = db.execute(
                select(Purchase, distance)
                .where(Purchase.customer_id == customer_id, Purchase.embedding.is_not(None))
                .order_by(distance.asc())
                .limit(2)
            ).all()
            rag_context[customer_id] = [
                {
                    "purchase_id": purchase.id,
                    "product_name": purchase.product_name,
                    "product_category": purchase.product_category,
                    "product_description": purchase.product_description,
                    "purchase_date": purchase.purchase_date.isoformat(),
                    "similarity": round(max(0.0, min(1.0, 1.0 - float(distance_value))), 4),
                }
                for purchase, distance_value in rows
            ]

    return {"rag_context": rag_context}


def score_customers_node(state: CampaignWorkflowState) -> dict[str, Any]:
    today = state.get("today") or date.today()
    rag_context = state["rag_context"]
    scores: list[CustomerScore] = []

    for candidate in state["candidates"]:
        matches = rag_context.get(candidate["id"], [])
        best_similarity = max((match["similarity"] for match in matches), default=0.0)
        most_recent_purchase = max((purchase["purchase_date"] for purchase in candidate["purchases"]), default=None)
        recency_days = (today - date.fromisoformat(most_recent_purchase)).days if most_recent_purchase else 365

        # Normalization rules are intentionally explicit for later tuning:
        # similarity contributes cosine_similarity * 35; recency gives full points
        # before 30 days and linearly decays to zero at 365 days; purchase count caps
        # at 5; LTV caps at $1000; engagement_score is already a 0-100 input.
        product_similarity = clamp(best_similarity * 35.0, 0.0, 35.0)
        purchase_recency = recency_score(recency_days)
        purchase_frequency = min(candidate["purchase_count"] / 5.0, 1.0) * 20.0
        lifetime_value = min(candidate["lifetime_value"] / 1000.0, 1.0) * 10.0
        engagement_score = (candidate["engagement_score"] / 100.0) * 10.0

        breakdown = {
            "product_similarity": round(product_similarity, 2),
            "purchase_recency": round(purchase_recency, 2),
            "purchase_frequency": round(purchase_frequency, 2),
            "lifetime_value": round(lifetime_value, 2),
            "engagement_score": round(engagement_score, 2),
        }
        total_score = round(sum(breakdown.values()), 2)
        top_match_name = matches[0]["product_name"] if matches else "purchase history"
        scores.append(
            CustomerScore(
                customer_id=candidate["id"],
                customer_name=candidate["name"],
                buyer_score=total_score,
                score_breakdown=breakdown,
                ranking_reason=(
                    f"{candidate['name']} scored {total_score} based on {top_match_name}, "
                    f"{candidate['purchase_count']} purchases, ${candidate['lifetime_value']:.2f} LTV, "
                    f"and engagement score {candidate['engagement_score']:.0f}."
                ),
            )
        )

    return {"scores": sorted(scores, key=lambda item: item.buyer_score, reverse=True)}


def filter_and_channel_decision_node(state: CampaignWorkflowState) -> dict[str, Any]:
    candidates_by_id = {candidate["id"]: candidate for candidate in state["candidates"]}
    decisions: dict[int, dict[str, Any]] = {}

    for score in state["scores"]:
        candidate = candidates_by_id[score.customer_id]
        if candidate["unsubscribed"] or score.buyer_score < 50:
            decisions[score.customer_id] = {
                "eligible": False,
                "recommended_channel": "none",
                "reason": "Skipped because the customer is unsubscribed or below the score threshold.",
            }
            continue

        if candidate["email_opt_in"] and candidate["sms_opt_in"] and score.buyer_score >= 75:
            channel = "both"
        elif candidate["email_opt_in"]:
            channel = "email"
        elif candidate["sms_opt_in"]:
            channel = "sms"
        else:
            channel = "none"

        decisions[score.customer_id] = {
            "eligible": channel != "none",
            "recommended_channel": channel,
            "reason": f"Eligible via {channel} based on consent flags and score {score.buyer_score}.",
        }

    return {"channel_decisions": decisions}


def generate_drafts_node(state: CampaignWorkflowState, ai_client: AIClient) -> dict[str, Any]:
    candidates_by_id = {candidate["id"]: candidate for candidate in state["candidates"]}
    scores_by_id = {score.customer_id: score for score in state["scores"]}
    correction_instructions = state.get("correction_instructions", {})
    retry_count = state.get("compliance_retry_count", 0)
    eligible_scores = [
        score for score in state["scores"] if state["channel_decisions"][score.customer_id]["eligible"]
    ][:MAX_DRAFT_CUSTOMERS]
    drafts: dict[int, DraftOutput] = {}

    for index, score in enumerate(eligible_scores):
        customer = candidates_by_id[score.customer_id]
        channel = state["channel_decisions"][score.customer_id]["recommended_channel"]
        top_match = (state["rag_context"].get(score.customer_id) or [None])[0]
        force_bad_sms_opt_out = (
            bool(state.get("force_bad_compliance_once"))
            and retry_count == 0
            and index == 0
            and channel in {"sms", "both"}
        )
        drafts[score.customer_id] = ai_client.generate_draft(
            customer=customer,
            campaign=state["campaign"],
            product_analysis=state["product_analysis"],
            top_match=top_match,
            ranking_reason=scores_by_id[score.customer_id].ranking_reason,
            channel=channel,
            correction_instructions=correction_instructions.get(score.customer_id),
            force_bad_sms_opt_out=force_bad_sms_opt_out,
        )

    return {"drafts": drafts}


def compliance_check_node(state: CampaignWorkflowState, ai_client: AIClient) -> dict[str, Any]:
    candidates_by_id = {candidate["id"]: candidate for candidate in state["candidates"]}
    compliance_results: dict[int, ComplianceResult] = {}
    correction_instructions: dict[int, str] = {}

    for customer_id, draft in state.get("drafts", {}).items():
        channel = state["channel_decisions"][customer_id]["recommended_channel"]
        result = ai_client.check_compliance(candidates_by_id[customer_id], draft, channel)
        compliance_results[customer_id] = result
        if not result.passed and result.correction_instructions:
            correction_instructions[customer_id] = result.correction_instructions

    retry_count = state.get("compliance_retry_count", 0)
    has_failures = any(not result.passed for result in compliance_results.values())
    should_retry = has_failures and retry_count < MAX_COMPLIANCE_RETRIES
    next_retry_count = retry_count + 1 if should_retry else retry_count

    if has_failures and not should_retry:
        compliance_results = {
            customer_id: (
                result
                if result.passed
                else ComplianceResult(
                    customer_id=customer_id,
                    passed=False,
                    compliance_status="needs_manual_review",
                    issues=result.issues,
                    correction_instructions=result.correction_instructions,
                )
            )
            for customer_id, result in compliance_results.items()
        }

    return {
        "compliance_results": compliance_results,
        "correction_instructions": correction_instructions if should_retry else {},
        "compliance_retry_count": next_retry_count,
        "should_retry_compliance": should_retry,
    }


def route_after_compliance(state: CampaignWorkflowState) -> Literal["retry", "save"]:
    if state.get("should_retry_compliance", False):
        return "retry"
    return "save"


def run_campaign_workflow(campaign_id: int, force_bad_compliance_once: bool = False) -> CampaignWorkflowState:
    with SessionLocal() as db:
        campaign = db.get(Campaign, campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id} not found.")

        initial_state: CampaignWorkflowState = {
            "campaign_id": campaign.id,
            "campaign": campaign_to_state(campaign),
            "today": date.today(),
            "force_bad_compliance_once": force_bad_compliance_once,
            "compliance_retry_count": 0,
        }

    graph = build_campaign_graph()
    return graph.invoke(initial_state)


def save_results_node(state: CampaignWorkflowState) -> dict[str, int]:
    saved_result_count = 0
    saved_draft_count = 0
    decisions = state["channel_decisions"]
    drafts = state.get("drafts", {})
    compliance_results = state.get("compliance_results", {})

    with SessionLocal() as db:
        db.execute(delete(CampaignResult).where(CampaignResult.campaign_id == state["campaign_id"]))
        db.flush()

        for score in state["scores"]:
            decision = decisions[score.customer_id]
            compliance = compliance_results.get(score.customer_id)
            result = CampaignResult(
                campaign_id=state["campaign_id"],
                customer_id=score.customer_id,
                buyer_score=Decimal(str(score.buyer_score)),
                score_breakdown_json=score.score_breakdown,
                ranking_reason=score.ranking_reason,
                recommended_channel=decision["recommended_channel"],
                compliance_status=(
                    compliance.compliance_status
                    if compliance is not None
                    else ("not_generated_score_below_threshold" if not decision["eligible"] else "not_checked")
                ),
            )
            db.add(result)
            db.flush()
            saved_result_count += 1

            draft = drafts.get(score.customer_id)
            if draft is not None:
                db.add(
                    Draft(
                        campaign_result_id=result.id,
                        email_subject=draft.email_subject,
                        email_body=draft.email_body,
                        sms_body=draft.sms_body,
                        status="pending_review",
                    )
                )
                saved_draft_count += 1

        db.commit()

    return {"saved_result_count": saved_result_count, "saved_draft_count": saved_draft_count}


def campaign_to_state(campaign: Campaign) -> dict[str, str | None]:
    return {
        "name": campaign.name,
        "product_name": campaign.product_name,
        "product_description": campaign.product_description,
        "product_category": campaign.product_category,
        "launch_offer": campaign.launch_offer,
    }


def create_demo_campaign(db: Session) -> Campaign:
    campaign = Campaign(
        name="Workflow Demo - Premium Headphones",
        product_name="Premium Noise-Canceling Headphones",
        product_description="Over-ear wireless headphones with adaptive noise cancellation and premium comfort.",
        product_category="Audio",
        launch_offer="15% off during launch week",
        status="draft",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def customer_to_candidate(customer: Customer) -> dict[str, Any]:
    purchases = list(customer.purchases)
    return {
        "id": customer.id,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "name": f"{customer.first_name} {customer.last_name}",
        "email": customer.email,
        "phone": customer.phone,
        "email_opt_in": customer.email_opt_in,
        "sms_opt_in": customer.sms_opt_in,
        "unsubscribed": customer.unsubscribed,
        "lifetime_value": float(customer.lifetime_value),
        "engagement_score": float(customer.engagement_score),
        "purchase_count": len(purchases),
        "purchases": [
            {
                "id": purchase.id,
                "product_name": purchase.product_name,
                "product_category": purchase.product_category,
                "product_description": purchase.product_description,
                "amount": float(purchase.amount),
                "purchase_date": purchase.purchase_date.isoformat(),
            }
            for purchase in purchases
        ],
    }


def hydrate_missing_purchase_embeddings(db: Session, ai_client: AIClient) -> None:
    purchases = db.scalars(select(Purchase).where(Purchase.embedding.is_(None))).all()
    for purchase in purchases:
        text = " ".join(
            [
                purchase.product_name,
                purchase.product_category,
                purchase.product_description,
            ]
        )
        purchase.embedding = ai_client.embed_text(text)
    if purchases:
        db.commit()


def recency_score(days_since_purchase: int) -> float:
    if days_since_purchase <= 30:
        return 25.0
    if days_since_purchase >= 365:
        return 0.0
    return ((365.0 - days_since_purchase) / (365.0 - 30.0)) * 25.0


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
