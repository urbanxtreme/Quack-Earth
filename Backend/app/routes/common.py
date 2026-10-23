from datetime import datetime, timezone
from typing import Any


def error(message: str, status: int = 400, code: str | None = None) -> tuple[dict[str, Any], int]:
    data: dict[str, Any] = {
        "error": message,
        "message": message,
    }
    if code:
        data["code"] = code
    return data, status


def parse_iso(value: str, field: str = "time") -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (AttributeError, ValueError):
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp")
