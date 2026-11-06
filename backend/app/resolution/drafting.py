"""Prepare presentation contracts from the same case; no transport capability."""

import re
from typing import Protocol

from app.resolution.models import DraftSpecification


class ChannelRenderer(Protocol):
    def presentation(self) -> str: ...


class ChatPresentation:
    def presentation(self):
        return "Brief plain-language message ready to paste into support chat. Reference the previous ticket if present; no email salutation or invented legal threat."


class EmailPresentation:
    def presentation(self):
        return "Professional subject, short chronology, prior complaint/reference, unresolved issue, specific requested action and factual sign-off. Missing details belong outside the prose or in explicit placeholders."


class FormPresentation:
    def presentation(self):
        return "Field-by-field preparation using verified field names where available. Clearly label suggested fields when the authenticated form has not been inspected. Do not invent character limits or submit anything."


class FormalPresentation:
    def presentation(self):
        return "Self-represented provisional preparation: parties, jurisdiction facts, numbered chronology, supported grounds, relief, verification placeholders and annexure index. Check actual filing requirements; never fabricate a signature, affidavit execution, advocate identity, notarisation or seal."


class DraftPreparationService:
    def __init__(self, registry):
        self.registry = registry
        self.renderers = {
            "chat": ChatPresentation(),
            "email": EmailPresentation(),
            "form": FormPresentation(),
            "formal": FormalPresentation(),
        }

    def prepare(self, memory, recommendation, message, intent):
        if intent != "draft":
            return None
        routes = recommendation.alternatives
        explicit = None
        for pattern, route in [
            (r"\bnch\b|national consumer helpline", "nch"),
            (r"commission|consumer court|petition", "commission"),
            (r"grievance officer|grievance team", "grievance"),
            (r"\brbi\b", "rbi"),
            (r"food safety|fssai", "food_safety"),
        ]:
            if re.search(pattern, message, re.I):
                explicit = route
                break
        previous = memory.last_draft_spec
        chosen = (
            next((r for r in routes if r.route_id == explicit or r.recipient_id == explicit), None)
            if explicit
            else None
        )
        if (
            not chosen
            and previous
            and re.search(r"shorter|polite|revise|rewrite|same|hindi|हिंदी", message, re.I)
        ):
            chosen = next(
                (
                    r
                    for r in routes
                    if r.route_id == previous.route_id or r.recipient_id == previous.recipient_id
                ),
                None,
            )
        if not chosen:
            chosen = next(
                (r for r in routes if r.route_id == recommendation.recommended_route_id), None
            )
        if not chosen:
            return None
        profile = self.registry.platform(chosen.recipient_id)
        if not profile:
            profile = (
                {"required_fields": ["order reference", "issue", "requested resolution"]}
                if chosen.recipient_id in {"company_support", "company_grievance"}
                else self.registry.authority(chosen.recipient_id)
            )
        required = profile["required_fields"]
        known = {k: f.value for k, f in memory.facts.items()}
        combined_text = (message + " " + " ".join(known.values())).casefold()
        if memory.requested_remedy:
            known["requested_resolution"] = memory.requested_remedy
        elif re.search(r"\b(?:hotel|booking|check-?in|property|stay)\b", combined_text):
            known["requested_resolution"] = (
                "Full refund of ₹[amount] to the original payment method, without cancellation deductions"
            )
        elif re.search(
            r"\b(?:refund|cancel|damaged|defective|expired|missing|wrong item|not delivered)\b",
            combined_text,
        ):
            known["requested_resolution"] = "Full refund of ₹[amount] to the original payment method"
        else:
            known["requested_resolution"] = "[Requested resolution]"
        if memory.journey.submissions:
            known["previous_complaints"] = "; ".join(
                f"{s.recipient}: {s.reference or 'reference not supplied'}"
                for s in memory.journey.submissions
            )
        missing = []
        mappings = {
            "order reference": ["order_id", "order_reference"],
            "booking reference": ["booking_id", "booking_reference"],
            "issue": ["issue_type", "problem"],
            "requested resolution": ["requested_remedy"],
            "stay dates including year": ["stay_dates"],
            "property and country": ["property_name", "transaction_country"],
        }
        for label in required:
            if label == "requested resolution" and memory.requested_remedy:
                continue
            keys = mappings.get(label, [])
            if not keys or not any(known.get(key) for key in keys):
                missing.append(label)
        channel = chosen.channel
        if re.search(r"\bchat\b", message, re.I) and chosen.recipient_id not in {"commission"}:
            channel = "chat"
        elif re.search(r"\bemail\b|\bletter\b", message, re.I) and chosen.recipient_id not in {
            "commission"
        }:
            channel = "email"
        spec = DraftSpecification(
            recipient_id=chosen.recipient_id,
            route_id=chosen.route_id,
            channel=channel,
            purpose=chosen.title,
            case_version=memory.version,
            required_fields=required,
            known_details=known,
            missing_details=missing,
            evidence_names=[
                str(e.get("document_name") or "Evidence document") for e in memory.evidence
            ],
            presentation=self.renderers[channel].presentation(),
        )
        memory.last_draft_spec = spec
        return spec
