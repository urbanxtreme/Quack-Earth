"""Magnitude outlook, plain zones, the excavation card, and the offline verdict."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quack_risk.guidance import LIMIT_LINE, attach_public_zone, build_guidance, public_zones
from quack_risk.io import write_risk_grid
from quack_risk.outlook import attach_outlook, probability_at_least
from quack_risk.schema import GRID_COLUMNS, PUBLIC_COLUMNS
from quack_risk.verdict import _output_text, compose_verdict, render_verdict


def test_magnitude_outlook_follows_gutenberg_richter() -> None:
    rate = np.array([0.2, 0.01])
    magnitude_5 = probability_at_least(rate, 5.0)
    magnitude_6 = probability_at_least(rate, 6.0)
    assert np.allclose(magnitude_5, 1.0 - np.exp(-rate * 0.1))
    assert np.allclose(magnitude_6, 1.0 - np.exp(-rate * 0.01))
    assert np.all(magnitude_6 < magnitude_5)
    assert np.all(magnitude_5 < 1.0 - np.exp(-rate))


def test_public_zone_cutoffs() -> None:
    chance = np.array([0.0, 0.009, 0.01, 0.049, 0.05, 0.149, 0.15, 0.5])
    assert list(public_zones(chance)) == [
        "usual",
        "usual",
        "stay aware",
        "stay aware",
        "limit work",
        "limit work",
        "priority",
        "priority",
    ]


def _card_grid() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"lat": 37.20, "lon": 37.00, "total_rate": 0.20, "probability_24h": 0.20, "probability_m5_24h": 0.02, "probability_m6_24h": 0.002},
            {"lat": 37.25, "lon": 37.00, "total_rate": 0.16, "probability_24h": 0.16, "probability_m5_24h": 0.016, "probability_m6_24h": 0.0016},
            {"lat": 37.80, "lon": 37.00, "total_rate": 0.08, "probability_24h": 0.08, "probability_m5_24h": 0.008, "probability_m6_24h": 0.0008},
            {"lat": 37.20, "lon": 37.70, "total_rate": 0.02, "probability_24h": 0.02, "probability_m5_24h": 0.002, "probability_m6_24h": 0.0002},
            {"lat": 36.40, "lon": 36.40, "total_rate": 0.001, "probability_24h": 0.001, "probability_m5_24h": 0.0001, "probability_m6_24h": 0.00001},
        ]
    )


def test_excavation_pauses_for_limit_work_and_priority() -> None:
    card = build_guidance(attach_public_zone(_card_grid()), as_of="2024-01-15T03:35:00Z")
    by_zone = {sector["public_zone"]: sector for sector in card["sectors"]}
    assert card["limit"] == LIMIT_LINE
    assert "commander decides evacuation" in card["limit"]
    assert by_zone["priority"]["excavation"] == "pause"
    assert "Pause excavation" in by_zone["priority"]["action"]
    assert by_zone["priority"]["place"] == "at the peak"
    assert by_zone["limit work"]["excavation"] == "pause"
    assert "Pause excavation" in by_zone["limit work"]["action"]
    assert by_zone["limit work"]["direction"] == "north"
    assert by_zone["stay aware"]["excavation"] == "open-area checks"
    assert "Open-area checks can continue" in by_zone["stay aware"]["action"]
    assert all(sector["public_zone"] != "usual" for sector in card["sectors"])


def _verdict_grid() -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "lat": 37.00,
                "lon": 37.00,
                "total_rate": 0.20,
                "probability_24h": 0.174,
                "probability_m5_24h": 0.0185,
                "probability_m6_24h": 0.00186,
                "public_zone": "priority",
            },
            {
                "lat": 37.27,
                "lon": 37.00,
                "total_rate": 0.10,
                "probability_24h": 0.09,
                "probability_m5_24h": 0.009,
                "probability_m6_24h": 0.0009,
                "public_zone": "limit work",
            },
        ]
    )
    return frame


def test_verdict_template_states_the_chance_and_no_clock_time() -> None:
    text = render_verdict(_verdict_grid())
    assert "24 hours" in text
    assert "17%" in text
    assert "1.8%" in text
    assert "magnitude 6" in text
    assert "excavation" in text
    assert "commander decides evacuation" in text
    assert "03:" not in text


def test_missing_api_key_keeps_the_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    grid = _verdict_grid()

    def explode(_template: str) -> str:
        raise AssertionError("rewrite should not run without an API key")

    text, source = compose_verdict(grid, allow_network=True, rewriter=explode)
    assert source == "template"
    assert text == render_verdict(grid)


def test_rewrite_that_changes_the_facts_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    text, source = compose_verdict(
        _verdict_grid(),
        allow_network=True,
        rewriter=lambda _template: "Evacuate immediately at 03:15. The magnitude will be 7.",
    )
    assert source == "template"
    assert "03:15" not in text
    assert "17%" in text


def test_rewrite_that_keeps_the_facts_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    text, source = compose_verdict(
        _verdict_grid(),
        allow_network=True,
        rewriter=lambda template: "Field note. " + template,
    )
    assert source == "spacexai"
    assert text.startswith("Field note. ")
    assert "17%" in text


def test_output_text_reads_the_message_block() -> None:
    payload = {
        "output": [
            {"type": "reasoning", "content": []},
            {"type": "message", "content": [{"type": "output_text", "text": "Stay back."}]},
        ]
    }
    assert _output_text(payload) == "Stay back."


def test_written_grid_keeps_the_original_columns_first(tmp_path) -> None:
    base = pd.DataFrame(
        [
            {
                "lat": 37.0,
                "lon": 37.0,
                "baseline_rate": 1e-6,
                "triggered_rate": 0.2,
                "total_rate": 0.2,
                "probability_24h": 0.18,
                "probability_7d": 0.75,
                "relative_risk": 20.0,
                "risk_level": "high",
            }
        ]
    )
    framed = attach_public_zone(attach_outlook(base))
    csv_path, _geojson_path = write_risk_grid(framed, tmp_path / "grid.csv")
    written = pd.read_csv(csv_path)
    assert list(written.columns) == list(GRID_COLUMNS) + list(PUBLIC_COLUMNS)
