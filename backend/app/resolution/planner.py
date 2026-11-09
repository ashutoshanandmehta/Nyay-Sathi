"""Data-driven recipients and explainable preparation policies. Never submits."""

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from app.resolution.models import (
    CostEstimate,
    EligibilityResult,
    Recommendation,
    RouteOption,
    utc_now,
)

_backend_root = Path(__file__).resolve().parents[2]
_data_root = (_backend_root / "data") if (_backend_root / "data").exists() else (_backend_root.parent / "data")
ROOT = _backend_root.parent if (_backend_root.parent / "data").exists() else _backend_root


class ChannelRegistry:
    def __init__(self, path=None):
        self.data = json.loads(
            (path or ROOT / "data/knowledge/recipient_playbooks_v1.json").read_text()
        )
        self.version = self.data["version"]

    def platform(self, identifier):
        return next((p for p in self.data["platforms"] if p["id"] == identifier), None)

    def authority(self, identifier):
        return next(p for p in self.data["authorities"] if p["id"] == identifier)

    def public_payload(self):
        return self.data

    def policy_passages(self):
        """Attach registered primary-source bases for route facts shown in the plan.

        These are existing approved excerpts, never generated playbook prose.
        Web discovery is still needed for any procedural details they do not cover.
        """
        path = ROOT / "data/sources/consumer_passages.json"
        return [
            p
            for p in json.loads(path.read_text())
            if p.get("source_id") in {"nch-about", "india-code-cpa-2019"}
            and p.get("passage_id") in {"nch-prelitigation", "cpa2019-s69-limitation"}
        ]


class RecipientResolver:
    def __init__(self, registry):
        self.registry = registry

    def resolve(self, memory, message):
        def identify(text):
            return [
                p["id"]
                for p in self.registry.data["platforms"]
                if any(
                    re.search(r"\b" + re.escape(alias) + r"\b", text, re.I)
                    for alias in p["aliases"]
                )
            ]

        found = identify(message)
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            return None
        previous = identify(
            " ".join(str(p.get("name", "")) for p in memory.parties)
            + " "
            + " ".join(f.value for f in memory.facts.values())
        )
        if len(previous) == 1:
            return previous[0]
        recipients = {
            e.recipient
            for e in memory.journey.events
            if e.recipient in {p["id"] for p in self.registry.data["platforms"]}
        }
        return next(iter(recipients)) if len(recipients) == 1 else None

    def canonical_recipient(self, value):
        if not value:
            return None
        lower = value.casefold()
        if "grievance" in lower and not any(
            word in lower for word in ("nch", "consumer helpline", "rbi")
        ):
            return "company_grievance"
        for identifier, terms in {
            "nch": ["nch", "national consumer helpline"],
            "commission": ["consumer commission", "consumer court"],
            "rbi": ["rbi"],
            "food_safety": ["fssai", "food safety"],
        }.items():
            if any(re.search(r"\b" + re.escape(term) + r"\b", lower) for term in terms):
                return identifier
        for profile in self.registry.data["platforms"]:
            if any(
                re.search(r"\b" + re.escape(alias) + r"\b", lower) for alias in profile["aliases"]
            ):
                return profile["id"]
        return value


class AuthorityPolicy(Protocol):
    def evaluate(self, memory, route_id: str) -> EligibilityResult: ...


