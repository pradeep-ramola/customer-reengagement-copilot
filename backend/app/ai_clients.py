from __future__ import annotations

from abc import ABC, abstractmethod
from hashlib import sha256
from math import sqrt
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.workflow_schemas import ComplianceResult, DraftOutput, ProductAnalysis


EMBEDDING_DIMENSION = 1536
EMBEDDING_MODEL = "text-embedding-3-small"


class AIClient(ABC):
    @abstractmethod
    def analyze_product(self, campaign: dict[str, str | None]) -> ProductAnalysis:
        raise NotImplementedError

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

    @abstractmethod
    def generate_draft(
        self,
        customer: dict[str, Any],
        campaign: dict[str, str | None],
        product_analysis: ProductAnalysis,
        top_match: dict[str, Any] | None,
        ranking_reason: str,
        channel: str,
        correction_instructions: str | None = None,
        force_bad_sms_opt_out: bool = False,
        tone: str | None = None,
        instruction: str | None = None,
    ) -> DraftOutput:
        raise NotImplementedError

    @abstractmethod
    def check_compliance(self, customer: dict[str, Any], draft: DraftOutput, channel: str) -> ComplianceResult:
        raise NotImplementedError


class MockAIClient(AIClient):
    def analyze_product(self, campaign: dict[str, str | None]) -> ProductAnalysis:
        category = campaign["product_category"] or "Audio"
        return ProductAnalysis(
            category=category,
            key_benefits=[
                "adaptive noise cancellation",
                "premium wireless sound",
                "comfortable all-day listening",
            ],
            likely_customer_traits=[
                "recent audio buyers",
                "customers with high engagement",
                "premium accessory shoppers",
            ],
            related_categories=["Audio", "Phone Accessories", "Productivity Accessories"],
            messaging_angle="Position the launch as a premium listening upgrade tailored to recent tech purchases.",
        )

    def embed_text(self, text: str) -> list[float]:
        return deterministic_embedding(text)

    def generate_draft(
        self,
        customer: dict[str, Any],
        campaign: dict[str, str | None],
        product_analysis: ProductAnalysis,
        top_match: dict[str, Any] | None,
        ranking_reason: str,
        channel: str,
        correction_instructions: str | None = None,
        force_bad_sms_opt_out: bool = False,
        tone: str | None = None,
        instruction: str | None = None,
    ) -> DraftOutput:
        first_name = customer["first_name"]
        product_name = campaign["product_name"]
        offer = campaign.get("launch_offer") or "a limited launch offer"
        match_text = "your recent tech purchase"
        if top_match is not None:
            match_text = f"your recent {top_match['product_name']} purchase"
        tone_label = (tone or "professional").replace("-", " ")
        extra_instruction = f"\n\nRefresh note: {instruction}" if instruction else ""

        subject = None
        email_body = None
        sms_body = None

        if channel in {"email", "both"}:
            if tone == "short-direct":
                subject = f"{first_name}, new headphones offer"
                email_body = (
                    f"Hi {first_name},\n\n"
                    f"{product_name} is launching with {offer}. Based on {match_text}, this looks like a relevant upgrade."
                    f"{extra_instruction}\n\n"
                    "Unsubscribe link: {{unsubscribe_url}}"
                )
            elif tone == "promotional":
                subject = f"{first_name}, launch-week audio savings"
                email_body = (
                    f"Hi {first_name},\n\n"
                    f"Launch week is here for {product_name}. Your interest in {match_text} makes this a timely fit, "
                    f"especially for {product_analysis.key_benefits[0]} and {product_analysis.key_benefits[1]}.\n\n"
                    f"Offer: {offer}.{extra_instruction}\n\n"
                    f"Why this recommendation: {ranking_reason}\n\n"
                    "Unsubscribe link: {{unsubscribe_url}}"
                )
            else:
                subject = f"{first_name}, an audio upgrade picked for you"
                warmth = "with a little more warmth" if tone == "warm" else f"in a {tone_label} tone"
                email_body = (
                    f"Hi {first_name},\n\n"
                    f"Because you showed interest through {match_text}, we thought {product_name} could be a strong fit. "
                    f"It focuses on {product_analysis.key_benefits[0]}, {product_analysis.key_benefits[1]}, and "
                    f"{product_analysis.key_benefits[2]}.\n\n"
                    f"{offer}. This version is written {warmth}.{extra_instruction}\n\n"
                    f"Why this recommendation: {ranking_reason}\n\n"
                    "Unsubscribe link: {{unsubscribe_url}}"
                )

        if channel in {"sms", "both"}:
            if tone == "short-direct":
                sms_body = f"Hi {first_name}, {product_name} is live with {offer}. Picked from {match_text}."
            else:
                sms_body = (
                    f"Hi {first_name}, {product_name} is launching with {offer}. "
                    f"Picked based on {match_text}."
                )
            if not force_bad_sms_opt_out:
                sms_body = f"{sms_body} Reply STOP to opt out."

        if correction_instructions:
            if email_body and "Unsubscribe link" not in email_body:
                email_body = f"{email_body}\n\nUnsubscribe link: {{{{unsubscribe_url}}}}"
            if sms_body and "STOP" not in sms_body.upper():
                sms_body = f"{sms_body} Reply STOP to opt out."

        return DraftOutput(
            customer_id=customer["id"],
            email_subject=subject,
            email_body=email_body,
            sms_body=sms_body,
        )

    def check_compliance(self, customer: dict[str, Any], draft: DraftOutput, channel: str) -> ComplianceResult:
        return deterministic_compliance_check(customer, draft, channel)


