"""One atomic allowance across concurrent tools, model continuations and verification."""

import threading
import time

from app.services.model_calls import BudgetExhausted


class TurnBudget:
    def __init__(self, settings, clock=time.monotonic):
        self.settings, self.clock = settings, clock
        self.started = clock()
        self.deadline = self.started + settings.agent_deadline_seconds
        self.lock = threading.Lock()
        self.requests = self.tokens = self.queries = self.documents = self.batches = 0
        self.projected_cost = 0.0
        self.projected_tokens = 0
        self.reported_cost = 0.0
        self.cost_records = []
        self.unknown_cost = False
        self.query_hashes = set()

    def remaining_time(self):
        return max(0.0, self.deadline - self.clock())

    def available(self, count=1, reserve=0):
        with self.lock:
            return (
                self.remaining_time() > 0
                and self.tokens < self.settings.agent_max_tokens
                and self.requests + count + reserve <= self.settings.agent_max_requests
            )

    def reserve(self, model, input_chars=0, reserve=0, search=False):
        with self.lock:
            # Search injects provider-managed context; reserve a conservative
            # additional allowance instead of treating discovery as a tiny prompt.
            input_chars += 32000 if search else 0
            projected_tokens = input_chars + self.settings.agent_max_output_tokens
            if (
                self.remaining_time() <= 0
                or self.projected_tokens + projected_tokens > self.settings.agent_max_tokens
                or self.requests + 1 + reserve > self.settings.agent_max_requests
            ):
                raise BudgetExhausted("Turn request/time/token allowance exhausted")
            prices = self.settings.agent_pricing.get(model)
            if self.settings.agent_max_cost_usd is not None:
                if not prices or not self.settings.agent_pricing_date:
                    raise BudgetExhausted(
                        "A spend cap requires dated pricing for every provider model"
                    )
                # UTF-8 bytes are a conservative input-token estimate for text.
                estimate = (
                    input_chars * prices.get("input_per_million", 0)
                    + self.settings.agent_max_output_tokens * prices.get("output_per_million", 0)
                ) / 1_000_000
                if search:
                    estimate += prices.get("search_per_call", 0)
                if not all(k in prices for k in ("input_per_million", "output_per_million")) or (
                    search and "search_per_call" not in prices
                ):
                    raise BudgetExhausted("Incomplete pricing cannot enforce a spend cap")
                if self.projected_cost + estimate > self.settings.agent_max_cost_usd:
                    raise BudgetExhausted("Projected spend would exceed the turn allowance")
                self.projected_cost += estimate
            self.requests += 1
            self.projected_tokens += projected_tokens

    def report(self, usage, model=None, search=False):
        with self.lock:
            if usage:
                self.tokens += usage.get("total_tokens", 0)
            else:
                self.unknown_cost = True
            prices = self.settings.agent_pricing.get(model, {})
            if (
                usage
                and self.settings.agent_pricing_date
                and all(k in prices for k in ("input_per_million", "output_per_million"))
                and (not search or "search_per_call" in prices)
            ):
                cached = usage.get("input_details", {}).get("cached_tokens", 0)
                value = (
                    max(0, usage.get("input_tokens", 0) - cached) * prices["input_per_million"]
                    + cached * prices.get("cached_input_per_million", prices["input_per_million"])
                    + usage.get("output_tokens", 0) * prices["output_per_million"]
                ) / 1_000_000
                value += prices.get("search_per_call", 0) if search else 0
                self.reported_cost += value
                self.cost_records.append(value)
            else:
                self.unknown_cost = True

    def snapshot(self):
        with self.lock:
            return {
                "provider_requests_reserved": self.requests,
                "reported_tokens": self.tokens,
                "conservative_tokens_reserved": self.projected_tokens,
                "queries": self.queries,
                "documents_attempted": self.documents,
                "research_batches": self.batches,
                "remaining_seconds": round(self.remaining_time(), 3),
                "projected_cost_usd": self.projected_cost
                if self.settings.agent_max_cost_usd
                else None,
                "cost_status": "unknown"
                if self.unknown_cost or not self.settings.agent_pricing_date
                else "estimated",
                "estimated_cost_usd": self.reported_cost
                if self.cost_records and not self.unknown_cost
                else None,
                "known_estimated_cost_usd": self.reported_cost if self.cost_records else None,
                "actual_billed_cost_usd": None,
                "pricing_date": self.settings.agent_pricing_date,
            }
