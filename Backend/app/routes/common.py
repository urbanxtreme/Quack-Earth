from datetime import datetime, timezone

from flask import request


def error(code, message, status=400):
    return {"error": {"code": code, "message": message, "request": request.get_json(silent=True) or request.args}}, status


def parse_iso(value, field):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (AttributeError, ValueError):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
