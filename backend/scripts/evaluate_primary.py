"""Run deterministic integration fixtures or explicitly budgeted live A-H evaluations.

Offline mode tests protocol, isolation, safety and fallback, not LLM or legal quality.
Live mode spends at most the configured case/request/projected-USD allowances.
"""

import argparse
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from app.agent.contracts import AgentAnswer, AgentTask, AnswerClaim, ResearchRequest
from app.agent.runner import PrimaryAgent
from app.config import Settings
from app.db import Database
from app.rag.retrieval import HybridRetriever
from app.routing.segments import segment_message
from app.schemas.models import CaseMemory
from app.services.context_builder import ContextBuilder
from app.services.model_calls import model_calls

ROOT = Path(__file__).resolve().parents[2]


class FixtureProvider:
    def __init__(self, case):
        self.case, self.round = case, 0

    def complete(self, items, instructions, budget, **kwargs):
        budget.reserve("offline-fixture")
        self.round += 1
        with model_calls.operation("fixture_primary", "offline-fixture") as event:
            event["usage_reported"] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            if self.round == 1:
                request = ResearchRequest(
                    questions=[
                        {
                            "query": self.case["research_query"],
                            "material_gap": "Fixture verifies read-only research protocol",
                        }
                    ]
                )
                call = {
                    "type": "function_call",
                    "call_id": "fixture-call",
                    "name": "research_legal_issue",
                    "arguments": request.model_dump_json(),
                }
                return [call], [call], None
            answer = AgentAnswer(
                central_question=self.case["message"],
                tasks=[
                    AgentTask(
                        task_id="task-1",
                        title="Evidence to prepare",
                        intent=self.case["intent"],
                        domain=self.case["domain"],
                        case_link="unrelated" if self.case["educational"] else "new",
                        source_segment_ids=[s["id"] for s in segment_message(self.case["message"])],
                    )
                ],
                claims=[
                    AnswerClaim(
                        claim_id="prepare",
                        task_id="task-1",
                        kind="template",
                        text="",
                        template_id="preserve_records",
                    ),
                    AnswerClaim(
                        claim_id="limited",
                        task_id="task-1",
                        kind="template",
                        text="",
                        template_id="limited_research",
                    ),
                ],
                risk="urgent" if self.case["urgent"] else "ordinary",
                unresolved=["Offline fixture deliberately contains no legal conclusion."],
            )
            return [], [], answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case", help="Optional exact scenario ID")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "evals/reports/primary-v2-offline.json"
    )
    args = parser.parse_args()
    cases = json.loads((ROOT / "evals/cases/primary_agent_v2.json").read_text())
    cases = [c for c in cases if not args.case or c["id"] == args.case]
    if not cases:
        raise SystemExit("Unknown case")
    configured = Settings()
    if args.live:
        from scripts.live_guard import require_live_budget

        require_live_budget(configured, minimum_requests=len(cases), cases=len(cases))
        if not configured.agent_pricing_date or not configured.agent_pricing:
            raise SystemExit(
                "Not run: dated provider pricing is required to enforce projected evaluation spending."
            )
    records, requests_left, dollars_left = (
        [],
        configured.live_eval_max_model_calls,
        configured.live_eval_max_cost_usd,
    )
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="nyay-v2-eval-") as folder:
            directory = Path(folder)
            config = configured.model_copy(
                update={
                    "database_path": directory / "app.sqlite3",
                    "checkpoint_path": directory / "cp.sqlite3",
                    "upload_path": directory / "uploads",
                    "export_path": directory / "exports",
                    "openai_api_key": configured.openai_api_key if args.live else "offline-fixture",
                    "vector_index_enabled": False,
                }
            )
            if args.live:
                if requests_left < 1 or dollars_left <= 0:
                    break
                config.agent_max_requests = min(config.agent_max_requests, requests_left)
                config.agent_max_cost_usd = dollars_left
            config.ensure_dirs()
            database = Database(config.database_path)
            owner = database.create_owner("synthetic-evaluation")
            cid = database.create_conversation(owner, "en")["id"]
            memory = CaseMemory()
            state = {
                "owner_id": owner,
                "conversation_id": cid,
                "request_id": "evaluation",
                "message_id": "evaluation-message",
                "current_message": case["message"],
                "memory": memory.model_dump(mode="json"),
                "summary": "",
                "language": "en",
                "context": ContextBuilder().build(
                    current_message=case["message"], memory=memory, summary="", recent_messages=[]
                ),
            }
            research = (
                None
                if args.live
                else SimpleNamespace(
                    run=lambda *a: {
                        "status": "unavailable",
                        "evidence": [],
                        "limitations": ["Deliberate offline fixture search outage"],
                    }
                )
            )
            runner = PrimaryAgent(
                config,
                HybridRetriever(config),
                provider=None if args.live else FixtureProvider(case),
                research=research,
            )
            started = time.perf_counter()
            result = runner.invoke(state, f"{owner}:{cid}")
            requests_left -= result["metrics"]["provider_requests_reserved"] if args.live else 0
            dollars_left -= (result["metrics"].get("projected_cost_usd") or 0) if args.live else 0
            checks = {
                "case_unchanged_without_authorized_patch": result["memory"] == state["memory"]
                if not args.live
                else None,
                "has_approved_safety": bool(result["safety_messages"]) if case["urgent"] else None,
                "bounded_requests": result["metrics"]["provider_requests_reserved"]
                <= config.agent_max_requests,
                "no_invented_citations_on_empty_evidence": "[Source:" not in result["response"]
                if not result["passages"]
                else None,
            }
            records.append(
                {
                    "id": case["id"],
                    "mode": "live" if args.live else "offline_protocol_fixture",
                    "checks": checks,
                    "observed_wall_seconds": round(time.perf_counter() - started, 4),
                    "metrics": result["metrics"],
                    "answer": result["response"],
                    "expected_for_human_review": case["expected"],
                    "legal_accuracy_assessed": False,
                    "real_model_called": args.live
                    and any(r.get("attempts_observed", 0) for r in result["call_telemetry"]),
                    "publication_status": result["publication_status"],
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "engine": "primary-agent-v2.0",
                "records": records,
                "caution": "Offline timings and fixture outputs do not predict live latency, legal accuracy or model reasoning quality.",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(
        f"Wrote {len(records)} {'live' if args.live else 'offline protocol'} evaluations to {args.output}"
    )
    return 0 if all(v is not False for r in records for v in r["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
