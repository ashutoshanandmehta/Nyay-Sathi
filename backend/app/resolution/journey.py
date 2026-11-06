"""Append-only reports with derived current state. No inferred filing or remedy."""

import hashlib
import re
from datetime import datetime

from app.resolution.models import (
    Commitment,
    ComplaintEvent,
    EventType,
    JourneyProposal,
    Submission,
    utc_now,
)


class ComplaintJourneyService:
    def apply(self, journey, proposals, *, message_id, evidence, at=None, source_text=None):
        at = at or utc_now()
        authorised = {item["id"] for item in evidence}
        changed = False
        for proposal in proposals:
            item = JourneyProposal.model_validate(proposal)
            source = message_id
            status = "user_reported"
            supported_text = source_text
            if item.source_type == "document":
                if item.source_id not in authorised:
                    continue
                excerpts = [
                    excerpt
                    for excerpt in evidence
                    if excerpt["id"] == item.source_id
                    and (item.page is None or excerpt.get("page") == item.page)
                ]
                if not excerpts:
                    continue
                excerpt = excerpts[0]
                source = item.source_id
                status = "documentary_statement"
                supported_text = excerpt.get("text", "")
                if item.page is not None and item.page != excerpt.get("page"):
                    continue
            if item.supersedes_id and not any(e.id == item.supersedes_id for e in journey.events):
                continue
            # Accept only explicit ISO timestamps/dates. Historical years are never supplied by this service.
            for field in ("occurred_at", "promised_by"):
                value = getattr(item, field)
                if value:
                    try:
                        parsed = datetime.fromisoformat(value)
                        representations = [
                            value,
                            parsed.date().isoformat(),
                            parsed.strftime("%d %B %Y"),
                            parsed.strftime("%d %b %Y"),
                            parsed.strftime("%d/%m/%Y"),
                            parsed.strftime("%d-%m-%Y"),
                        ]
                        if supported_text is not None and not any(
                            representation.casefold() in supported_text.casefold()
                            for representation in representations
                        ):
                            item = item.model_copy(update={field: None})
                    except ValueError:
                        item = item.model_copy(update={field: None})
            digest = hashlib.sha256(
                f"{source}:{item.event_type}:{item.description}:{item.reference}".encode()
            ).hexdigest()[:24]
            if any(e.id == digest for e in journey.events):
                continue
            payload = item.model_dump(exclude={"source_id"})
            journey.events.append(
                ComplaintEvent(
                    **payload, id=digest, source_id=source, recorded_at=at, evidence_status=status
                )
            )
            changed = True
        if changed:
            for recommendation in journey.recommendations:
                recommendation.stale = True
        self.project(journey, at)
        return changed

    @staticmethod
    def active_events(journey):
        superseded = {e.supersedes_id for e in journey.events if e.supersedes_id}
        return [e for e in journey.events if e.id not in superseded]

    def project(self, journey, at):
        events = self.active_events(journey)
        journey.submissions = [
            Submission(
                id=e.id,
                recipient=e.recipient or "Recipient not identified",
                channel=e.channel,
                submitted_at=e.occurred_at,
                reference=e.reference,
                event_id=e.id,
            )
            for e in events
            if e.event_type == EventType.SUBMITTED
        ]
        journey.responses = [
            {
                "event_id": e.id,
                "recipient": e.recipient,
                "description": e.description,
                "occurred_at": e.occurred_at,
                "status": e.evidence_status,
            }
            for e in events
            if e.event_type in {EventType.RESPONSE, EventType.REJECTED, EventType.CLOSED}
        ]
        journey.commitments = []
        for event in events:
            if event.event_type != EventType.PROMISED:
                continue
            later_received = any(
                e.event_type == EventType.CREDITED
                and e.recorded_at >= event.recorded_at
                and e.recipient == event.recipient
                for e in events
            )
            state = "date_unknown" if not event.promised_by else "pending"
            if event.promised_by and event.promised_by[:10] < at[:10]:
                state = "past_reported_target"
            if later_received:
                state = "remedy_reported_received"
            journey.commitments.append(
                Commitment(
                    event_id=event.id,
                    recipient=event.recipient,
                    description=event.description,
                    due_at=event.promised_by,
                    status=state,
                )
            )
        journey.outcome = "unknown"
        for event in events:
            journey.outcome = {
                EventType.PROMISED: "promised_pending",
                EventType.PROCESSED: "processed_not_credit_verified",
                EventType.CREDITED: "remedy_reported_received",
                EventType.REJECTED: "unresolved_rejected",
                EventType.CLOSED: "closed_by_recipient_outcome_unknown",
                EventType.PARTIAL: "partially_resolved",
                EventType.SETTLED: "settlement_reported_accepted",
                EventType.STOPPED: "pursuit_stopped",
            }.get(event.event_type, journey.outcome)
        # Satisfaction is reported independently; never derived from a ticket label.


