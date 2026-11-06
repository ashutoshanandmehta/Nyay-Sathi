"""Request-scoped accounting and managed SDK clients; never logs request bodies."""

import json
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from openai import DefaultHttpx2Client, OpenAI


def normalize_usage(usage):
    if not usage:
        return None
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    return {
        "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens", 0)),
        "output_tokens": usage.get("output_tokens", usage.get("completion_tokens", 0)),
        "total_tokens": usage.get("total_tokens", 0),
        "input_details": usage.get(
            "input_tokens_details",
            usage.get("prompt_tokens_details", usage.get("input_token_details", {})),
        ),
        "output_details": usage.get(
            "output_tokens_details",
            usage.get("completion_tokens_details", usage.get("output_token_details", {})),
        ),
    }


@dataclass
class CallScope:
    limit: int
    embedding_limit: int = 1
    records: list = field(default_factory=list)
    sink: object = None
    lock: object = field(default_factory=threading.Lock)

    def totals(self):
        return {
            key: sum((r.get("usage_reported") or {}).get(key, 0) for r in self.records)
            for key in ("input_tokens", "output_tokens", "total_tokens")
        }


active_scope = ContextVar("model_call_scope", default=None)


class BudgetExhausted(RuntimeError):
    pass


class ModelCalls:
    @contextmanager
    def validation(self, stage):
        scope = active_scope.get()
        event = (
            next((r for r in reversed(scope.records) if r["stage"] == stage), None)
            if scope
            else None
        )
        try:
            yield
            if event is not None:
                event["validation_status"] = "valid"
        except Exception as exc:
            if event is not None:
                event.update(validation_status="failed", validation_error_type=type(exc).__name__)
            raise
        finally:
            if event is not None and scope.sink:
                scope.sink(event)

    @contextmanager
    def scope(self, limit, sink=None):
        scope = CallScope(limit=limit, sink=sink)
        token = active_scope.set(scope)
        try:
            yield scope
        finally:
            active_scope.reset(token)

    @contextmanager
    def operation(self, stage, model, category="generation", settings=None):
        scope = active_scope.get()
        event = {
            "call_id": str(uuid.uuid4()),
            "stage": stage,
            "category": category,
            "model": model,
            "settings": settings or {},
            "attempts_observed": 0,
            "attempts_confirmed": 0,
            "usage_reported": None,
            "usage_completeness": "unknown",
            "status": "started",
            "first_token_ms": None,
            "first_token_reason": "non_streaming",
            "provider_queue_ms": None,
            "application_wait_ms": 0,
            "attempts": [],
        }
        if scope:
            with scope.lock:
                used = sum(
                    r["category"] == "embedding"
                    if category == "embedding"
                    else r["category"] != "embedding"
                    for r in scope.records
                )
                if used >= (scope.embedding_limit if category == "embedding" else scope.limit):
                    raise BudgetExhausted("Required model dependency exceeds the turn allowance")
                scope.records.append(event)

        def persist():
            if scope and scope.sink:
                scope.sink(event)

        started = time.perf_counter()
        persist()
        try:
            yield event
            event["status"] = "completed"
        except Exception as exc:
            event.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            event["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            known = [a for a in event["attempts"] if a.get("usage") is not None]
            if known:
                event["usage_reported"] = {
                    key: sum(a["usage"].get(key, 0) for a in known)
                    for key in ("input_tokens", "output_tokens", "total_tokens")
                }
                event["usage_reported"]["attempt_details"] = [a["usage"] for a in known]
            if event["usage_reported"] is not None:
                event["usage_completeness"] = (
                    "complete"
                    if event["attempts"] and len(known) == len(event["attempts"])
                    else "partial"
                )
            persist()

    @contextmanager
    def transport(self, event):
        def request_hook(request):
            event["attempts_observed"] += 1
            request.extensions["nyay_attempt"] = len(event["attempts"])
            event["attempts"].append({"status": "sent", "usage": None})

        def response_hook(response):
            index = response.request.extensions.get("nyay_attempt")
            if index is None:
                return
            event["attempts_confirmed"] += 1
            attempt = event["attempts"][index]
            attempt.update(
                status="response",
                http_status=response.status_code,
                provider_request_id=response.headers.get("x-request-id"),
            )
            # Structured calls are non-streaming. Reading here preserves usage
            # even if schema parsing subsequently fails in LangChain/the SDK.
            try:
                body = json.loads(response.read())
                attempt["usage"] = normalize_usage(body.get("usage"))
                if response.status_code >= 400 and isinstance(body.get("error"), dict):
                    error = body["error"]
                    attempt["provider_error"] = {
                        key: error.get(key)
                        for key in ("type", "code", "param")
                        if error.get(key) is not None
                    }
                    # Provider messages describe the rejected field and are useful for
                    # diagnostics. Keep them bounded; request and response bodies are
                    # deliberately never persisted.
                    if error.get("message"):
                        attempt["provider_error"]["message"] = str(error["message"])[:500]
            except (ValueError, UnicodeError):
                pass

        with DefaultHttpx2Client(
            event_hooks={"request": [request_hook], "response": [response_hook]}
        ) as client:
            yield client

    def structured(self, factory, schema, messages, settings, stage, review=False):
        model = settings.openai_review_model if review else settings.openai_chat_model
        with self.operation(
            stage, model, settings={"timeout": settings.model_timeout_seconds, "max_retries": 0}
        ) as event:
            with self.transport(event) as client:
                result = (
                    factory(
                        model=model,
                        api_key=settings.openai_api_key,
                        timeout=settings.model_timeout_seconds,
                        max_retries=0,
                        http_client=client,
                    )
                    .with_structured_output(schema, method="json_schema", include_raw=True)
                    .invoke(messages)
                )
                raw = result.get("raw")
                usage = getattr(raw, "usage_metadata", None)
                if usage and event["usage_reported"] is None:
                    event["usage_reported"] = normalize_usage(usage)
                return result

    @contextmanager
    def sdk(self, settings, stage, model, factory=OpenAI, category="generation"):
        with self.operation(
            stage, model, category, {"max_retries": 0, "timeout": settings.model_timeout_seconds}
        ) as event:
            with self.transport(event) as transport:
                with factory(
                    api_key=settings.openai_api_key,
                    timeout=settings.model_timeout_seconds,
                    max_retries=0,
                    http_client=transport,
                ) as client:
                    yield client


model_calls = ModelCalls()
