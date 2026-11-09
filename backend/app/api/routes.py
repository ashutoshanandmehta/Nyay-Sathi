import asyncio
import base64
import json
import logging
import re
import wave
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.types import Overwrite
from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.db import Database, MemoryConflict, now
from app.escalation.brief import formalize
from app.escalation.bundle import build_escalation_bundle
from app.escalation.documents import write_bundle_docx, write_bundle_pdf
from app.practice.contracts import (
    PracticeExportRequest,
    PracticeScenario,
    PracticeSessionCreate,
    PracticeTurnRequest,
    RoleplayChatRequest,
    RoleplayChatResponse,
    RoleplaySetupResponse,
    RoleplayStartRequest,
    RoleplayStartResponse,
)
from app.practice.engine import PracticeEngine, session_case, session_objective
from app.resolution.documents import CorrespondenceExporter
from app.routing.contracts import CaseUpdateProposal, RequestInterpretation
from app.routing.policy import CapabilityRegistry
from app.routing.state_manager import CaseStateManager, UnauthorizedCaseUpdate
from app.schemas.models import (
    CaseMemory,
    ConversationCreate,
    ConversationRename,
    MessageCreate,
    TurnResponse,
)
from app.security.ownership import (
    OwnerContext,
    csrf_guard,
    owner_context,
    rotate_owner_credential,
    set_owner_cookies,
)
from app.security.privacy import (
    export_encrypted_transfer_bundle,
    import_encrypted_transfer_bundle,
    retention_status,
)
from app.services.context_builder import ContextBuilder
from app.services.documents import process_upload
from app.services.exports import export_payload, write_docx, write_json, write_pdf
from app.services.turn_persistence import RequestConflict, TurnPersistence, payload_hash
from app.services.turns import TurnCoordinator

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
turns = TurnCoordinator()


class AttachmentCorrection(BaseModel):
    extracted_text: str = Field(max_length=100_000)


class AttachmentConsentBody(BaseModel):
    consented: bool


class QualityConsentBody(BaseModel):
    opted_in: bool


class DraftBody(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=50_000)
    expected_version: int | None = None


class UserActionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    status: Literal["pending", "completed", "skipped"] = "completed"
    notes: str = Field(default="", max_length=2000)
    occurred_at: str | None = None


class UserActionUpdate(BaseModel):
    status: Literal["pending", "completed", "skipped"]
    notes: str | None = Field(default=None, max_length=2000)


class SubmissionStepCreate(BaseModel):
    target_channel: str = Field(min_length=2, max_length=160)
    step: Literal["previewed", "consented", "submitted_by_user", "receipt_captured"]
    draft_id: str | None = None
    receipt_reference: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)


class TransferExportRequest(BaseModel):
    passphrase: str = Field(min_length=8, max_length=200)


class TransferImportRequest(BaseModel):
    passphrase: str = Field(min_length=8, max_length=200)
    bundle: dict[str, Any]


def db(request: Request) -> Database:
    return request.app.state.db


def live_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def clean_conversation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        k: row.get(k)
        for k in ("id", "title", "language", "created_at", "updated_at", "last_message")
    }


def http_not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc.args[0]))


