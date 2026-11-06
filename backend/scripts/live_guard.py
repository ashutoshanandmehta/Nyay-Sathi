"""Paid historical runners are opt-in and disabled under V2's default development budget."""


def require_live_budget(settings, minimum_requests=1, cases=1):
    if (
        not settings.ai_configured
        or settings.live_eval_max_cases < cases
        or settings.live_eval_max_model_calls < minimum_requests
        or settings.live_eval_max_cost_usd <= 0
    ):
        raise SystemExit(
            "Not run: configure an explicit live case, request and USD allowance first. Use scripts.evaluate_primary for the V2 budget-enforced runner."
        )