class ConsumerEligibilityPolicy:
    def evaluate(self, memory, route_id):
        if memory.domain not in {"consumer", "unknown"}:
            return EligibilityResult(
                status="ineligible",
                reasons=["This issue is outside validated consumer preparation coverage."],
            )
        if memory.journey.outcome in {"settlement_reported_accepted", "pursuit_stopped"}:
            return EligibilityResult(
                status="insufficient_information",
                reasons=[
                    "The reported settlement or decision to stop must be reviewed before proposing further action."
                ],
                missing_inputs=["Whether further action is wanted and available"],
            )
        if route_id in {"support", "follow_up", "grievance"}:
            return EligibilityResult(
                status="eligible",
                reasons=[
                    "Suitable for preparing factual correspondence; no legal entitlement or successful submission is inferred."
                ],
            )
        if any(e.recipient in {"commission", "court", "rbi"} for e in memory.journey.submissions):
            return EligibilityResult(
                status="insufficient_information",
                reasons=[
                    "Another formal route may already be involved; check compatibility before parallel action."
                ],
                missing_inputs=["Existing proceedings and their status"],
            )
        missing = []
        country = memory.facts.get("transaction_country")
        if not country:
            missing.append("Indian transaction/jurisdiction connection")
        elif country.value.casefold() not in {"india", "in", "भारत"}:
            missing.append("Cross-border applicability assessment")
        if route_id == "commission":
            purpose = memory.facts.get("consumer_purpose")
            if purpose and purpose.value.casefold() not in {
                "personal",
                "personal use",
                "household",
                "self employment livelihood",
            }:
                missing.append(
                    "Assess consumer-status applicability for the reported purchase purpose"
                )
            for key, label in [
                ("consumer_purpose", "Consumer purpose"),
                ("consideration_paid", "Consideration actually paid"),
                ("cause_of_action_date", "Legally relevant cause-of-action date"),
                ("territorial_jurisdiction", "Territorial jurisdiction facts"),
            ]:
                if not memory.facts.get(key):
                    missing.append(label)
        if route_id == "rbi":
            missing.extend(
                [
                    "Covered regulated entity and specific service deficiency",
                    "Prior regulated-entity complaint and applicable scheme timing",
                ]
            )
        if missing:
            return EligibilityResult(
                status="insufficient_information",
                reasons=[
                    "Preparation can continue, but filing eligibility has not been established."
                ],
                missing_inputs=missing,
            )
        return EligibilityResult(
            status="eligible",
            reasons=[
                "Recorded inputs support considering this preparation route; recheck applicability and current filing requirements."
            ],
        )


class VersionedFeePolicy:
    def __init__(self, path=None):
        self.data = json.loads(
            (path or ROOT / "data/knowledge/resolution_rules_v1.json").read_text()
        )

    @staticmethod
    def active(rule, as_of):
        return rule["valid_from"] <= as_of and (
            not rule.get("valid_until") or as_of < rule["valid_until"]
        )

    def calculate(self, consideration, as_of=None):
        as_of = as_of or datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
        rule = self.data["fee_schedule"]
        if not self.active(rule, as_of):
            return {"amount": None, "reason": "No applicable verified fee schedule for this date."}
        try:
            amount = Decimal(str(consideration).replace(",", ""))
            if not amount.is_finite() or amount < 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            return {
                "amount": None,
                "reason": "Confirm consideration actually paid; do not use requested compensation.",
            }
        fee = next(
            value for ceiling, value in rule["slabs"] if ceiling is None or amount <= ceiling
        )
        jurisdiction = self.data["pecuniary_jurisdiction"]
        band = None
        if self.active(jurisdiction, as_of):
            band = next(
                value
                for ceiling, value in jurisdiction["slabs"]
                if ceiling is None or amount <= ceiling
            )
        return {
            "amount": str(fee),
            "reason": rule["basis"],
            "source_id": rule["source_id"],
            "source_url": rule["source_url"],
            "rule_version": self.data["version"],
            "pecuniary_band": band,
            "limitation": rule["limitation"],
        }