class OpenAIClient(AIClient):
    def __init__(self) -> None:
        if not settings.openai_api_key or settings.openai_api_key.startswith("dummy"):
            raise RuntimeError("OPENAI_API_KEY is missing or is a dummy value.")
        self.client = OpenAI(api_key=settings.openai_api_key)

    def analyze_product(self, campaign: dict[str, str | None]) -> ProductAnalysis:
        prompt = (
            "Return strict JSON for ProductAnalysis with keys category, key_benefits, "
            "likely_customer_traits, related_categories, messaging_angle.\n"
            f"Product: {campaign}"
        )
        return self._chat_json(prompt, ProductAnalysis)

    def embed_text(self, text: str) -> list[float]:
        response = self.client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return list(response.data[0].embedding)

    def generate_draft(
        self,
        customer: dict[str, Any],
        campaign: dict[str, str | None],
        product_analysis: ProductAnalysis,
        top_match: dict[str, Any] | None,
        ranking_reason: str,
        channel: str,
        correction_instructions: str | None = None,
        force_bad_sms_opt_out: bool = False,
        tone: str | None = None,
        instruction: str | None = None,
    ) -> DraftOutput:
        prompt = (
            "Return strict JSON for DraftOutput with keys customer_id, email_subject, email_body, sms_body. "
            "Use only channels allowed by the channel field. Email must include an unsubscribe placeholder. "
            "SMS must be under 320 characters and include 'Reply STOP to opt out.'\n"
            f"Customer: {customer}\nCampaign: {campaign}\nProduct analysis: {product_analysis.model_dump()}\n"
            f"Top RAG match: {top_match}\nReason: {ranking_reason}\nChannel: {channel}\n"
            f"Correction instructions: {correction_instructions or 'none'}\n"
            f"Tone: {tone or 'professional'}\nAdditional user instruction: {instruction or 'none'}"
        )
        return self._chat_json(prompt, DraftOutput)

    def check_compliance(self, customer: dict[str, Any], draft: DraftOutput, channel: str) -> ComplianceResult:
        prompt = (
            "Return strict JSON for ComplianceResult with keys customer_id, passed, compliance_status, "
            "issues, correction_instructions. Verify consent, opt-out/unsubscribe text, and unsupported claims.\n"
            f"Customer: {customer}\nChannel: {channel}\nDraft: {draft.model_dump()}"
        )
        return self._chat_json(prompt, ComplianceResult)

    def _chat_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        response = self.client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "You produce valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            raise RuntimeError(f"OpenAI response did not match {schema.__name__}: {exc}") from exc


def get_ai_client() -> AIClient:
    if settings.ai_provider.lower() == "openai":
        return OpenAIClient()
    return MockAIClient()


def deterministic_embedding(text: str) -> list[float]:
    normalized = text.lower()
    vector = [0.0] * EMBEDDING_DIMENSION

    keyword_weights = {
        0: ["audio", "earbuds", "headphones", "speaker", "sound", "bass", "listening", "noise"],
        1: ["phone", "case", "charger", "usb-c", "magsafe", "mobile"],
        2: ["laptop", "computer", "ultrabook", "remote work", "productivity"],
        3: ["keyboard", "stand", "ergonomic", "desk", "workflow"],
        4: ["watch", "wearable", "fitness", "tracker", "health", "sport"],
        5: ["premium", "pro", "elite", "studio", "advanced"],
    }

    for index, keywords in keyword_weights.items():
        vector[index] = sum(1.0 for keyword in keywords if keyword in normalized)

    digest = sha256(normalized.encode("utf-8")).digest()
    for offset, byte in enumerate(digest):
        vector[32 + offset] = (byte / 255.0) * 0.05

    magnitude = sqrt(sum(value * value for value in vector)) or 1.0
    return [value / magnitude for value in vector]


def deterministic_compliance_check(customer: dict[str, Any], draft: DraftOutput, channel: str) -> ComplianceResult:
    issues: list[str] = []

    if channel in {"email", "both"}:
        if not customer["email_opt_in"]:
            issues.append("Email draft generated for a customer without email consent.")
        if not draft.email_body or "unsubscribe" not in draft.email_body.lower():
            issues.append("Email body is missing an unsubscribe placeholder.")

    if channel in {"sms", "both"}:
        if not customer["sms_opt_in"]:
            issues.append("SMS draft generated for a customer without SMS consent.")
        if not draft.sms_body or "stop" not in draft.sms_body.lower():
            issues.append("SMS body is missing Reply STOP opt-out text.")

    if customer["unsubscribed"]:
        issues.append("Customer is unsubscribed.")

    if issues:
        return ComplianceResult(
            customer_id=customer["id"],
            passed=False,
            compliance_status="failed",
            issues=issues,
            correction_instructions="Regenerate only for consented channels and include required opt-out language.",
        )

    return ComplianceResult(customer_id=customer["id"], passed=True, compliance_status="passed")
