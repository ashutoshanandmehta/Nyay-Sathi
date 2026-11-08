"""Nyay Saathi Practice Engine.

Simulates adversarial opposing parties (police officers, grievance heads, landlords, employers)
and delivers parallel defense coaching grounded in verified Indian law.
Strictly adheres to the Anti-Coaching / Zero-Fabrication rule.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.safety import is_physical_liberty_category
from app.config import get_settings
from app.practice.contracts import (
    CoachFeedback,
    PracticeScenario,
    StatutorySafeguard,
)
from app.schemas.models import CaseMemory


CRISIS_PATTERNS = re.compile(
    r"\b(?:suicid\w*|kill myself|end my life|hanging|poison)\b|"
    r"\b(?:beating (?:him|me|her) right now|torturing|custodial violence|third degree|physically assaulting)\b|"
    r"आत्महत्या|जान दे दूंगा|मारपीट कर रहे हैं|हिरासत में मार",
    re.I,
)

FABRICATION_PATTERNS = re.compile(
    r"\b(?:fake (?:bill|invoice|alibi|receipt)|forge|forged|fabricat\w*|lie to (?:police|court)|say i wasn't there|pretend i was|false alibi)\b|"
    r"झूठा बिल|झूठ बोल|फर्जी|बहाना बना",
    re.I,
)

EMOTIONAL_CONFRONTATION_PATTERNS = re.compile(
    r"\b(?:suspend you|take your job|destroy you|see you outside|corrupt cops|watch what i do)\b|"
    r"नौकरी खा जाऊंगा|सस्पेंड करवा दूंगा|बर्बाद कर दूंगा",
    re.I,
)

ADMISSION_OWNERSHIP_PATTERNS = re.compile(
    r"\b(?:it is my (?:car|vehicle|bottle|liquor|bag)|i kept it|i brought it|i knew it was there)\b|"
    r"मेरी ही गाड़ी है|मैंने ही रखा था|मुझे पता था",
    re.I,
)


class PracticeEngine:
    """Manages roleplay simulation and real-time legal argument coaching."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    def generate_scenarios(
        self,
        memory: CaseMemory | None,
        title: str = "",
        recent_messages: list[str] | None = None,
    ) -> list[PracticeScenario]:
        """Produce 2-3 tailored practice scenarios from case facts and domain."""
        domain = (memory.domain if memory else "unknown").lower()
        facts_text = " ".join([f.value for f in (memory.facts.values() if memory else [])])
        combined = f"{domain} {title} {facts_text} {' '.join(recent_messages or [])}".lower()

        scenarios: list[PracticeScenario] = []

        # 1. Criminal / Police / Custody / Bihar Prohibition
        if any(w in combined for w in ["bihar", "liquor", "alcohol", "sharab", "prohibition", "patna", "vehicle"]):
            scenarios.append(
                PracticeScenario(
                    scenario_id="bihar-police-interrogation",
                    title="Police Questioning: Vehicle Alcohol Seizure & Knowledge",
                    domain="criminal",
                    opponent_role="Investigating Officer (Sub-Inspector)",
                    setting="Police Station Interrogation Room",
                    objective="State your lack of conscious knowledge or driver custody without making contradictory statements; assert right to legal counsel.",
                    opening_statement="We intercepted the vehicle and recovered bottles of liquor inside. Under Bihar's Prohibition Act, the owner and occupants are presumed to have conscious possession. Why should we not book you under Section 30(a) and confiscate the car?",
                    key_rights=[
                        "Right to consult an advocate during questioning (BNSS Section 38)",
                        "Right to know grounds of arrest in writing (BNSS Section 47)",
                        "Penalty payment option for vehicle release (Section 56D, Bihar Prohibition Rules)",
                    ],
                    suggested_first_response="The vehicle was driven by the designated driver, and I had no conscious knowledge of any prohibited items in the luggage area. Before answering detailed questions, I exercise my right to consult our advocate under Section 38 of the BNSS.",
                )
            )

        if domain == "criminal" or any(w in combined for w in ["arrest", "police", "jail", "custody", "fir", "thana", "bail"]):
            scenarios.append(
                PracticeScenario(
                    scenario_id="criminal-bail-remand",
                    title="Bail Hearing: Opposing Police Remand & Custody",
                    domain="criminal",
                    opponent_role="Assistant Public Prosecutor",
                    setting="Judicial Magistrate First Class (JMFC) Courtroom",
                    objective="Argue for immediate bail under BNSS 480/482; demonstrate permanent community roots, no flight risk, and no recovery from personal search.",
                    opening_statement="Your Honour, the accused is involved in a serious cognizable offence. Police remand is necessary to investigate accomplices and recover further materials. Releasing the accused on bail will tamper with witnesses.",
                    key_rights=[
                        "Bail is the general rule, jail is the exception for non-capital offences",
                        "Section 480 BNSS criteria: roots in community, cooperation with probe",
                        "Section 58 BNSS mandate: production before magistrate within 24 hours",
                    ],
                    suggested_first_response="Your Honour, nothing was recovered from my personal search. I am a permanent resident with no criminal antecedents, fully willing to surrender travel documents and report daily to the police station. Continued detention serves no investigatory purpose.",
                )
            )

        # 2. Consumer / E-Commerce / Product Dispute
        if domain == "consumer" or any(w in combined for w in ["refund", "order", "delivery", "product", "seller", "amazon", "flipkart", "defective"]):
            scenarios.append(
                PracticeScenario(
                    scenario_id="consumer-support-escalation",
                    title="Customer Support Call: Refusal of Refund for Non-Delivery / Defect",
                    domain="consumer",
                    opponent_role="Senior Grievance Officer (E-Commerce Platform)",
                    setting="Escalated Telephone Support",
                    objective="Overcome assertions of 'courier OTP confirmed' or '7-day policy elapsed'; cite Consumer Protection (E-Commerce) Rules 2020.",
                    opening_statement="Our logistics report shows delivery completed with OTP verification at your location. Furthermore, your return request was logged after our 7-day app window. Company policy prohibits refunds in this case.",
                    key_rights=[
                        "Consumer Protection (E-Commerce) Rules 2020 Rule 4: Mandatory grievance redressal",
                        "Platforms cannot impose unreasonable return denial terms contrary to statutory rules",
                        "National Consumer Helpline (1915 / NCH portal) escalation right",
                    ],
                    suggested_first_response="An automated OTP delivery status does not supersede physical proof of correct handover. Under Rule 4 of the Consumer Protection (E-Commerce) Rules 2020, you are legally obligated to review delivery disputes on merits. I have documented the missing package and will log a complaint with the National Consumer Helpline if unresolved.",
                )
            )
            scenarios.append(
                PracticeScenario(
                    scenario_id="consumer-mediation-commission",
                    title="Pre-Litigation Mediation: Defective Goods & Settlement",
                    domain="consumer",
                    opponent_role="Company Legal Representative",
                    setting="District Consumer Commission Mediation Cell",
                    objective="Demand complete refund and compensation; resist low-value coupons or blanket non-disclosure waivers.",
                    opening_statement="We are prepared to offer a 25% discount coupon on your next order as an amicable gesture, provided you withdraw your complaint and sign a mutual non-disclosure agreement. Going to trial will take months.",
                    key_rights=[
                        "Right to full refund of consideration paid for defective goods (CPA 2019 Section 35)",
                        "Right to reasonable compensation for harassment and mental agony",
                        "No obligation to sign gag orders or waive statutory consumer remedies",
                    ],
                    suggested_first_response="The delivered product was defective from day one, which constitutes deficiency of service under Section 2(11) of the Consumer Protection Act. I decline promotional vouchers. I am willing to settle for a 100% refund of the purchase price and reimbursement of reasonable communication costs.",
                )
            )

        # 3. Tenancy / Security Deposit Dispute
        if domain in {"tenancy", "civil"} or any(w in combined for w in ["landlord", "tenant", "rent", "flat", "deposit", "lease"]):
            scenarios.append(
                PracticeScenario(
                    scenario_id="landlord-deposit-dispute",
                    title="Flat Handover: Contesting Unfair Security Deposit Deductions",
                    domain="tenancy",
                    opponent_role="Property Owner / Landlord",
                    setting="Apartment Handover Inspection",
                    objective="Differentiate normal wear-and-tear from actual damage; demand itemized repair receipts and timeline for deposit return.",
                    opening_statement="The walls have scuffs and the bathroom tiles are dull. Complete repainting and deep servicing will cost ₹40,000, so I am forfeiting your entire security deposit.",
                    key_rights=[
                        "Ordinary wear and tear cannot be deducted from a tenant's security deposit",
                        "Landlord must produce legitimate third-party invoices for any genuine damages",
                        "Prompt refund of deposit within the agreed notice period",
                    ],
                    suggested_first_response="Under standard tenancy law, scuffs from normal habitation constitute reasonable wear and tear, not willful damage. If you claim repairs are required, please provide formal itemized contractor quotations. Please transfer the undisputed deposit balance today.",
                )
            )

        # 4. Employment / Unpaid Wages
        if domain in {"employment", "labor"} or any(w in combined for w in ["salary", "wages", "employer", "unpaid", "resignation", "dues", "boss"]):
            scenarios.append(
                PracticeScenario(
                    scenario_id="employer-unpaid-salary",
                    title="Exit Meeting: Demanding Unpaid Wages & Settlement",
                    domain="employment",
                    opponent_role="HR Director / Managing Director",
                    setting="Company Exit & Settlement Meeting",
                    objective="Demand full disbursement of statutory wages under Code on Wages 2019 without signing coercive waivers.",
                    opening_statement="Due to sudden project cancellations, all exit settlements are paused for 90 days. If you send legal notices, we will counter-claim for breach of contract and project losses.",
                    key_rights=[
                        "Statutory wages must be paid promptly and cannot be withheld due to business difficulties (Code on Wages 2019)",
                        "Threats of retaliatory damages do not extinguish earned wages",
                        "Right to approach the Labor Commissioner / Authority under Payment of Wages laws",
                    ],
                    suggested_first_response="Earned wages for work already performed are a statutory right under the Code on Wages, 2019, and cannot be conditioned on internal company cash flow. I request my Form 16 and full-and-final settlement within 7 days, failing which I will file a claim before the Labor Authority.",
                )
            )

        # Fallback if no specific match
        if not scenarios:
            scenarios.append(
                PracticeScenario(
                    scenario_id="general-dispute-resolution",
                    title="Formal Discussion: Presenting Your Legal Position",
                    domain="general",
                    opponent_role="Opposing Representative / Officer",
                    setting="Formal Meeting Room",
                    objective="State your grievance calmly, identify facts and documents, and propose a fair solution without yielding to pressure.",
                    opening_statement="We have reviewed your request and find no merit in your claims. We do not agree to the settlement you are asking for.",
                    key_rights=[
                        "Right to fair hearing and transparent statement of reasons",
                        "Right to rely on contemporaneous documentary records",
                        "Option to escalate to relevant regulatory authority or tribunal",
                    ],
                    suggested_first_response="My claim is grounded in contemporaneous records and written communications. I am prepared to present these documents today so we can reach an amicable resolution.",
                )
            )

        return scenarios

    def evaluate_and_respond(
        self,
        scenario: PracticeScenario,
        session_history: list[dict[str, Any]],
        user_argument: str,
        language: str = "en",
    ) -> tuple[str, CoachFeedback]:
        """Analyze user's argument, provide coach critique, and generate next opponent challenge."""
        # 1. Crisis Interceptor
        if CRISIS_PATTERNS.search(user_argument):
            feedback = CoachFeedback(
                assessment="risky_admission",
                strengths=[],
                vulnerabilities=["Immediate physical harm or safety crisis indicated."],
                statutory_safeguards=[],
                suggested_phrasing="Stop argument simulation immediately. Prioritize physical safety and contact emergency authorities.",
                is_crisis=True,
                crisis_text="If you or someone else is in immediate danger or facing custodial abuse, stop this practice drill. Call 112 (National Emergency Helpline) immediately or contact the District Legal Services Authority (DLSA / NALSA 15100).",
            )
            opponent_reply = "[Simulation Halted: Emergency Safety Protocol Activated]"
            return opponent_reply, feedback

        # 2. Anti-Fabrication Check
        fabrication_warning = None
        if FABRICATION_PATTERNS.search(user_argument):
            fabrication_warning = (
                "Anti-Coaching Warning: Never fabricate facts, alibis, or documents. "
                "Giving false statements to police or judicial authorities is a criminal offence under Indian law. "
                "Maintain complete factual honesty and require the other side to prove their allegations."
            )

        # 3. Analyze Argument Strengths and Vulnerabilities
        strengths: list[str] = []
        vulnerabilities: list[str] = []
        safeguards: list[StatutorySafeguard] = []

        is_calm = not bool(EMOTIONAL_CONFRONTATION_PATTERNS.search(user_argument))
        has_legal_or_doc_ref = any(
            w in user_argument.lower()
            for w in ["section", "act", "advocate", "lawyer", "receipt", "written", "record", "rule", "proof"]
        )

        if is_calm:
            strengths.append("Maintained composed, professional tone without personal threats or agitation.")
        else:
            vulnerabilities.append("Used confrontational language or emotional threats. In real hearings, this undermines credibility and invites hostile counter-actions.")

        if has_legal_or_doc_ref:
            strengths.append("Referenced specific rights, statutory provisions, or documentary records.")

        # Domain-specific coaching & traps
        if scenario.domain == "criminal":
            if ADMISSION_OWNERSHIP_PATTERNS.search(user_argument):
                vulnerabilities.append(
                    "Trap Warning: Inadvertently admitted ownership or knowledge of the vehicle/contents without qualification. "
                    "In contraband cases, distinguish between bare registered ownership, driver custody, and conscious possession."
                )
            if "lawyer" in user_argument.lower() or "advocate" in user_argument.lower() or "38" in user_argument:
                strengths.append("Effectively invoked the constitutional and statutory right to legal counsel.")
            else:
                vulnerabilities.append("Did not mention your right to meet an advocate under BNSS Section 38 before answering detailed questions.")

            safeguards.append(
                StatutorySafeguard(
                    section="Section 38",
                    act="BNSS 2023",
                    title="Right of arrested person to meet advocate of his choice during interrogation",
                    relevance="You are entitled to consult your advocate throughout the inquiry process.",
                )
            )
            safeguards.append(
                StatutorySafeguard(
                    section="Section 47",
                    act="BNSS 2023",
                    title="Person arrested to be informed of grounds of arrest and right to bail",
                    relevance="Police must communicate full particulars of the offence in writing.",
                )
            )

        elif scenario.domain == "consumer":
            if "nch" in user_argument.lower() or "1915" in user_argument or "consumer" in user_argument.lower():
                strengths.append("Strategically leveraged escalation to the National Consumer Helpline (NCH 1915).")
            safeguards.append(
                StatutorySafeguard(
                    section="Rule 4",
                    act="Consumer Protection (E-Commerce) Rules, 2020",
                    title="Consumer Grievance Redressal Mechanism",
                    relevance="Entities must acknowledge grievances within 48 hours and resolve within 1 month.",
                )
            )

        elif scenario.domain == "tenancy":
            if "wear and tear" in user_argument.lower() or "invoice" in user_argument.lower():
                strengths.append("Accurately separated normal wear-and-tear from property damage.")
            safeguards.append(
                StatutorySafeguard(
                    section="Tenancy Precedent",
                    act="General Tenancy Jurisprudence",
                    title="Wear and Tear Doctrine",
                    relevance="Landlords cannot deduct routine maintenance or aging costs from deposit.",
                )
            )

        elif scenario.domain == "employment":
            if "code on wages" in user_argument.lower() or "labor" in user_argument.lower():
                strengths.append("Asserted statutory wages protection under the Code on Wages.")
            safeguards.append(
                StatutorySafeguard(
                    section="Section 18 & 24",
                    act="Code on Wages, 2019",
                    title="Deductions and Time Limit for Payment of Wages",
                    relevance="Wages must be paid by the 7th-10th of following month and cannot be arbitrarily docked.",
                )
            )

        # Determine Assessment
        if vulnerabilities and any("Trap Warning" in v for v in vulnerabilities):
            assessment = "risky_admission"
        elif vulnerabilities:
            assessment = "caution"
        else:
            assessment = "strong"

        # Suggested Truthful Phrasing
        if scenario.domain == "criminal":
            suggested = (
                "I reiterate that I had no conscious knowledge of any prohibited items, "
                "which were located in an area under the driver's custody. "
                "I request the grounds of detention in writing under Section 47 of BNSS, "
                "and wish to consult our advocate under Section 38 before signing any statement."
            )
        elif scenario.domain == "consumer":
            suggested = (
                "Automated delivery marks do not resolve genuine non-receipt disputes. "
                "Under the Consumer Protection (E-Commerce) Rules 2020, you must investigate "
                "the courier's GPS proof and recipient signature. Please initiate the refund or provide a formal complaint reference."
            )
        elif scenario.domain == "tenancy":
            suggested = (
                "Wall discoloration after two years of tenancy is normal wear and tear. "
                "Please provide itemized repair invoices from licensed contractors. "
                "I request the refund of the undisputed deposit balance within 7 business days."
            )
        else:
            suggested = (
                "I stand by the factual records already shared in writing. "
                "I seek an amicable settlement in accordance with statutory rules, "
                "failing which I will escalate to the designated regulatory grievance cell."
            )

        feedback = CoachFeedback(
            assessment=assessment,
            strengths=strengths,
            vulnerabilities=vulnerabilities,
            statutory_safeguards=safeguards,
            suggested_phrasing=suggested,
            anti_fabrication_warning=fabrication_warning,
            is_crisis=False,
        )

        # 4. Generate Opposing Counter-Challenge
        turn_count = len(session_history) + 1
        opponent_reply = self._generate_opponent_reply(scenario, user_argument, turn_count)

        return opponent_reply, feedback

    def _generate_opponent_reply(
        self, scenario: PracticeScenario, user_argument: str, turn_index: int
    ) -> str:
        """Create a realistic, challenging, in-character opposing turn."""
        arg_lower = user_argument.lower()

        if scenario.domain == "criminal":
            if turn_index == 1:
                return (
                    "Saying you didn't know is the standard defense everyone uses at the checkpoint. "
                    "The car was traveling under your direction, and the boot wasn't locked separately. "
                    "Who hired the driver, who paid the fuel, and why didn't you inspect what went into your own vehicle?"
                )
            elif "lawyer" in arg_lower or "advocate" in arg_lower:
                return (
                    "You will have every right to consult your counsel at the appropriate stage. "
                    "Right now, we are completing the inventory search memo and seizing the vehicle. "
                    "Do you admit or deny that you were an occupant of this vehicle when the recovery occurred?"
                )
            else:
                return (
                    "If you claim the driver was solely responsible, where are his identity documents, "
                    "license, and trip sheet? If you cannot produce evidence of independent custody, "
                    "the presumption under the Special Act remains with the occupants."
                )

        elif scenario.domain == "consumer":
            if turn_index == 1:
                return (
                    "The courier log shows an exact GPS ping at your gate and delivery was signed off. "
                    "Our app clearly states all return windows close at 7 days. "
                    "Why did you wait until after the window closed to contact our support desk?"
                )
            elif "nch" in arg_lower or "rules" in arg_lower or "consumer" in arg_lower:
                return (
                    "You are welcome to approach any forum, but our seller agreement limits our platform liability "
                    "once a carrier marks delivery. Can you provide CCTV footage or an unboxing video proving the box was empty?"
                )
            else:
                return (
                    "We have reviewed the courier's internal investigation and they stand by the delivery. "
                    "We can at most offer a one-time courtesy shipping voucher, but a bank refund is not possible under our terms."
                )

        elif scenario.domain == "tenancy":
            if turn_index == 1:
                return (
                    "The flat was freshly painted when you moved in. Normal wear-and-tear doesn't include "
                    "nail holes, furniture scrapes, and stained grout. Repainting costs money. "
                    "Did you document the condition of the walls in writing when you took possession?"
                )
            else:
                return (
                    "I am taking quotes from my usual building painter. If you want to dispute the amount, "
                    "you'll have to wait until he finishes the job next month before I calculate what's left of your deposit."
                )

        elif scenario.domain == "employment":
            if turn_index == 1:
                return (
                    "The company is in an unexpected cash crunch because clients haven't paid their milestone bills. "
                    "Everyone's settlement is delayed, not just yours. If you take an aggressive legal route, "
                    "we will review your project records for incomplete deliverables and counter-claim for damages."
                )
            else:
                return (
                    "If you want immediate payment, we can offer 60% of your pending dues as a final full settlement "
                    "if you sign our standard mutual waiver. Otherwise, you can wait for the routine 90-day accounting cycle."
                )

        return (
            "We have noted your points, but our position remains unchanged. "
            "Unless you can produce concrete documentary evidence supporting your position today, "
            "we cannot entertain this settlement."
        )