@router.get("/bootstrap")
def bootstrap(
    request: Request,
    response: Response,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    cfg = live_settings(request)
    set_owner_cookies(response, owner, cfg)
    return {
        "product": "Nyay Saathi",
        "ai_configured": cfg.ai_configured,
        "devspace_enabled": cfg.devspace_enabled,
        "supported_languages": ["en", "hi", "hinglish"],
        "capabilities": CapabilityRegistry(cfg).snapshot(),
        "privacy_notice": (
            "Guest-only pseudonymous access: no phone or email is collected. Sensitive case records are "
            "envelope-encrypted per case and retained for up to 1 year of inactivity unless deleted earlier. "
            "Losing both your browser credential and encrypted transfer package permanently removes access."
        ),
        "disclaimer": "AI legal-resolution copilot with licensed-human escalation; prepares analysis and documents without filing, signing, paying, or representing you.",
    }


@router.post("/privacy/rotate-credential", dependencies=[Depends(csrf_guard)])
def rotate_credential(
    request: Request,
    response: Response,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    cfg = live_settings(request)
    rotated = rotate_owner_credential(db(request), owner.owner_id, cfg)
    set_owner_cookies(response, rotated, cfg)
    return {"rotated": True, "csrf_token": rotated.new_csrf_token}


@router.get("/conversations")
def conversations(request: Request, owner: Annotated[OwnerContext, Depends(owner_context)]):
    return [clean_conversation(x) for x in db(request).list_conversations(owner.owner_id)]


@router.post("/conversations", dependencies=[Depends(csrf_guard)])
def create_conversation(
    body: ConversationCreate,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    return clean_conversation(db(request).create_conversation(owner.owner_id, body.language.value))


@router.get("/conversations/{conversation_id}")
def conversation_detail(
    conversation_id: str, request: Request, owner: Annotated[OwnerContext, Depends(owner_context)]
):
    try:
        database = db(request)
        cfg = live_settings(request)
        conv = database.get_conversation(owner.owner_id, conversation_id)
        memory, summary = database.load_memory(owner.owner_id, conversation_id)
        return {
            "conversation": clean_conversation(conv),
            "messages": database.messages(owner.owner_id, conversation_id),
            "safety_messages": database.safety_messages(owner.owner_id, conversation_id),
            "case_memory": memory.model_dump(mode="json"),
            "case_proposals": database.case_proposals(owner.owner_id, conversation_id),
            "staged_patches": database.staged_patches(owner.owner_id, conversation_id),
            "summary": summary,
            "attachments": [
                {**a, "stored_path": None}
                for a in database.attachments(owner.owner_id, conversation_id)
            ],
            "drafts": database.drafts(owner.owner_id, conversation_id),
            "user_actions": database.list_user_actions(owner.owner_id, conversation_id),
            "submission_steps": database.list_submission_steps(owner.owner_id, conversation_id),
            "retention": retention_status(conv["updated_at"], cfg.retention_inactivity_days),
            "encryption": database.case_key_metadata(owner.owner_id, conversation_id),
            "quality_review_consent": database.get_quality_review_consent(
                owner.owner_id, conversation_id
            ),
        }
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.patch("/conversations/{conversation_id}", dependencies=[Depends(csrf_guard)])
def rename_conversation(
    conversation_id: str,
    body: ConversationRename,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        db(request).rename_conversation(owner.owner_id, conversation_id, body.title.strip())
        return {"ok": True}
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.delete("/conversations/{conversation_id}", dependencies=[Depends(csrf_guard)])
def delete_conversation(
    conversation_id: str, request: Request, owner: Annotated[OwnerContext, Depends(owner_context)]
):
    try:
        files = db(request).delete_conversation(owner.owner_id, conversation_id)
    except KeyError as exc:
        raise http_not_found(exc) from exc
    for item in files:
        Path(item).unlink(missing_ok=True)
    for item in live_settings(request).export_path.glob(f"{conversation_id}-*"):
        item.unlink(missing_ok=True)
    request.app.state.assistant_graph.delete_thread(f"{owner.owner_id}:{conversation_id}")
    return {"deleted": True, "cryptographic_key_destroyed": True, "physical_purge_scheduled": True}


def _lawyer_bundle(request: Request, owner: OwnerContext, conversation_id: str) -> dict[str, Any]:
    """The bundle in formal wording, cached per case state so the panel and the download
    show the same text and repeated clicks make no new model call."""
    database = db(request)
    conv = database.get_conversation(owner.owner_id, conversation_id)
    memory, summary = database.load_memory(owner.owner_id, conversation_id)
    messages = database.messages(owner.owner_id, conversation_id)
    attachments = database.attachments(owner.owner_id, conversation_id)
    drafts = database.drafts(owner.owner_id, conversation_id)
    safety = database.safety_messages(owner.owner_id, conversation_id)
    actions = database.list_user_actions(owner.owner_id, conversation_id)
    submissions = database.list_submission_steps(owner.owner_id, conversation_id)
    cache = getattr(request.app.state, "bundle_cache", None)
    if cache is None:
        cache = request.app.state.bundle_cache = {}
    key = (
        owner.owner_id,
        conversation_id,
        memory.version,
        len(messages),
        tuple((d["id"], d["version"]) for d in drafts),
        len(attachments),
        len(safety),
        tuple((a["id"], a["status"], a.get("updated_at")) for a in actions),
        len(submissions),
    )
    if key in cache:
        return cache[key]
    bundle = build_escalation_bundle(
        conversation=conv,
        memory=memory,
        summary=summary,
        messages=messages,
        attachments=attachments,
        drafts=drafts,
        safety_messages=safety,
        user_actions=actions,
        submission_steps=submissions,
    )
    cfg = live_settings(request)
    if cfg.ai_configured:
        _check_model_circuit(request, owner, conversation_id, cfg)
        bundle, calls = formalize(bundle, cfg)
        abuse = getattr(request.app.state, "abuse", None)
        if abuse is not None:
            abuse.record_turn_usage(owner.owner_id, calls)
    if len(cache) >= 256:
        cache.pop(next(iter(cache)))
    cache[key] = bundle
    return bundle


@router.get("/conversations/{conversation_id}/escalation-bundle")
def get_escalation_bundle(
    conversation_id: str, request: Request, owner: Annotated[OwnerContext, Depends(owner_context)]
):
    try:
        return _lawyer_bundle(request, owner, conversation_id)
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.get("/conversations/{conversation_id}/escalation-bundle/export/{format}")
def export_escalation_bundle(
    conversation_id: str,
    format: str,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    if format not in {"pdf", "docx"}:
        raise HTTPException(status_code=404, detail="Unsupported export format")
    try:
        bundle = _lawyer_bundle(request, owner, conversation_id)
    except KeyError as exc:
        raise http_not_found(exc) from exc
    target = live_settings(request).export_path / f"{conversation_id}-lawyer-bundle.{format}"
    {"pdf": write_bundle_pdf, "docx": write_bundle_docx}[format](target, bundle)
    media = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }[format]
    return FileResponse(
        target,
        media_type=media,
        filename=f"nyay-saathi-lawyer-bundle.{format}",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/conversations/{conversation_id}/actions", dependencies=[Depends(csrf_guard)])
def create_user_action(
    conversation_id: str,
    body: UserActionCreate,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        return db(request).add_user_action(
            owner.owner_id,
            conversation_id,
            body.title.strip(),
            body.status,
            body.notes.strip(),
            body.occurred_at,
        )
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.patch(
    "/conversations/{conversation_id}/actions/{action_id}", dependencies=[Depends(csrf_guard)]
)
def update_user_action(
    conversation_id: str,
    action_id: str,
    body: UserActionUpdate,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        return db(request).update_user_action(
            owner.owner_id, conversation_id, action_id, body.status, body.notes
        )
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post("/conversations/{conversation_id}/submissions", dependencies=[Depends(csrf_guard)])
def create_submission_step(
    conversation_id: str,
    body: SubmissionStepCreate,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        return db(request).record_submission_step(
            owner.owner_id,
            conversation_id,
            target_channel=body.target_channel.strip(),
            step=body.step,
            draft_id=body.draft_id,
            receipt_reference=body.receipt_reference.strip(),
            notes=body.notes.strip(),
        )
    except KeyError as exc:
        raise http_not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/conversations/{conversation_id}/attachments/{attachment_id}/consent",
    dependencies=[Depends(csrf_guard)],
)
def set_attachment_consent(
    conversation_id: str,
    attachment_id: str,
    body: AttachmentConsentBody,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        status_str = "consented" if body.consented else "withheld"
        return db(request).set_attachment_consent(
            owner.owner_id, conversation_id, attachment_id, status_str
        )
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post(
    "/conversations/{conversation_id}/quality-consent", dependencies=[Depends(csrf_guard)]
)
def set_quality_consent(
    conversation_id: str,
    body: QualityConsentBody,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        return db(request).set_quality_review_consent(
            owner.owner_id, conversation_id, body.opted_in
        )
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post(
    "/conversations/{conversation_id}/transfer/export", dependencies=[Depends(csrf_guard)]
)
def export_transfer_package(
    conversation_id: str,
    body: TransferExportRequest,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        database = db(request)
        conv = database.get_conversation(owner.owner_id, conversation_id)
        memory, summary = database.load_memory(owner.owner_id, conversation_id)
        snapshot = {
            "conversation": clean_conversation(conv),
            "case_memory": memory.model_dump(mode="json"),
            "summary": summary,
            "messages": database.messages(owner.owner_id, conversation_id),
            "drafts": database.drafts(owner.owner_id, conversation_id),
            "user_actions": database.list_user_actions(owner.owner_id, conversation_id),
        }
        database.record_security_audit(
            "encrypted_case_transfer_exported",
            owner_id=owner.owner_id,
            conversation_id=conversation_id,
        )
        return export_encrypted_transfer_bundle(snapshot, body.passphrase)
    except KeyError as exc:
        raise http_not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/conversations/transfer/import", dependencies=[Depends(csrf_guard)])
def import_transfer_package(
    body: TransferImportRequest,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        snapshot = import_encrypted_transfer_bundle(body.bundle, body.passphrase)
        restored = db(request).restore_transferred_case(owner.owner_id, snapshot)
        return {"imported": True, "conversation": clean_conversation(restored)}
    except ValueError as exc:
        db(request).record_security_audit(
            "encrypted_case_transfer_import_failed", owner_id=owner.owner_id
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _check_model_circuit(
    request: Request, owner: OwnerContext, conversation_id: str, cfg: Settings
) -> None:
    abuse = getattr(request.app.state, "abuse", None)
    if abuse is None:
        return
    cb_ok, cb_reason = abuse.check_circuit_breaker(owner.owner_id, cfg)
    if not cb_ok:
        db(request).record_security_audit(
            "model_circuit_breaker_tripped",
            owner_id=owner.owner_id,
            conversation_id=conversation_id,
            metadata={"reason": cb_reason},
        )
        raise HTTPException(status_code=503, detail=cb_reason)


def _practice_engine(
    request: Request, owner: OwnerContext, conversation_id: str, *, with_index: bool = False
) -> PracticeEngine:
    """Practice shares the hourly model-call limits and, for drills, the agent's legal index."""
    cfg = live_settings(request)
    _check_model_circuit(request, owner, conversation_id, cfg)
    index = None
    if with_index:
        state = request.app.state
        research = getattr(getattr(state, "assistant_graph", None), "research", None)
        index = getattr(research, "knowledge_index", None) or getattr(state, "practice_index", None)
        if index is None:
            from app.knowledge.search_index import OpenSearchLegalIndex

            index = state.practice_index = OpenSearchLegalIndex(
                cfg, getattr(state, "retriever", None)
            )
    return PracticeEngine(cfg, knowledge_index=index)


def _record_practice_usage(request: Request, owner: OwnerContext, engine: PracticeEngine) -> None:
    abuse = getattr(request.app.state, "abuse", None)
    if abuse is not None:
        abuse.record_turn_usage(owner.owner_id, engine.model_calls)


def _recent_user_messages(database: Database, owner_id: str, conversation_id: str) -> list[str]:
    msgs = database.messages(owner_id, conversation_id)
    return [m["content"] for m in msgs if m.get("role") == "user"][-3:]


@router.get("/conversations/{conversation_id}/roleplay/setup")
def get_roleplay_setup(
    conversation_id: str,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
    language: Annotated[str, Query(max_length=12)] = "en",
):
    try:
        database = db(request)
        conv = database.get_conversation(owner.owner_id, conversation_id)
        memory, _ = database.load_memory(owner.owner_id, conversation_id)
        msgs = database.messages(owner.owner_id, conversation_id)
        # Reopening the panel on an unchanged case reuses the summary instead of a new call.
        cache = getattr(request.app.state, "roleplay_setups", None)
        if cache is None:
            cache = request.app.state.roleplay_setups = {}
        key = (owner.owner_id, conversation_id, len(msgs), memory.version, language)
        if key in cache:
            return RoleplaySetupResponse(**cache[key])
        recent_user = [m["content"] for m in msgs if m.get("role") == "user"][-3:]
        engine = _practice_engine(request, owner, conversation_id)
        try:
            setup = engine.extract_roleplay_setup(
                memory, recent_user, conv.get("title", ""), language
            )
        finally:
            _record_practice_usage(request, owner, engine)
        if len(cache) >= 512:
            cache.pop(next(iter(cache)))
        cache[key] = setup
        return RoleplaySetupResponse(**setup)
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post(
    "/conversations/{conversation_id}/roleplay/start", dependencies=[Depends(csrf_guard)]
)
def start_roleplay_session(
    conversation_id: str,
    body: RoleplayStartRequest,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        database = db(request)
        conv = database.get_conversation(owner.owner_id, conversation_id)
        memory, _ = database.load_memory(owner.owner_id, conversation_id)
        engine = _practice_engine(request, owner, conversation_id)
        stakeholder = (
            (body.custom_stakeholder or "").strip() or body.stakeholder.strip() or "Opposing party"
        )
        try:
            if body.case_synopsis and body.case_synopsis.strip():
                setup = {
                    "case_title": (body.case_title or "").strip() or conv.get("title", ""),
                    "case_synopsis": body.case_synopsis.strip(),
                }
            else:
                recent_user = _recent_user_messages(database, owner.owner_id, conversation_id)
                setup = engine.extract_roleplay_setup(
                    memory, recent_user, conv.get("title", ""), body.language
                )
            # Persona setup, during the panel's setup screen: who this person really is,
            # what is and isn't their job, and their first line.
            persona = engine.build_persona(stakeholder, setup["case_synopsis"], body.language)
        finally:
            _record_practice_usage(request, owner, engine)
        opening = persona.opening_line
        scenario_slug = "roleplay-" + re.sub(r"\W+", "-", stakeholder.lower()).strip("-")
        # Synopsis and persona are kept with the session, so every turn plays the same person.
        session = database.create_practice_session(
            owner.owner_id,
            conversation_id,
            scenario_id=scenario_slug,
            title=f"Roleplay: {stakeholder}",
            domain=memory.domain or "general",
            opponent_role=stakeholder,
            setting="Direct Conversation",
            objective=session_objective(setup["case_synopsis"], persona),
            opening_statement=opening,
        )
        return RoleplayStartResponse(
            session_id=session["id"],
            stakeholder=stakeholder,
            case_title=setup["case_title"],
            case_synopsis=setup["case_synopsis"],
            opening_message=opening,
        )
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post(
    "/conversations/{conversation_id}/roleplay/chat", dependencies=[Depends(csrf_guard)]
)
def chat_roleplay_turn(
    conversation_id: str,
    body: RoleplayChatRequest,
    session_id: Annotated[str, Query()],
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        database = db(request)
        session = database.get_practice_session(owner.owner_id, conversation_id, session_id)
        synopsis, persona = session_case(session["objective"])
        engine = _practice_engine(request, owner, conversation_id, with_index=True)
        try:
            result = engine.roleplay_turn(
                session["opponent_role"],
                synopsis,
                session.get("turns", []),
                body.message,
                body.language,
                opening=session["opening_statement"],
                persona=persona,
            )
        finally:
            _record_practice_usage(request, owner, engine)
        turn = database.add_practice_turn(
            owner.owner_id,
            conversation_id,
            session_id,
            body.message,
            result.reply,
            {"in_character": result.in_character, "notice": result.notice},
        )
        return RoleplayChatResponse(**result.model_dump(), turn_index=turn["turn_index"])
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post(
    "/conversations/{conversation_id}/roleplay/chat/stream", dependencies=[Depends(csrf_guard)]
)
def stream_roleplay_turn(
    conversation_id: str,
    body: RoleplayChatRequest,
    session_id: Annotated[str, Query()],
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    """The character's reply as server-sent events: ``delta`` text, then one ``result``."""
    database = db(request)
    try:
        session = database.get_practice_session(owner.owner_id, conversation_id, session_id)
    except KeyError as exc:
        raise http_not_found(exc) from exc
    synopsis, persona = session_case(session["objective"])
    engine = _practice_engine(request, owner, conversation_id, with_index=True)

    def events():
        try:
            result = None
            for kind, value in engine.roleplay_stream(
                session["opponent_role"],
                synopsis,
                session.get("turns", []),
                body.message,
                body.language,
                opening=session["opening_statement"],
                persona=persona,
            ):
                if kind == "delta":
                    yield "event: delta\ndata: " + json.dumps({"text": value}) + "\n\n"
                else:
                    result = value
            turn = database.add_practice_turn(
                owner.owner_id,
                conversation_id,
                session_id,
                body.message,
                result.reply,
                {"in_character": result.in_character, "notice": result.notice},
            )
            payload = {**result.model_dump(), "turn_index": turn["turn_index"]}
            yield "event: result\ndata: " + json.dumps(payload) + "\n\n"
        except KeyError:
            yield 'event: error\ndata: {"status": 404, "detail": "practice_session_not_found"}\n\n'
        finally:
            _record_practice_usage(request, owner, engine)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations/{conversation_id}/practice/scenarios")
def get_practice_scenarios(
    conversation_id: str,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        database = db(request)
        conv = database.get_conversation(owner.owner_id, conversation_id)
        memory, _ = database.load_memory(owner.owner_id, conversation_id)
        msgs = database.messages(owner.owner_id, conversation_id)
        recent_user = [m["content"] for m in msgs if m.get("role") == "user"][-3:]
        engine = _practice_engine(request, owner, conversation_id, with_index=True)
        scenarios = engine.generate_scenarios(memory, conv.get("title", ""), recent_user)
        return [s.model_dump() for s in scenarios]
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post(
    "/conversations/{conversation_id}/practice/sessions", dependencies=[Depends(csrf_guard)]
)
def create_practice_session(
    conversation_id: str,
    body: PracticeSessionCreate,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        database = db(request)
        conv = database.get_conversation(owner.owner_id, conversation_id)
        memory, _ = database.load_memory(owner.owner_id, conversation_id)
        msgs = database.messages(owner.owner_id, conversation_id)
        recent_user = [m["content"] for m in msgs if m.get("role") == "user"][-3:]
        engine = _practice_engine(request, owner, conversation_id, with_index=True)
        scenarios = engine.generate_scenarios(memory, conv.get("title", ""), recent_user)

        target_sc: PracticeScenario | None = None
        if body.custom_scenario and body.custom_scenario.strip():
            desc = body.custom_scenario.strip()
            target_sc = PracticeScenario(
                scenario_id="custom",
                title=body.title or f"Custom Drill: {desc[:40]}",
                domain=memory.domain or "general",
                opponent_role=body.opponent_role or "Opposing Party / Authority",
                setting=body.setting or "Dispute Meeting",
                objective=body.objective or "Present truthful arguments and assert statutory rights",
                opening_statement=body.opening_statement
                or f"We dispute your position regarding: {desc}. What is your justification?",
            )
        else:
            target_sc = next(
                (s for s in scenarios if s.scenario_id == body.scenario_id),
                scenarios[0] if scenarios else None,
            )

        if not target_sc:
            raise HTTPException(status_code=400, detail="No valid scenario found")

        session = database.create_practice_session(
            owner.owner_id,
            conversation_id,
            target_sc.scenario_id,
            target_sc.title,
            target_sc.domain,
            target_sc.opponent_role,
            target_sc.setting,
            target_sc.objective,
            target_sc.opening_statement,
        )
        return session
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.get("/conversations/{conversation_id}/practice/sessions")
def list_practice_sessions(
    conversation_id: str,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        database = db(request)
        return database.list_practice_sessions(owner.owner_id, conversation_id)
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.get("/conversations/{conversation_id}/practice/sessions/{session_id}")
def get_practice_session(
    conversation_id: str,
    session_id: str,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        database = db(request)
        return database.get_practice_session(owner.owner_id, conversation_id, session_id)
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post(
    "/conversations/{conversation_id}/practice/sessions/{session_id}/turns",
    dependencies=[Depends(csrf_guard)],
)
def add_practice_turn(
    conversation_id: str,
    session_id: str,
    body: PracticeTurnRequest,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        database = db(request)
        session = database.get_practice_session(owner.owner_id, conversation_id, session_id)
        scenario = PracticeScenario(
            scenario_id=session["scenario_id"],
            title=session["title"],
            domain=session["domain"],
            opponent_role=session["opponent_role"],
            setting=session["setting"],
            objective=session["objective"],
            opening_statement=session["opening_statement"],
        )
        engine = _practice_engine(request, owner, conversation_id, with_index=True)
        try:
            opponent_reply, coach_feedback = engine.evaluate_and_respond(
                scenario, session.get("turns", []), body.user_argument, body.language
            )
        finally:
            _record_practice_usage(request, owner, engine)
        turn = database.add_practice_turn(
            owner.owner_id,
            conversation_id,
            session_id,
            body.user_argument,
            opponent_reply,
            coach_feedback.model_dump(),
        )
        return turn
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post(
    "/conversations/{conversation_id}/practice/sessions/{session_id}/export-actions",
    dependencies=[Depends(csrf_guard)],
)
def export_practice_actions(
    conversation_id: str,
    session_id: str,
    body: PracticeExportRequest,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        database = db(request)
        session = database.get_practice_session(owner.owner_id, conversation_id, session_id)
        count = 0
        for title in body.action_titles:
            clean = title.strip()
            if clean:
                database.add_user_action(
                    owner.owner_id,
                    conversation_id,
                    title=clean,
                    status="pending",
                    notes=f"Key argument to prepare from Practice Drill: {session['title']}",
                )
                count += 1
        database.update_practice_session_status(
            owner.owner_id, conversation_id, session_id, "completed"
        )
        return {"exported_count": count, "status": "completed"}
    except KeyError as exc:
        raise http_not_found(exc) from exc



def _title_from(text: str) -> str:
    words = re.findall(r"[\w₹-]+", text, re.UNICODE)[:6]
    return " ".join(words).strip().capitalize()[:60] or "New case"


SOURCE_FIELDS = (
    "source_id",
    "passage_id",
    "title",
    "locator",
    "text",
    "canonical_url",
    "retrieved_at",
    "limitations",
    "origin",
    "content_hash",
    "verification_status",
    "publication_date",
    "effective_date",
    "source_type",
    "jurisdiction",
)


def _message_sources(passages, keep, citations=()):
    """Message source records, numbered and ordered to match in-text "[n](#cite-n)" markers."""
    numbers = {c["passage_id"]: c["number"] for c in citations}
    records = []
    for passage in passages:
        if not keep(passage):
            continue
        record = {k: passage.get(k) for k in SOURCE_FIELDS}
        if passage["passage_id"] in numbers:
            record["citation_number"] = numbers[passage["passage_id"]]
        records.append(record)
    # Stable sort: uncited published passages keep their order after the numbered ones.
    return sorted(records, key=lambda r: r.get("citation_number", len(numbers) + 1))


async def _run_turn(
    conversation_id: str, body: MessageCreate, request: Request, owner: OwnerContext, progress=None
) -> dict[str, Any]:
    database = db(request)
    cfg = live_settings(request)
    try:
        conv = database.get_conversation(owner.owner_id, conversation_id)
    except KeyError as exc:
        raise http_not_found(exc) from exc

    abuse = getattr(request.app.state, "abuse", None)
    _check_model_circuit(request, owner, conversation_id, cfg)

    durable = TurnPersistence(database)
    digest = payload_hash(body.model_dump(mode="json"))
    try:
        execution = durable.get(owner.owner_id, conversation_id, body.request_id, digest)
        if execution and execution["status"] in {"reviewed", "committed", "completed"}:
            return durable.finalize(owner.owner_id, conversation_id, body.request_id)
        if execution and execution["status"] == "conflict":
            raise RequestConflict(
                "The case changed. Review the latest case and start a fresh turn; this request will not rerun models."
            )
    except (RequestConflict, MemoryConflict) as exc:
        if isinstance(exc, MemoryConflict):
            durable.mark(owner.owner_id, conversation_id, body.request_id, "conflict")
        raise HTTPException(status_code=409, detail=str(exc)) from None
    existing = database.find_turn(conversation_id, body.request_id)
    if existing and existing[1]["status"] != "failed":
        user, assistant = existing
        memory, _ = database.load_memory(owner.owner_id, conversation_id)
        return {
            "conversation_id": conversation_id,
            "user_message": user,
            "assistant_message": assistant,
            "case_version": memory.version,
            "sources": assistant["metadata"].get("sources", []),
            "verification": assistant["metadata"].get("verification", {}),
            "token_usage": assistant["metadata"].get("token_usage", {}),
            "ai_configured": cfg.ai_configured,
        }
    lock = turns.lock_for(owner.owner_id, conversation_id)
    if lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Another turn is still running for this case. Please retry with the same request ID.",
        )
    async with lock:
        available = database.attachments(owner.owner_id, conversation_id)
        if set(body.attachment_ids) - {a["id"] for a in available}:
            raise HTTPException(status_code=404, detail="Attachment not found in this case")
        existing = database.find_turn(conversation_id, body.request_id)
        if existing and existing[1]["status"] != "failed":
            user, assistant = existing
            memory, _ = database.load_memory(owner.owner_id, conversation_id)
            return {
                "conversation_id": conversation_id,
                "user_message": user,
                "assistant_message": assistant,
                "case_version": memory.version,
                "sources": assistant["metadata"].get("sources", []),
                "verification": assistant["metadata"].get("verification", {}),
                "token_usage": assistant["metadata"].get("token_usage", {}),
                "ai_configured": cfg.ai_configured,
            }
        if existing:
            user, _ = existing
            database.delete_failed_assistant(conversation_id, body.request_id)
        else:
            user = database.add_message(
                conversation_id,
                "user",
                body.content,
                body.request_id,
                "complete",
                {"attachment_ids": body.attachment_ids, "language": body.language},
            )
        try:
            durable.begin(owner.owner_id, conversation_id, body.request_id, digest)
        except RequestConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        memory, summary = database.load_memory(owner.owner_id, conversation_id)
        loaded_version = memory.version
        recent = database.messages(owner.owner_id, conversation_id)[-12:]
        evidence = [
            a
            for a in database.attachments(owner.owner_id, conversation_id)
            if a.get("consent_status") != "withheld"
            and (
                not cfg.require_explicit_attachment_consent
                or a.get("consent_status") == "consented"
                or a["id"] in body.attachment_ids
            )
            and (not body.attachment_ids or a["id"] in body.attachment_ids)
        ]
        context = ContextBuilder().build(
            current_message=body.content,
            memory=memory,
            summary=summary,
            recent_messages=recent,
            evidence=evidence,
        )
        context["staged_case_proposals"] = database.case_proposals(owner.owner_id, conversation_id)[
            :3
        ]
        context["current_drafts"] = [
            {
                key: draft.get(key)
                for key in ("id", "title", "content", "status", "case_version", "version")
            }
            for draft in database.drafts(owner.owner_id, conversation_id)[:2]
        ]
        user_logged_actions = database.list_user_actions(owner.owner_id, conversation_id)[:8]
        if user_logged_actions:
            context["user_tracked_actions"] = [
                {"title": act["title"], "status": act["status"], "notes": act["notes"]}
                for act in user_logged_actions
            ]
        initial = {
            "request_id": body.request_id,
            "pipeline_version": "legacy",
            "owner_id": owner.owner_id,
            "conversation_id": conversation_id,
            "message_id": user["id"],
            "current_message": body.content,
            "language": (body.language.value if body.language else conv["language"]),
            "context": context,
            "memory": memory.model_dump(mode="json"),
            "summary": summary,
            "passages": [],
            "prior_web_sources": ContextBuilder.prior_web_sources(recent),
            "research_plan": {},
            "research_status": "not_required",
            "web_sources": [],
            "request_plan": [],
            "request_coverage": [],
            "follow_up_questions": [],
            "response": "",
            "response_envelope": {},
            "feedback_review": {},
            "token_usage": {},
            "model_calls": 0,
            "revision_attempts": 0,
            "revision_succeeded": False,
            "resolution_plan": {},
            "draft_spec": {},
            "draft_content": "",
            "draft_title": "",
            "events": Overwrite([]),
            "unit_protocol": False,
            "candidate_batch": {"units": []},
            "unit_review": {},
            "reviewed_candidate_digest": "",
            "reviewed_context_digest": "",
            "verified_claim_reviews": {},
            "turn_review_findings": [],
            "staged_case_memory": {},
            "unit_outcomes": [],
            "approved_documents": [],
            "published_passage_ids": [],
            "interpretation": {},
            "task_plan": [],
            "tool_records": [],
            "case_update_allowed": False,
            "case_task_ids": [],
            "case_input": "",
        }
        try:
            args = (initial, f"{owner.owner_id}:{conversation_id}")
            kwargs = {"progress": progress} if progress is not None else {}
            result = await asyncio.to_thread(
                request.app.state.assistant_graph.invoke, *args, **kwargs
            )
        except Exception as exc:
            durable.mark(owner.owner_id, conversation_id, body.request_id, "failed")
            logger.error(
                "Turn execution failed conversation_id=%s request_id=%s error_type=%s",
                conversation_id,
                body.request_id,
                type(exc).__name__,
            )
            assistant = database.add_message(
                conversation_id,
                "assistant",
                "The assistant could not complete this turn. Your message was saved; retry with the same request ID after checking the backend configuration.",
                body.request_id,
                "failed",
                {"error_code": "turn_failed", "error_type": type(exc).__name__},
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "turn_failed",
                    "retryable": True,
                    "assistant_message_id": assistant["id"],
                },
            ) from None

        if abuse is not None:
            est_cost = float((result.get("metrics") or {}).get("known_estimated_cost_usd") or 0.0)
            abuse.record_turn_usage(
                owner.owner_id, int(result.get("model_calls", 0) or 0), est_cost
            )

        updated_memory = CaseMemory.model_validate(result["memory"])
        if result.get("pipeline_version") == "v2":
            published_ids = set(result.get("published_passage_ids", []))
            sources = _message_sources(
                result.get("passages", []),
                lambda p: p["passage_id"] in published_ids,
                result.get("citations", []),
            )
            durable.reviewed(
                owner.owner_id,
                conversation_id,
                body.request_id,
                {
                    "state": result,
                    "before": memory.model_dump(mode="json"),
                    "base_summary": summary,
                    "user": user,
                    "sources": sources,
                    "ai_configured": cfg.ai_configured,
                },
            )
            try:
                response = durable.finalize(owner.owner_id, conversation_id, body.request_id)
            except (MemoryConflict, UnauthorizedCaseUpdate) as exc:
                durable.mark(owner.owner_id, conversation_id, body.request_id, "conflict")
                raise HTTPException(status_code=409, detail=str(exc)) from None
            if conv["title"] == "New case" and len(body.content.strip()) > 15:
                database.rename_conversation(
                    owner.owner_id, conversation_id, _title_from(body.content)
                )
            return response
        try:
            graph_state = {
                k: result.get(k)
                for k in (
                    "intent",
                    "scope",
                    "urgent_reason",
                    "rewritten_query",
                    "verification",
                    "request_plan",
                    "request_coverage",
                    "feedback_review",
                    "research_plan",
                    "research_status",
                    "resolution_plan",
                    "draft_spec",
                    "interpretation",
                    "task_plan",
                    "tool_records",
                    "interpretation_status",
                    "entity_candidates",
                    "staged_case_memory",
                    "case_proposal_task_ids",
                    "unit_outcomes",
                    "publication_status",
                )
            }
            if result.get("interpretation"):
                proposal = CaseUpdateProposal(
                    base_version=loaded_version,
                    source_message_id=user["id"],
                    source_task_ids=result.get("case_task_ids", []),
                    proposed_memory=updated_memory.model_dump(mode="json"),
                    summary=result.get("summary", summary),
                )
                updated_memory = CaseStateManager(database).commit(
                    owner_id=owner.owner_id,
                    conversation_id=conversation_id,
                    before=memory,
                    proposal=proposal,
                    interpretation=RequestInterpretation.model_validate(result["interpretation"]),
                    graph_state=graph_state,
                )
            else:
                if updated_memory.model_dump() != memory.model_dump():
                    raise UnauthorizedCaseUpdate("Missing request interpretation")
                database.save_memory(
                    conversation_id,
                    updated_memory,
                    summary,
                    graph_state,
                    expected_version=loaded_version,
                    invalidate_drafts=False,
                    owner_id=owner.owner_id,
                )
        except MemoryConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except UnauthorizedCaseUpdate:
            raise HTTPException(
                status_code=409,
                detail="Case update rejected by the state policy; your existing case was preserved.",
            ) from None
        result["resolution_plan"] = graph_state.get("resolution_plan") or {}
        result["draft_spec"] = graph_state.get("draft_spec") or {}
        sources = _message_sources(
            result.get("passages", []),
            lambda p: (
                not result.get("unit_protocol")
                or not cfg.ai_configured
                or p["passage_id"] in result.get("published_passage_ids", [])
            ),
        )
        metadata = {
            "sources": sources,
            "verification": result.get("verification", {}),
            "token_usage": result.get("token_usage", {}),
            "events": result.get("events", []),
            "rewritten_query": result.get("rewritten_query"),
            "request_coverage": result.get("request_coverage", []),
            "case_version": updated_memory.version,
            "research_status": result.get("research_status"),
            "resolution_plan": result.get("resolution_plan", {}),
            "interpretation": result.get("interpretation", {}),
            "case_update_allowed": result.get("case_update_allowed", False),
            "entity_candidates": result.get("entity_candidates", []),
            "task_plan": result.get("task_plan", []),
            "tool_records": result.get("tool_records", []),
            "legal_recommendations": result.get("response_envelope", {}).get(
                "legal_recommendations", []
            ),
            "unit_outcomes": result.get("unit_outcomes", []),
            "publication_status": result.get("publication_status"),
        }
        assistant = database.add_message(
            conversation_id,
            "assistant",
            str(result.get("response", "")),
            body.request_id,
            "complete",
            metadata,
        )
        if (
            result.get("draft_generated")
            and cfg.ai_configured
            and result.get("case_update_allowed", True)
        ):
            artifacts = result.get("approved_documents") or [
                {
                    "title": result.get("draft_title", "Prepared correspondence"),
                    "content": result.get("draft_content", ""),
                }
            ]
            for artifact in artifacts:
                database.create_draft(
                    owner.owner_id,
                    conversation_id,
                    artifact["title"],
                    artifact["content"],
                    updated_memory.version,
                )
        if conv["title"] == "New case" and len(body.content.strip()) > 15:
            database.rename_conversation(owner.owner_id, conversation_id, _title_from(body.content))
        return {
            "conversation_id": conversation_id,
            "user_message": user,
            "assistant_message": assistant,
            "case_version": updated_memory.version,
            "sources": sources,
            "verification": result.get("verification", {}),
            "token_usage": result.get("token_usage", {}),
            "ai_configured": cfg.ai_configured,
        }


@router.post(
    "/conversations/{conversation_id}/turns",
    response_model=TurnResponse,
    dependencies=[Depends(csrf_guard)],
)
async def create_turn(
    conversation_id: str,
    body: MessageCreate,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    return await _run_turn(conversation_id, body, request, owner)


@router.post("/conversations/{conversation_id}/turns/stream", dependencies=[Depends(csrf_guard)])
async def stream_turn(
    conversation_id: str,
    body: MessageCreate,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        db(request).get_conversation(owner.owner_id, conversation_id)
    except KeyError as exc:
        raise http_not_found(exc) from exc

    async def events():
        yield 'event: progress\ndata: {"stage":"saving"}\n\n'
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def publish(event):
            loop.call_soon_threadsafe(queue.put_nowait, event)

        task = asyncio.create_task(_run_turn(conversation_id, body, request, owner, publish))
        try:
            while not task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                    kind = "safety" if event.get("type") == "safety" else "progress"
                    yield f"event: {kind}\ndata: " + json.dumps(event) + "\n\n"
                except TimeoutError:
                    yield ": heartbeat\n\n"
            result = await task
            yield "event: result\ndata: " + json.dumps(result, default=str) + "\n\n"
        except HTTPException as exc:
            yield (
                "event: error\ndata: "
                + json.dumps({"status": exc.status_code, "detail": exc.detail})
                + "\n\n"
            )
        finally:
            if not task.done():
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations/{conversation_id}/attachments", dependencies=[Depends(csrf_guard)])
async def upload_attachment(
    conversation_id: str,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
    consent: Annotated[Literal["consented", "withheld"], Query()] = "consented",
    file: UploadFile = File(...),
):
    database = db(request)
    cfg = live_settings(request)
    try:
        database.get_conversation(owner.owner_id, conversation_id)
        item = await process_upload(
            file,
            cfg.upload_path,
            cfg.max_upload_bytes,
            cfg.max_pdf_pages,
            pdf_engine=cfg.pdf_engine,
            encrypt_fn=lambda raw: database.encrypt_case_bytes(conversation_id, raw),
        )
        item.update({"conversation_id": conversation_id, "created_at": now()})
        saved = database.add_attachment(item, consent_status=consent)
        meta_parsed = json.loads(item["metadata_json"])
        database.record_security_audit(
            "upload_scanned_and_isolated",
            owner_id=owner.owner_id,
            conversation_id=conversation_id,
            metadata={
                "attachment_id": item["id"],
                "mime_type": item["mime_type"],
                "consent_status": consent,
                "prompt_injection_detected": bool(
                    (meta_parsed.get("security_scan") or {}).get("prompt_injection_detected")
                ),
            },
        )
        memory, summary = database.load_memory(owner.owner_id, conversation_id)
        memory.evidence.append(
            {
                "document_id": item["id"],
                "document_name": item["filename"],
                "mime_type": item["mime_type"],
                "extraction_status": item["extraction_status"],
                "status": "private_document_unassessed",
                "provenance": {
                    "source_type": "document",
                    "source_id": item["id"],
                },
                "may_support": [],
                "does_not_automatically_prove": [
                    "The truth of every statement contained in the document"
                ],
                "preservation": "Original retained in private envelope-encrypted case storage",
            }
        )
        memory.version += 1
        memory.stale_draft_ids = list(
            dict.fromkeys(
                memory.stale_draft_ids
                + database.mark_drafts_stale(conversation_id, memory.version)
            )
        )
        database.save_memory(conversation_id, memory, summary)
        return {
            **saved,
            "stored_path": None,
            "metadata": meta_parsed,
        }
    except KeyError as exc:
        raise http_not_found(exc) from exc
    except ValueError as exc:
        database.record_security_audit(
            "upload_rejected_by_security_gate",
            owner_id=owner.owner_id,
            conversation_id=conversation_id,
            metadata={"reason_code": str(exc)},
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch(
    "/conversations/{conversation_id}/attachments/{attachment_id}",
    dependencies=[Depends(csrf_guard)],
)
def correct_attachment(
    conversation_id: str,
    attachment_id: str,
    body: AttachmentCorrection,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        db(request).update_attachment_text(
            owner.owner_id, conversation_id, attachment_id, body.extracted_text
        )
        memory, summary = db(request).load_memory(owner.owner_id, conversation_id)
        for evidence in memory.evidence:
            if evidence.get("document_id") == attachment_id:
                evidence["extraction_status"] = "user_corrected"
                evidence["correction_source"] = {
                    "source_type": "document",
                    "source_id": attachment_id,
                    "span": "user-corrected extracted text",
                }
                memory.version += 1
                break
        memory.stale_draft_ids = list(
            dict.fromkeys(
                memory.stale_draft_ids
                + db(request).mark_drafts_stale(conversation_id, memory.version)
            )
        )
        db(request).save_memory(conversation_id, memory, summary)
        return {"updated": True}
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post("/conversations/{conversation_id}/drafts", dependencies=[Depends(csrf_guard)])
def create_draft(
    conversation_id: str,
    body: DraftBody,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        memory, _ = db(request).load_memory(owner.owner_id, conversation_id)
        return db(request).create_draft(
            owner.owner_id, conversation_id, body.title, body.content, memory.version
        )
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.patch(
    "/conversations/{conversation_id}/drafts/{draft_id}", dependencies=[Depends(csrf_guard)]
)
def update_draft(
    conversation_id: str,
    draft_id: str,
    body: DraftBody,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    try:
        memory, _ = db(request).load_memory(owner.owner_id, conversation_id)
        return db(request).update_draft(
            owner.owner_id,
            conversation_id,
            draft_id,
            body.content,
            memory.version,
            body.expected_version,
        )
    except MemoryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except KeyError as exc:
        raise http_not_found(exc) from exc


@router.post("/audio/transcribe", dependencies=[Depends(csrf_guard)])
async def transcribe(
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
    file: UploadFile = File(...),
):
    del owner
    cfg = live_settings(request)
    if not cfg.ai_configured:
        raise HTTPException(
            status_code=503, detail="OpenAI configuration required for transcription"
        )
    data = await file.read(25 * 1024 * 1024 + 1)
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio exceeds 25 MB")
    try:
        client = OpenAI(
            api_key=cfg.effective_openai_key, timeout=cfg.model_timeout_seconds, max_retries=2
        )
        result = await asyncio.to_thread(
            client.audio.transcriptions.create,
            model=cfg.openai_transcription_model,
            file=(
                Path(file.filename or "recording.webm").name,
                data,
                file.content_type or "audio/webm",
            ),
            prompt="Indian legal question or dispute. Preserve names, dates, rupee amounts, negation, Hindi-English code-switching and uncertainty.",
        )
        return {
            "transcript": result.text,
            "editable": True,
            "model": cfg.openai_transcription_model,
        }
    except Exception:
        raise HTTPException(
            status_code=502, detail="Transcription failed; the audio was not added to the case"
        ) from None


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/speech",
    dependencies=[Depends(csrf_guard)],
)
async def speech(
    conversation_id: str,
    message_id: str,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    cfg = live_settings(request)
    if not cfg.ai_configured:
        raise HTTPException(status_code=503, detail="OpenAI configuration required for speech")
    try:
        message = db(request).get_message(owner.owner_id, conversation_id, message_id)
    except KeyError as exc:
        raise http_not_found(exc) from exc
    if (
        message["role"] != "assistant"
        or message["status"] != "complete"
        or not (
            message["metadata"].get("verification", {}).get("passed")
            or message["metadata"].get("verification", {}).get("publication_safe")
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Speech is available only for completed verified assistant answers",
        )
    short = message["content"][:1800]
    target = cfg.export_path / f"speech-{message_id}.wav"
    try:
        chunks: list[bytes] = []
        async with asyncio.timeout(cfg.model_timeout_seconds):
            async with AsyncOpenAI(api_key=cfg.effective_openai_key) as client:
                async with client.realtime.connect(
                    model=cfg.openai_tts_model, max_retries=2
                ) as connection:
                    await connection.response.create(
                        response={
                            "conversation": "none",
                            "output_modalities": ["audio"],
                            "audio": {
                                "output": {
                                    "format": {"type": "audio/pcm", "rate": 24000},
                                    "voice": "marin",
                                }
                            },
                            "input": [
                                {
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "input_text",
                                            "text": (
                                                "Read the following verified answer clearly and calmly. "
                                                "Do not add, remove, or reinterpret content:\n"
                                                + short
                                            ),
                                        }
                                    ],
                                }
                            ],
                        }
                    )
                    async for event in connection:
                        if event.type == "response.output_audio.delta":
                            chunks.append(base64.b64decode(event.delta))
                        if event.type == "response.done":
                            break
        if not chunks:
            raise RuntimeError("No audio returned")
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"".join(chunks))
    except Exception:
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=502, detail="Speech generation failed; use the text answer instead"
        ) from None
    return FileResponse(
        target,
        media_type="audio/wav",
        filename="nyay-saathi-ai-summary.wav",
        headers={"X-AI-Generated-Voice": "true", "Cache-Control": "no-store"},
    )


@router.get("/conversations/{conversation_id}/export/{format}")
def export_case(
    conversation_id: str,
    format: str,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    if format not in {"json", "docx", "pdf"}:
        raise HTTPException(status_code=404, detail="Unsupported export format")
    try:
        database = db(request)
        conv = database.get_conversation(owner.owner_id, conversation_id)
        memory, summary = database.load_memory(owner.owner_id, conversation_id)
        payload = export_payload(
            conv,
            memory,
            summary,
            database.messages(owner.owner_id, conversation_id),
            database.attachments(owner.owner_id, conversation_id),
            database.drafts(owner.owner_id, conversation_id),
        )
    except KeyError as exc:
        raise http_not_found(exc) from exc
    target = live_settings(request).export_path / f"{conversation_id}-case-pack.{format}"
    {"json": write_json, "docx": write_docx, "pdf": write_pdf}[format](target, payload)
    media = {
        "json": "application/json",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }[format]
    return FileResponse(
        target,
        media_type=media,
        filename=f"nyay-saathi-case-pack.{format}",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/conversations/{conversation_id}/drafts/{draft_id}/export/{format}")
def export_correspondence(
    conversation_id: str,
    draft_id: str,
    format: str,
    request: Request,
    owner: Annotated[OwnerContext, Depends(owner_context)],
):
    if format not in {"docx", "pdf"}:
        raise HTTPException(status_code=404, detail="Unsupported format")
    try:
        draft = next(
            (d for d in db(request).drafts(owner.owner_id, conversation_id) if d["id"] == draft_id),
            None,
        )
        if draft is None:
            raise KeyError("draft_not_found")
    except KeyError as exc:
        raise http_not_found(exc) from exc
    target = (
        live_settings(request).export_path
        / f"{conversation_id}-{draft_id}-v{draft['version']}.{format}"
    )
    getattr(CorrespondenceExporter(), format)(target, draft["title"], draft["content"])
    return FileResponse(
        target,
        filename=f"prepared-correspondence.{format}",
        media_type="application/pdf"
        if format == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Cache-Control": "no-store", "X-Draft-Status": draft["status"]},
    )
