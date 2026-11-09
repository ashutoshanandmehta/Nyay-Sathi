"""Thin, injectable Responses adapter using the installed SDK and existing telemetry."""

import json

from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema

from app.agent.contracts import ActionPlan, AgentAnswer, AgentReview, RepairPatch, ResearchRequest
from app.services.model_calls import model_calls, normalize_usage


def research_tool():
    return {
        "type": "function",
        "name": "research_legal_issue",
        "description": "Research focused Indian legal questions. Return fetched supporting passages, not snippets. Use only sanitized public legal questions; no personal data.",
        "strict": True,
        "parameters": to_strict_json_schema(ResearchRequest),
    }


def safety_tool():
    return {
        "type": "function",
        "name": "emit_safety",
        "description": (
            "Immediately display approved protective guidance tailored to the exact urgent risk mechanism "
            "(physical_safety for violence/detention/coercion, financial_cyber_fraud for active bank/UPI/wallet scams, "
            "domestic_violence, self_harm, or medical_emergency) before doing legal research."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "physical_safety",
                        "financial_cyber_fraud",
                        "domestic_violence",
                        "self_harm",
                        "medical_emergency",
                    ],
                    "description": "Exact urgent risk category matching the user's situation.",
                }
            },
            "required": ["category"],
            "additionalProperties": False,
        },
    }


class ResponsesProvider:
    def __init__(self, settings, factory=OpenAI):
        self.settings, self.factory = settings, factory

    def complete_plan(self, items, instructions, budget):
        """Optional lightweight pre-turn ActionPlan call for separate_planner ablation mode."""
        model = self.settings.openai_planner_model or self.settings.openai_review_model
        schema_json = to_strict_json_schema(ActionPlan)
        size = (
            len(json.dumps(items, ensure_ascii=False).encode())
            + len(instructions.encode())
            + len(json.dumps(schema_json).encode())
        )
        reservation = budget.reserve(model, size)
        settings = self.settings.model_copy(
            update={
                "model_timeout_seconds": max(
                    0.1, min(self.settings.model_timeout_seconds, budget.remaining_time())
                )
            }
        )
        kwargs = {
            "model": model,
            "input": items,
            "instructions": instructions,
            "store": False,
            "max_output_tokens": min(1800, settings.agent_max_output_tokens),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": ActionPlan.__name__,
                    "strict": True,
                    "schema": schema_json,
                }
            },
        }
        try:
            with model_calls.sdk(settings, "plan", model, factory=self.factory) as client:
                response = client.responses.create(**kwargs)
            data = response.model_dump(mode="json", by_alias=True)
            budget.report(
                normalize_usage(data.get("usage")), model=model, reservation=reservation
            )
            if data.get("status") != "completed":
                raise ValueError("Planner returned incomplete output")
            output = data.get("output", [])
            content = "".join(
                c.get("text", "")
                for item in output
                if item.get("type") == "message"
                for c in item.get("content", [])
                if c.get("type") == "output_text"
            )
            return ActionPlan.model_validate_json(content)
        except Exception:
            budget.unknown_cost = True
            raise

    def complete(
        self,
        items,
        instructions,
        budget,
        *,
        review=False,
        allow_tools=True,
        stage="primary",
        schema=None,
        prompt_cache_key=None,
        conversation_id=None,
    ):
        if schema is None:
            schema = RepairPatch if stage == "repair" else (AgentReview if review else AgentAnswer)
        model = self.settings.openai_review_model if review else self.settings.openai_chat_model
        schema_json = to_strict_json_schema(schema)
        size = (
            len(json.dumps(items, ensure_ascii=False).encode())
            + len(instructions.encode())
            + len(json.dumps(schema_json).encode())
            + (
                len(json.dumps([research_tool(), safety_tool()]).encode())
                if allow_tools and not review
                else 0
            )
        )
        reservation = budget.reserve(model, size)
        min_timeout = 20.0 if review else 0.1
        settings = self.settings.model_copy(
            update={
                "model_timeout_seconds": min(
                    self.settings.model_timeout_seconds,
                    max(min_timeout, budget.remaining_time()),
                )
            }
        )
        kwargs = {
            "model": model,
            "input": items,
            "instructions": instructions,
            "store": False,
            "max_output_tokens": settings.agent_max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema_json,
                }
            },
            "include": ["reasoning.encrypted_content"],
        }
        stage_family = "review" if review else "primary"
        if not prompt_cache_key and conversation_id:
            prompt_cache_key = f"nyay:{stage_family}:{conversation_id}"
        if prompt_cache_key:
            kwargs["prompt_cache_key"] = prompt_cache_key
        if allow_tools and not review:
            kwargs.update(tools=[research_tool(), safety_tool()], parallel_tool_calls=False)
        if settings.agent_reasoning_effort:
            kwargs["reasoning"] = {"effort": settings.agent_reasoning_effort}
        try:
            with model_calls.sdk(settings, stage, model, factory=self.factory) as client:
                response = client.responses.create(**kwargs)
            # The SDK exposes reserved API names such as ``async`` as Python-safe
            # attributes (``async_``). Stateless continuation replays these items
            # to the API, so serialize with wire aliases rather than attribute names.
            data = response.model_dump(mode="json", by_alias=True, exclude_none=True)
            budget.report(
                normalize_usage(data.get("usage")), model=model, reservation=reservation
            )
            if data.get("status") != "completed":
                raise ValueError("Provider returned incomplete output")
            output = [
                {k: v for k, v in item.items() if k != "parsed_arguments"}
                if isinstance(item, dict)
                else item
                for item in data.get("output", [])
            ]
            if any(c.get("type") == "refusal" for item in output for c in item.get("content", [])):
                raise ValueError("Provider refused the request")
            calls = [item for item in output if item.get("type") == "function_call"]
            if calls:
                if review or not allow_tools or len(calls) != 1:
                    raise ValueError("Unexpected tool calls")
                return output, calls, None
            content = "".join(
                c.get("text", "")
                for item in output
                if item.get("type") == "message"
                for c in item.get("content", [])
                if c.get("type") == "output_text"
            )
            return output, [], schema.model_validate_json(content)
        except Exception:
            budget.unknown_cost = True
            raise
