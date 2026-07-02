from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select

from app.database import SessionLocal, init_db
from app.models import Customer
from app.seed import DEMO_CUSTOMERS
from app.workflow import build_campaign_graph, create_demo_campaign


def main() -> None:
    init_db()
    ensure_seeded_demo_data()

    with SessionLocal() as db:
        campaign = create_demo_campaign(db)

    initial_state = {
        "campaign_id": campaign.id,
        "campaign": {
            "name": campaign.name,
            "product_name": campaign.product_name,
            "product_description": campaign.product_description,
            "product_category": campaign.product_category,
            "launch_offer": campaign.launch_offer,
        },
        "today": date(2026, 7, 2),
        "force_bad_compliance_once": True,
        "compliance_retry_count": 0,
    }

    print_header("Running standalone LangGraph workflow")
    print_json({"campaign_id": campaign.id, "campaign": initial_state["campaign"]})
    print("AI provider: mock (no paid OpenAI API calls)\n")

    graph = build_campaign_graph()
    final_state: dict[str, Any] = {}
    for update in graph.stream(initial_state, stream_mode="updates"):
        for node_name, node_update in update.items():
            print_header(node_name)
            print_json(sanitize(node_update))
        final_state.update(next(iter(update.values())))

    print_header("Definition-of-done checks")
    candidates = final_state.get("candidates", [])
    scores = final_state.get("scores", [])
    decisions = final_state.get("channel_decisions", {})
    drafts = final_state.get("drafts", {})
    emily_present = any(candidate["first_name"] == "Emily" for candidate in candidates)
    score_sums = {
        score.customer_name: round(sum(score.score_breakdown.values()), 2) == score.buyer_score
        for score in scores
    }
    print_json(
        {
            "candidate_count": len(candidates),
            "emily_present": emily_present,
            "score_sums_match_total": score_sums,
            "draft_customer_ids": sorted(drafts.keys()),
            "channel_decisions": decisions,
            "saved_results": final_state.get("saved_result_count"),
            "saved_drafts": final_state.get("saved_draft_count"),
        }
    )


def ensure_seeded_demo_data() -> None:
    with SessionLocal() as db:
        count = db.scalar(select(func.count()).select_from(Customer)) or 0
        if count:
            return

        for item in DEMO_CUSTOMERS:
            from app.models import Purchase

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
        db.commit()


def print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=json_default))


def json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def sanitize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return sanitize(value.model_dump())
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key == "product_embedding":
                sanitized[key] = "<1536-dimensional embedding>"
            elif key == "drafts":
                sanitized[key] = {customer_id: sanitize(draft) for customer_id, draft in item.items()}
            elif key in {"scores", "compliance_results"}:
                sanitized[key] = sanitize(item)
            else:
                sanitized[key] = sanitize(item)
        return sanitized
    if isinstance(value, list):
        if len(value) == 1536 and all(isinstance(item, float) for item in value):
            return "<1536-dimensional embedding>"
        return [sanitize(item) for item in value]
    return value


if __name__ == "__main__":
    main()