class TradeoffEvaluator:
    def __init__(self, fees=None):
        self.fees = fees or VersionedFeePolicy()

    def estimate(self, memory, route):
        if route in {"support", "follow_up", "grievance", "clarify"}:
            return CostEstimate(
                effort="low",
                fee_basis="No government filing is involved in preparing this company message.",
                uncertainty=["Company response and resolution time are not guaranteed."],
            )
        if route == "commission":
            fact = memory.facts.get("consideration_paid")
            fee = self.fees.calculate(fact.value if fact else None)
            return CostEstimate(
                effort="high",
                filing_fee_inr=fee["amount"],
                fee_basis=fee["reason"],
                other_costs=[
                    "Possible printing, postage, travel and execution costs where applicable",
                    "Optional professional assistance; obtain a quote before spending",
                ],
                uncertainty=[
                    "Filing fee is not total cost.",
                    "Formal eligibility and local document requirements need checking.",
                    "No individual success probability or resolution duration is available.",
                ],
                source_ids=[fee["source_id"]] if fee.get("source_id") else [],
            )
        if route == "nch":
            return CostEstimate(
                effort="medium",
                fee_basis="Verify the current official channel; no paid intermediary is required by this app.",
                uncertainty=[
                    "Pre-litigation assistance does not guarantee a remedy.",
                    "Closure/disposal is different from user-confirmed resolution.",
                ],
            )
        return CostEstimate(
            effort="medium",
            uncertainty=["Specialist suitability and current procedure require assessment."],
        )


