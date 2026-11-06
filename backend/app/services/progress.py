"""Request-local progress; callbacks never contain prompts or document contents."""

from collections.abc import Callable
from contextvars import ContextVar
from time import perf_counter

ProgressCallback = Callable[[dict], None]
publisher: ContextVar[ProgressCallback | None] = ContextVar("progress_publisher", default=None)


def observed(stage, operation):
    def run(state):
        callback = publisher.get()
        started = perf_counter()
        if callback:
            callback({"stage": stage, "status": "running"})
        result = operation(state)
        event = {
            "stage": stage,
            "status": "complete",
            "duration_ms": round((perf_counter() - started) * 1000),
        }
        if callback:
            callback(event)
        result["events"] = result.get("events", []) + [event]
        return result

    return run
