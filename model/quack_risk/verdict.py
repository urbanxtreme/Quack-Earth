"""Offline verdict from the grid, with an optional SpaceXAI rephrase."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from quack_risk.guidance import bright_radius_km

# Docs: https://docs.x.ai — model id checked against the models page.
VERDICT_MODEL = "grok-4.7"
XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
_FACT = re.compile(r"\d+(?:\.\d+)?%|\d+(?:\.\d+)? km")
_CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")
_SYSTEM = (
    "Rephrase the civil-protection note in plain sentences. "
    "Keep every number, percentage, and distance exactly as written. "
    "Do not add a clock time, a new magnitude, a new place, or an evacuation order. "
    "Return only the rephrased note."
)


def render_verdict(grid: pd.DataFrame) -> str:
    """Fill the fixed note from the peak cell. No extra facts."""
    required = ("probability_24h", "probability_m5_24h", "probability_m6_24h", "public_zone", "total_rate")
    missing = [name for name in required if name not in grid.columns]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Verdict grid is missing columns: {joined}.")

    peak = grid.loc[grid["probability_24h"].idxmax()]
    chance_m4 = float(peak["probability_24h"])
    chance_m5 = float(peak["probability_m5_24h"])
    chance_m6 = float(peak["probability_m6_24h"])
    zone = str(peak["public_zone"])
    larger = (
        f"about a {_percent(chance_m6)} chance of magnitude 6 or larger"
        if chance_m6 >= 0.01
        else "a much smaller chance of magnitude 6 or larger"
    )
    if zone == "usual":
        return (
            f"In the next 24 hours the highest cell on this map has about a {_percent(chance_m4)} chance "
            "of a magnitude 4 or larger earthquake. That stays under the 1% line for extra short-term action. "
            f"The chance of magnitude 5 or larger is about {_percent(chance_m5)}, with {larger}. "
            "No extra short-term action follows from this chance alone. "
            "A field commander decides any evacuation."
        )

    radius = bright_radius_km(grid)
    if zone in {"limit work", "priority"}:
        action = "Damaged buildings and excavation in this sector should wait. Move people out of cracked structures first."
    else:
        action = "Stay aware. Open-area checks can continue."
    return (
        f"In the next 24 hours the area within about {radius:.0f} km of the peak has about a {_percent(chance_m4)} "
        f"chance of a magnitude 4 or larger aftershock, about a {_percent(chance_m5)} chance of magnitude 5 or larger, "
        f"and {larger}. {action} "
        "This is a chance for the next 24 hours, not a clock time and not a single predicted magnitude. "
        "A field commander decides evacuation."
    )


def compose_verdict(
    grid: pd.DataFrame,
    *,
    allow_network: bool = False,
    rewriter=None,
) -> tuple[str, str]:
    """Return ``(text, source)``.

    ``source`` is ``template`` unless a rewrite is allowed, ``XAI_API_KEY`` is
    set, and the reply keeps the template's numbers. Any failure keeps the template.
    """
    template = render_verdict(grid)
    if not allow_network or not os.environ.get("XAI_API_KEY", "").strip():
        return template, "template"
    try:
        rewritten = (rewriter or rewrite_with_spacexai)(template)
    except Exception:
        return template, "template"
    if not rewritten or not _keeps_facts(template, rewritten):
        return template, "template"
    return rewritten.strip(), "spacexai"


def write_verdict(text: str, path: str | Path) -> Path:
    """Write the verdict note."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text.strip() + "\n", encoding="utf-8")
    return destination


def rewrite_with_spacexai(template: str) -> str:
    """Ask SpaceXAI to rephrase the template. Raises if the call does not return text."""
    api_key = os.environ.get("XAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set.")
    body = {
        "model": VERDICT_MODEL,
        "store": False,
        "input": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": template},
        ],
    }
    request = urllib.request.Request(
        XAI_RESPONSES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError("SpaceXAI verdict rewrite failed.") from exc
    return _output_text(payload)


def _output_text(payload: dict) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") not in {None, "message"}:
            continue
        content = item.get("content")
        if isinstance(content, str):
            parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("text") and block.get("type") in {None, "output_text"}:
                parts.append(str(block["text"]))
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("SpaceXAI response had no output text.")
    return text


def _keeps_facts(template: str, rewritten: str) -> bool:
    if _CLOCK.search(rewritten) and not _CLOCK.search(template):
        return False
    facts = _FACT.findall(template)
    return bool(facts) and all(fact in rewritten for fact in facts)


def _percent(probability: float) -> str:
    percent = 100.0 * float(probability)
    if percent >= 10.0:
        return f"{percent:.0f}%"
    if percent >= 1.0:
        return f"{percent:.1f}%"
    return f"{percent:.2f}%"
