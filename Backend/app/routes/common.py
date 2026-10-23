from datetime import datetime, timezone
from typing import Any


def error(
    first: str,
    second: Any = 400,
    status: int = 400,
    code: str | None = None,
) -> tuple[dict[str, Any], int]:
    if isinstance(second, str):
        error_code = first
        error_message = second
        final_status = status if isinstance(status, int) else 400
    else:
        error_message = first
        final_status = second if isinstance(second, int) else 400
        error_code = code

    data: dict[str, Any] = {
        "error": error_message,
        "message": error_message,
    }
    if error_code:
        data["code"] = error_code
    return data, final_status



def parse_iso(value: str, field: str = "time") -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (AttributeError, ValueError):
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp")
