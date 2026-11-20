"""Reproduce the offline routing fixtures, recording actual orchestration outputs.
This does not contact OpenAI and does not evaluate the model's routing judgment.
Run: PYTHONPATH=backend python scripts/evaluate_routing.py
"""

import json
import os
import sys
from pathlib import Path

os.environ["OPENAI_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tests.test_agent_routing import SCENARIOS, assessment, decision, request, setup
from app.agent.routing import prepare_route

results = []
for name, message, route in SCENARIOS:
    outputs = [decision(route, research=request() if route == "research" else None)]
    if route != "fast":
        outputs.append(assessment())
    agent, state, budget, emit, events, searches = setup(outputs, message)
    prepare_route(agent, state, budget, emit)
    expected_stages = (
        ["routing", "fast"] if route == "fast" else ["routing", "applicability"]
    )
    if route == "research":
        expected_stages.append("web_research")
    observed = list(dict.fromkeys(e["stage"] for e in events))
    passed = state["route"] == route and all(s in observed for s in expected_stages)
    results.append(
        {
            "scenario": name,
            "prompt": message,
            "expected_fixture_route": route,
            "actual_route": state["route"],
            "actual_stages": observed,
            "actual_route_history": state["route_history"],
            "actual_model_fixture_calls": budget.requests,
            "actual_research_fixture_batches": len(searches),
            "actual_guidance": state["route_guidance"],
            "actual_events": events,
            "passed": passed,
        }
    )
report = {
    "evidence_type": "offline orchestration fixtures, not live LLM evaluation",
    "paid_calls": 0,
    "cases": results,
}
path = Path(__file__).resolve().parents[1] / "docs/qa/routing-v2/scenarios.actual.json"
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(
    f"Recorded {len(results)} scenarios; {sum(r['passed'] for r in results)} passed. Live LLM judgment unverified."
)
if not all(r["passed"] for r in results):
    raise SystemExit(1)