def deterministic_journey_updates(text, recipient=None):
    """Conservative offline fallback. Suggestions and negated actions do not become submissions."""
    lower = text.casefold()
    result = []
    patterns = [
        (
            EventType.SUBMITTED,
            r"\b(?:i (?:already )?(?:complained|contacted|emailed|filed)|i have (?:already )?(?:complained|contacted|filed)|maine .*?(?:complaint|shikayat))\b",
        ),
        (
            EventType.CLOSED,
            r"\b(?:they|support|platform|company) (?:have |has )?(?:closed|marked .*?closed)\b",
        ),
        (
            EventType.PROMISED,
            r"\b(?:they|seller|support|platform|company) (?:have |has )?promised\b",
        ),
        (
            EventType.REJECTED,
            r"\b(?:they|seller|support|platform|company) (?:have |has )?(?:refused|rejected)\b",
        ),
        (
            EventType.CREDITED,
            r"\b(?:i received (?:the |my )?refund|refund (?:was |has been )?credited|money (?:has )?reached my account)\b",
        ),
        (
            EventType.PROCESSED,
            r"\b(?:they (?:say|said) .*?refund.*?processed|refund (?:was|has been) processed)\b",
        ),
        (EventType.SETTLED, r"\bi (?:have )?accepted (?:the |a )?(?:settlement|offer)\b"),
        (EventType.STOPPED, r"\bi (?:want to stop|do not want to pursue|don't want to pursue)\b"),
    ]
    for event_type, pattern in patterns:
        match = re.search(pattern, lower)
        if (
            event_type == EventType.SUBMITTED
            and match
            and re.search(r"\bif\s*$", lower[max(0, match.start() - 5) : match.start()])
        ):
            continue
        if event_type == EventType.CREDITED and re.search(
            r"(?:not|never|n't)\s+(?:been\s+)?(?:credited|received)|(?:refund|money).{0,15}(?:has not|was not|never)",
            lower,
        ):
            continue
        if match:
            sentence_end = re.search(r"[.!?\n]", text[match.end() :])
            end = match.end() + sentence_end.end() if sentence_end else len(text)
            reference = re.search(
                r"(?:ticket|reference|complaint)(?:\s+(?:id|number|no\.?))?\s*[:#]\s*([\w-]+)",
                text,
                re.I,
            )
            result.append(
                (
                    match.start(),
                    JourneyProposal(
                        event_type=event_type,
                        description=text[match.start() : end].strip()[:1500],
                        recipient=recipient,
                        reference=reference.group(1) if reference else None,
                        channel="email"
                        if "email" in lower
                        else "chat"
                        if "chat" in lower
                        else "unknown",
                    ),
                )
            )
    # Preserve the user's narrative order when several events arrive together.
    # Pattern-list ordering must not make an earlier promise override closure.
    return [proposal for _, proposal in sorted(result, key=lambda item: item[0])]
