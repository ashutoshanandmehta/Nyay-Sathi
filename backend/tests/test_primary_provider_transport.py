"""Faithful installed-SDK HTTP transport mocks; no paid requests or model evaluation."""

import json

import httpx2
import pytest
from pydantic import BaseModel

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


def test_sdk_tool_items_use_wire_aliases_for_stateless_replay(monkeypatch):
    def handle(_request):
        return httpx2.Response(
            200,
            json={
                "id": "resp_tool_fixture",
                "object": "response",
                "created_at": 1,
                "model": "fixture",
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "id": "fc_fixture",
                        "call_id": "call_fixture",
                        "name": "research_legal_issue",
                        "arguments": '{"questions":[],"fresh_required":false}',
                        "status": "completed",
                        "async": True,
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        )

    monkeypatch.setattr(
        "app.services.model_calls.DefaultHttpx2Client",
        lambda **kw: httpx2.Client(transport=httpx2.MockTransport(handle), **kw),
    )
    settings = Settings(openai_api_key="fixture-not-real")
    output, calls, answer = ResponsesProvider(settings).complete(
        [{"role": "user", "content": "research"}],
        "instructions",
        TurnBudget(settings),
    )
    assert answer is None and calls
    assert output[0]["async"] is True
    assert "async_" not in output[0]


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


def test_prompt_cache_key_is_sent_and_stable(monkeypatch):
    captured = []
    dummy_answer = {
        "central_question": "Respond to greeting",
        "tasks": [{"task_id": "task-1", "title": "Hello", "intent": "conversation", "domain": "general", "case_link": "unrelated"}],
        "claims": [{"claim_id": "c1", "task_id": "task-1", "kind": "template", "text": "", "template_id": "greeting"}],
    }

    class DummyReviewSchema(BaseModel):
        pass

    def handle(request):
        body = json.loads(request.content)
        captured.append(body)
        resp_text = json.dumps({}) if "review" in body.get("instructions", "") else json.dumps(dummy_answer)
        return httpx2.Response(
            200,
            json={
                "id": "resp_fixture",
                "object": "response",
                "created_at": 1,
                "model": "fixture",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": resp_text, "annotations": []}
                        ],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        )

    monkeypatch.setattr(
        "app.services.model_calls.DefaultHttpx2Client",
        lambda **kw: httpx2.Client(transport=httpx2.MockTransport(handle), **kw),
    )
    settings = Settings(openai_api_key="fixture-not-real")
    provider = ResponsesProvider(settings)

    # Round 1: primary stage
    provider.complete(
        [{"role": "user", "content": "test 1"}],
        "system instructions",
        TurnBudget(settings),
        stage="primary",
        conversation_id="conv-abc",
        schema=AgentAnswer,
    )
    # Round 2: same conversation primary stage
    provider.complete(
        [{"role": "user", "content": "test 2"}],
        "system instructions",
        TurnBudget(settings),
        stage="primary",
        conversation_id="conv-abc",
        schema=AgentAnswer,
    )
    # Round 3: review stage
    provider.complete(
        [{"role": "user", "content": "review 1"}],
        "review instructions",
        TurnBudget(settings),
        stage="review",
        review=True,
        conversation_id="conv-abc",
        schema=DummyReviewSchema,
    )

    assert len(captured) == 3
    assert captured[0]["prompt_cache_key"] == "nyay:primary:conv-abc"
    assert captured[1]["prompt_cache_key"] == "nyay:primary:conv-abc"
    assert captured[2]["prompt_cache_key"] == "nyay:review:conv-abc"
    assert captured[0]["prompt_cache_key"] == captured[1]["prompt_cache_key"]


def test_static_context_and_evidence_byte_identical_between_rounds():
    from app.agent.runner import PrimaryAgent

    settings = Settings(openai_api_key="fixture-not-real")
    state = {
        "owner_id": "test-owner",
        "conversation_id": "conv-test",
        "request_id": "req-1",
        "message_id": "msg-1",
        "current_message": "My complaint details",
        "memory": {"version": 1, "domain": "consumer"},
        "summary": "User needs help",
        "language": "en",
        "passages": [
            {"passage_id": "b-pass", "text": "Second statute passage", "canonical_url": "https://gov.in/b"},
            {"passage_id": "a-pass", "text": "First statute passage", "canonical_url": "https://gov.in/a"},
        ],
        "context": {"recent_turns": []},
        "tool_records": [],
    }

    agent = PrimaryAgent(settings, None)
    ctx1 = agent._context(state)
    ctx2 = agent._context(state)

    # Evidence is sorted deterministically by passage_id
    assert [e["passage_id"] for e in ctx1["evidence"] if e.get("passage_id")] == ["a-pass", "b-pass"]

    # Byte-identical serialization
    str1 = json.dumps(ctx1, ensure_ascii=False)
    str2 = json.dumps(ctx2, ensure_ascii=False)
    assert str1 == str2

    # Instructions are also constant
    assert agent.prompt is not None and len(agent.prompt) > 0