class ResolutionPlanner:
    def __init__(self, registry=None, policy: AuthorityPolicy | None = None, costs=None):
        self.registry = registry or ChannelRegistry()
        self.policy = policy or ConsumerEligibilityPolicy()
        self.costs = costs or TradeoffEvaluator()
        self.resolver = RecipientResolver(self.registry)

    def recommend(self, memory, message, as_of=None):
        platform_id = self.resolver.resolve(memory, message)
        platform = self.registry.platform(platform_id)
        options = []
        uncertainties = []
        submissions = memory.journey.submissions
        previous = any(
            s.recipient == platform_id or s.recipient == "company_support" for s in submissions
        )
        grievance_done = any(
            s.recipient in {"company_grievance", f"{platform_id}_grievance"} for s in submissions
        )
        nch_done = any(s.recipient == "nch" for s in submissions)
        # Explicit reported actions are planning evidence, not completed filings
        # inferred from a route name. They never mutate the complaint timeline.
        reported_history = (
            message
            + " "
            + " ".join(f.value for f in memory.facts.values())
            + " "
            + " ".join(memory.actions_completed)
        )
        clauses = re.split(r"[.!?\n;]", reported_history.casefold())
        reported = [
            c
            for c in clauses
            if re.search(
                r"\b(?:i|we)\s+(?:(?:also|already|have|had)\s+)*(?:contacted|emailed|complained|filed|wrote|raised)\b",
                c,
            )
            and not re.search(r"\b(?:if|should|could|will|might|not|never)\b", c)
        ]
        grievance_done = grievance_done or any("grievance" in c for c in reported)
        previous = (
            previous
            or grievance_done
            or any("support" in c or "customer service" in c for c in reported)
        )
        nch_done = nch_done or any(
            "nch" in c or "national consumer helpline" in c for c in reported
        )
        text = (message + " " + " ".join(f.value for f in memory.facts.values())).casefold()
        payment_issue = bool(
            re.search(
                r"unauthori[sz]ed (?:debit|transaction)|payment (?:failed|failure)|debited twice|bank .*?(?:failed|refused)",
                text,
            )
        )
        food_safety = bool(
            re.search(r"contaminat|adulterat|expired food|spoiled|unsafe food|food poisoning", text)
        )
        if not platform:
            uncertainties.append(
                "The platform/recipient is not uniquely identified; do not invent a contact address."
            )
            if re.search(r"\b(?:hotel|booking|check-?in|guest|property|stay)\b", text):
                uncertainties.append(
                    "Identify the property, contracting party, country, booking conditions and payment recipient; do not assume joint liability."
                )
            if not submissions:
                options.append(
                    RouteOption(
                        route_id="support",
                        recipient_id="company_support",
                        title="Prepare an order/booking-specific request to the seller, hotel, or platform",
                        channel="email",
                        eligibility=EligibilityResult(
                            status="insufficient_information",
                            reasons=[
                                "Identify the relevant seller/platform and its official channel before sending."
                            ],
                            missing_inputs=["Correct recipient and verified contact route"],
                        ),
                        reason="Prepare a concise factual request without inventing a contact address.",
                        preparation=[
                            "Order/invoice details",
                            "What went wrong",
                            "Requested resolution",
                        ],
                        instructions=[
                            "Use the official support route associated with the order or invoice after checking the recipient."
                        ],
                        source_urls=[],
                        tradeoff=self.costs.estimate(memory, "support"),
                        priority=12,
                    )
                )
            if not grievance_done:
                options.append(
                    RouteOption(
                        route_id="grievance",
                        recipient_id="company_grievance",
                        title="Escalate to the platform or seller's official Grievance Officer if initial support does not resolve the dispute",
                        channel="email",
                        eligibility=EligibilityResult(
                            status="insufficient_information",
                            reasons=[
                                "Verify the platform's published Grievance Officer contact on its official website or booking terms before sending."
                            ],
                            missing_inputs=[
                                "Official Grievance Officer contact and prior support ticket reference"
                            ],
                        ),
                        reason="Escalate with the support ticket reference if initial support rejects or fails to resolve the request.",
                        preparation=[
                            "Order/booking reference",
                            "Prior support ticket or rejection message",
                            "Requested resolution",
                        ],
                        instructions=[
                            "Attach the initial complaint reference and any written promise or cancellation rejection when escalating to the Grievance Officer."
                        ],
                        source_urls=[],
                        tradeoff=self.costs.estimate(memory, "grievance"),
                        priority=16,
                    )
                )
        if platform and platform["family"] == "travel":
            uncertainties.append(
                "Identify the property, contracting party, country, booking conditions and payment recipient; do not assume joint liability."
            )
        if platform and (not previous or not grievance_done):
            route = "support" if not previous else "grievance"
            verified_grievance = platform.get("grievance_url")
            instructions = list(platform["instructions"])
            if previous:
                instructions = [
                    "Reuse the existing complaint reference, the last response and the unfulfilled request. Do not restart the initial complaint."
                ] + instructions
                if verified_grievance:
                    instructions.append(
                        "Consult the official published grievance mechanism for the current appropriate recipient before sending."
                    )
                else:
                    instructions.append(
                        "The exact grievance contact has not been verified here; check it in the official help channel, not a search-directory phone number."
                    )
            options.append(
                RouteOption(
                    route_id=route,
                    recipient_id=platform_id,
                    title=f"{'Prepare an initial complaint to' if route == 'support' else 'Follow up or prepare grievance escalation with'} {platform['name']}",
                    channel=platform["channel"] if route == "support" else "email",
                    eligibility=self.policy.evaluate(memory, route),
                    reason="Carry the existing complaint forward."
                    if previous
                    else "Start with an order/booking-specific factual request.",
                    preparation=platform["evidence"],
                    instructions=instructions,
                    source_urls=[platform["source_url"]],
                    tradeoff=self.costs.estimate(memory, route),
                    priority=10,
                )
            )
            if route == "support" and not grievance_done:
                grievance_instructions = [
                    "If initial support does not resolve the issue, escalate with the support ticket reference rather than starting a duplicate complaint."
                ] + list(platform["instructions"])
                if verified_grievance:
                    grievance_instructions.append(
                        "Consult the official published grievance mechanism for the current appropriate recipient before sending."
                    )
                else:
                    grievance_instructions.append(
                        "The exact grievance contact has not been verified here; check it in the official help channel, not a search-directory phone number."
                    )
                options.append(
                    RouteOption(
                        route_id="grievance",
                        recipient_id=platform_id,
                        title=f"Follow up or prepare grievance escalation with {platform['name']}",
                        channel="email",
                        eligibility=self.policy.evaluate(memory, "grievance"),
                        reason="Escalate if the initial support request is rejected or unresolved.",
                        preparation=platform["evidence"],
                        instructions=grievance_instructions,
                        source_urls=[platform["source_url"]],
                        tradeoff=self.costs.estimate(memory, "grievance"),
                        priority=15,
                    )
                )
        for route_id in (
            ["nch", "commission"]
            + (["food_safety"] if food_safety else [])
            + (["rbi"] if payment_issue else [])
        ):
            authority = self.registry.authority(route_id)
            route_key = "nch_follow_up" if route_id == "nch" and nch_done else route_id
            reason = (
                "A possible external preparation route, subject to the stated eligibility gaps."
            )
            if route_id == "nch" and nch_done:
                reason = "Review the existing NCH reference and response before considering another filing; do not duplicate the grievance."
            if route_id == "food_safety":
                reason = "A safety concern has a different purpose from an ordinary refund request."
            priority = 20 if route_id == "nch" else 40
            if route_id == "food_safety":
                priority = 0
            options.append(
                RouteOption(
                    route_id=route_key,
                    recipient_id=route_id,
                    title=authority["name"],
                    channel=authority["channel"],
                    eligibility=self.policy.evaluate(memory, route_id),
                    reason=reason,
                    preparation=authority["required_fields"],
                    instructions=authority["instructions"],
                    source_urls=[authority["source_url"]],
                    tradeoff=self.costs.estimate(memory, route_id),
                    priority=priority,
                )
            )
        if memory.journey.outcome in {"settlement_reported_accepted", "pursuit_stopped"} or (
            memory.journey.outcome == "remedy_reported_received"
            and memory.journey.satisfaction != "dissatisfied"
        ):
            uncertainties.append(
                "Confirm whether any issue remains after the reported remedy, settlement or decision to stop; further escalation is not automatic."
            )
            recommended = None
        elif memory.urgent_matters and not food_safety:
            uncertainties.append(
                "Urgent professional/safety review takes priority over ordinary complaint cost comparisons."
            )
            recommended = None
        elif any(not c.get("resolved") for c in memory.contradictions):
            uncertainties.append(
                "Resolve material contradictions before a send-ready filing or definitive route selection."
            )
            recommended = None
        else:
            # Respect an explicit destination without asserting its eligibility.
            # Safety and material ambiguity gates above still take precedence.
            explicit_route = next(
                (
                    destination
                    for pattern, destination in (
                        (r"\bnch\b|national consumer helpline", "nch"),
                        (r"consumer commission|consumer court", "commission"),
                    )
                    if re.search(pattern, message, re.I)
                ),
                None,
            )
            feasible = sorted(
                [o for o in options if o.eligibility.status != "ineligible"],
                key=lambda o: (
                    0 if o.route_id == "food_safety" else 1,
                    0 if explicit_route and o.recipient_id == explicit_route else 1,
                    o.priority,
                ),
            )
            recommended = feasible[0].route_id if feasible else None
        if not payment_issue and re.search(r"\bupi\b", text):
            uncertainties.append(
                "UPI is a payment method, not by itself a reason to use the RBI Ombudsman."
            )
        if memory.journey.preferences.budget_inr:
            uncertainties.append(
                "User budget is a spending preference, not the transaction value or a source of fee estimates."
            )
        stamp = as_of or utc_now()
        identity = hashlib.sha256(
            f"{memory.version}:{self.registry.version}:{message}:{stamp[:10]}".encode()
        ).hexdigest()[:24]
        return Recommendation(
            id=identity,
            case_version=memory.version,
            policy_version=self.registry.version + " / " + self.costs.fees.data["version"],
            assessed_at=stamp,
            recommended_route_id=recommended,
            alternatives=sorted(options, key=lambda o: o.priority),
            important_uncertainties=uncertainties,
        )
