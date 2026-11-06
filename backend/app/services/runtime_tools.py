"""Small deterministic capabilities available to graph nodes, never directly to the model."""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def current_ist_datetime() -> dict[str, str]:
    now = datetime.now(IST)
    return {
        "datetime": now.isoformat(),
        "date": now.date().isoformat(),
        "timezone": "Asia/Kolkata",
    }


def calculate_days_between(start_iso: str, end_iso: str) -> int:
    """Calendar arithmetic only; this does not decide any legal deadline."""
    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    return (end - start).days


def add_calendar_days(start_iso: str, days: int) -> str:
    """Calendar arithmetic only; callers must not label the result a legal deadline."""
    return (date.fromisoformat(start_iso) + timedelta(days=days)).isoformat()


def decimal_calculation(left: str, operation: str, right: str) -> str:
    """Perform bounded decimal arithmetic without evaluating user-supplied code."""
    try:
        a, b = Decimal(left), Decimal(right)
    except InvalidOperation as exc:
        raise ValueError("Values must be decimal numbers") from exc
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            raise ValueError("Cannot divide by zero")
        result = a / b
    else:
        raise ValueError("Unsupported arithmetic operation")
    return format(result.normalize(), "f")
