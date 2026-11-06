"""Faithful installed-SDK HTTP transport mocks; no paid requests or model evaluation."""

import json

import httpx2
import pytest

from app.agent.budget import TurnBudget
from app.agent.contracts import AgentAnswer
from app.agent.provider import ResponsesProvider
from app.config import Settings
from app.services.model_calls import model_calls


def test_installed_sdk_serialization_parsing_and_usage_hooks(monkeypatch):
    captured = []
    answer = {
        "central_question": "Respond to greeting",
        "tasks": [
            {
                "task_id": "task-1",
                "title": "Hello",
                "intent": "conversation",
                "domain": "general",
                "case_link": "unrelated",
            }
        ],
        "claims": [
            {
                "claim_id": "c1",
                "task_id": "task-1",
                "kind": "template",
                "text": "",
                "template_id": "greeting",
            }
        ],
    }

    def handle(request):
        captured.append(json.loads(request.content))
        assert str(request.url).endswith("/responses")
        return httpx2.Response(
            200,
            headers={"x-request-id": "fixture-request"},
            json={
                "id": "resp_fixture",
                "object": "response",
                "created_at": 1,
                "model": "fixture",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "msg_fixture",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": json.dumps(answer), "annotations": []}
                        ],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130},
            },
        )

    monkeypatch.setattr(
        "app.services.model_calls.DefaultHttpx2Client",
        lambda **kw: httpx2.Client(transport=httpx2.MockTransport(handle), **kw),
    )
    settings = Settings(openai_api_key="fixture-not-real")
    with model_calls.scope(2) as scope:
        _, calls, parsed = ResponsesProvider(settings).complete(
            [{"role": "user", "content": "hello"}], "instructions", TurnBudget(settings)
        )
    assert isinstance(parsed, AgentAnswer) and not calls
    assert captured[0]["store"] is False
    assert captured[0]["tools"][0]["parameters"]["additionalProperties"] is False
    assert scope.records[0]["attempts_observed"] == 1
    assert scope.records[0]["usage_completeness"] == "complete"
    assert scope.totals()["total_tokens"] == 130


@pytest.mark.parametrize(
    "response",
    [
        {"status": "incomplete", "output": []},
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "refusal", "refusal": "Fixture refusal"}],
                }
            ],
        },
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "not JSON"}],
                }
            ],
        },
    ],
)
def test_sdk_refusal_truncation_and_invalid_structured_output_are_not_published(
    monkeypatch, response
):
    monkeypatch.setattr(
        "app.services.model_calls.DefaultHttpx2Client",
        lambda **kw: httpx2.Client(
            transport=httpx2.MockTransport(
                lambda req: httpx2.Response(
                    200,
                    json={
                        "id": "resp_fixture",
                        "object": "response",
                        "model": "fixture",
                        "created_at": 1,
                        **response,
                    },
                )
            ),
            **kw,
        ),
    )
    settings = Settings(openai_api_key="fixture-not-real")
    with pytest.raises(ValueError):
        ResponsesProvider(settings).complete([], "instructions", TurnBudget(settings))
