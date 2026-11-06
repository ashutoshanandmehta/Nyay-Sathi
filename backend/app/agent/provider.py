"""Thin, injectable Responses adapter using the installed SDK and existing telemetry."""

import json

from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema

from app.agent.contracts import AgentAnswer, AgentReview, ResearchRequest
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
        "description": "Immediately display approved protective guidance for an urgent situation before doing legal research.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    }


class ResponsesProvider:
    def __init__(self, settings, factory=OpenAI):
        self.settings, self.factory = settings, factory

    def complete(
        self, items, instructions, budget, *, review=False, allow_tools=True, stage="primary"
    ):
        schema = AgentReview if review else AgentAnswer
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
        budget.reserve(model, size)
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
        if allow_tools and not review:
            kwargs.update(tools=[research_tool(), safety_tool()], parallel_tool_calls=False)
        if settings.agent_reasoning_effort:
            kwargs["reasoning"] = {"effort": settings.agent_reasoning_effort}
        try:
            with model_calls.sdk(settings, stage, model, factory=self.factory) as client:
                response = client.responses.create(**kwargs)
            data = response.model_dump(mode="json")
            budget.report(normalize_usage(data.get("usage")), model=model)
            if data.get("status") != "completed":
                raise ValueError("Provider returned incomplete output")
            output = data.get("output", [])
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
