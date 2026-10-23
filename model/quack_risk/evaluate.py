"""Retrospective metrics and the four demo plots. No network calls."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from quack_risk.calibrate import (
    FIT_DAYS,
    baseline_log_likelihood,
    cell_index,
    observation_counts,
    prepare_bin,
    prepare_bins,
    select_mainshock,
    total_rate,
    triggered_rate,
    window_log_likelihood,
)
from quack_risk.config import DEMO_AS_OF, DEMO_BOUNDS, RiskParams
from quack_risk.geo import grid_centers

CAPTURE_MAGNITUDE = 4.5
OMORI_AGES_DAYS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0)


def capture_curve(rate: np.ndarray, counts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fraction of cells flagged against fraction of events captured, highest rate first."""
    values = np.asarray(rate, dtype=float)
    observed = np.asarray(counts, dtype=float)
    order = np.argsort(values, kind="mergesort")[::-1]
    ranked = observed[order]
    total = float(ranked.sum())
    share = np.arange(1, len(values) + 1, dtype=float) / len(values)
    if total <= 0.0:
        return share, np.zeros(len(values), dtype=float)
    return share, np.cumsum(ranked) / total


def top_fraction_capture(rate: np.ndarray, counts: np.ndarray, fraction: float = 0.2) -> float:
    """Share of events inside the highest-rate ``fraction`` of cells."""
    share, captured = capture_curve(rate, counts)
    if float(np.asarray(counts).sum()) <= 0.0:
        return float("nan")
    cutoff = int(np.searchsorted(share, fraction, side="left"))
    cutoff = min(cutoff, len(captured) - 1)
    return float(captured[cutoff])


def evaluation_metrics(
    bins,
    params: RiskParams,
    *,
    capture_rate: np.ndarray,
    capture_counts: np.ndarray,
) -> dict:
    """Likelihood, reliability, and the top-20% capture number."""
    full = window_log_likelihood(bins, k=params.k, c_days=params.c_days, p=params.p)
    baseline = baseline_log_likelihood(bins)
    predicted = [float(total_rate(prepared, k=params.k, c_days=params.c_days, p=params.p).sum()) for prepared in bins]
    observed = [float(prepared.counts.sum()) for prepared in bins]
    return {
        "log_likelihood_full": full,
        "log_likelihood_baseline": baseline,
        "full_beats_baseline": bool(full > baseline),
        "top20_capture": top_fraction_capture(capture_rate, capture_counts, 0.2),
        "mean_predicted_per_day": float(np.mean(predicted)) if predicted else 0.0,
        "mean_observed_per_day": float(np.mean(observed)) if observed else 0.0,
        "k": params.k,
        "c_days": params.c_days,
        "p": params.p,
        "n_days": len(bins),
    }


def write_evaluation(
    catalog: pd.DataFrame,
    params: RiskParams,
    out_dir: str | Path,
    *,
    bounds: tuple[float, float, float, float] = DEMO_BOUNDS,
    resolution_deg: float = 0.2,
    snapshot_as_of: str = DEMO_AS_OF,
) -> dict:
    """Write the four plots and ``metrics.json``. Returns the metrics."""
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    mainshock = select_mainshock(catalog)
    origin = pd.Timestamp(mainshock["time"])
    if origin.tzinfo is None:
        origin = origin.tz_localize("UTC")
    design = prepare_bins(
        catalog,
        origin=origin,
        bounds=bounds,
        resolution_deg=resolution_deg,
        params=params,
        n_days=FIT_DAYS,
    )
    snapshot = prepare_bin(
        catalog,
        as_of=snapshot_as_of,
        bounds=bounds,
        resolution_deg=resolution_deg,
        params=params,
        count_through=pd.Timestamp(snapshot_as_of) + pd.Timedelta(days=1),
    )
    capture_counts = observation_counts(
        catalog,
        as_of=snapshot.as_of,
        count_through=snapshot.as_of + pd.Timedelta(days=1),
        bounds=bounds,
        resolution_deg=resolution_deg,
        magnitude_threshold=CAPTURE_MAGNITUDE,
    )
    rate = total_rate(snapshot, k=params.k, c_days=params.c_days, p=params.p)
    metrics = evaluation_metrics(design, params, capture_rate=rate, capture_counts=capture_counts)
    metrics["origin"] = origin.strftime("%Y-%m-%dT%H:%M:%SZ")
    metrics["mainshock_magnitude"] = float(mainshock["magnitude"])
    metrics["snapshot_as_of"] = snapshot.as_of.strftime("%Y-%m-%dT%H:%M:%SZ")

    _plot_omori(catalog, mainshock, params, bounds, resolution_deg, destination / "omori_decay.png")
    _plot_snapshot(rate, snapshot.baseline, bounds, resolution_deg, mainshock, snapshot.as_of, destination / "risk_snapshot_24h.png")
    _plot_capture(rate, capture_counts, metrics["top20_capture"], destination / "capture_curve.png")
    _plot_likelihood(metrics, destination / "likelihood_bars.png")
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def _plot_omori(catalog, mainshock, params, bounds, resolution_deg, path: Path) -> None:
    origin = pd.Timestamp(mainshock["time"])
    if origin.tzinfo is None:
        origin = origin.tz_localize("UTC")
    index = cell_index(float(mainshock["latitude"]), float(mainshock["longitude"]), bounds, resolution_deg)
    only = catalog.loc[[mainshock.name]]
    full_rate = []
    mainshock_rate = []
    for age in OMORI_AGES_DAYS:
        as_of = origin + pd.Timedelta(days=age)
        full = prepare_bin(catalog, as_of=as_of, bounds=bounds, resolution_deg=resolution_deg, params=params)
        alone = prepare_bin(only, as_of=as_of, bounds=bounds, resolution_deg=resolution_deg, params=params)
        full_rate.append(float(triggered_rate(full, k=params.k, c_days=params.c_days, p=params.p)[index]))
        mainshock_rate.append(float(triggered_rate(alone, k=params.k, c_days=params.c_days, p=params.p)[index]))

    figure, axis = plt.subplots(figsize=(8, 5))
    axis.semilogy(OMORI_AGES_DAYS, full_rate, marker="o", label="All recent earthquakes")
    axis.semilogy(OMORI_AGES_DAYS, mainshock_rate, label=f"Mainshock only, M {float(mainshock['magnitude']):.1f}")
    axis.set_xlabel("Days since the mainshock")
    axis.set_ylabel("Triggered events per day in the epicentral cell")
    axis.set_title("Aftershock rate at the epicenter")
    axis.legend()
    axis.grid(True, which="both", alpha=0.3)
    figure.tight_layout()
    figure.savefig(path, dpi=120)
    plt.close(figure)


def _plot_snapshot(rate, baseline, bounds, resolution_deg, mainshock, as_of, path: Path) -> None:
    latitudes, longitudes = grid_centers(bounds, resolution_deg)
    relative = rate / np.maximum(baseline, 1e-30)
    image = np.log10(np.maximum(relative.reshape(len(latitudes), len(longitudes)), 1e-6))
    figure, axis = plt.subplots(figsize=(8, 6))
    picture = axis.imshow(
        image,
        origin="lower",
        extent=[bounds[0], bounds[2], bounds[1], bounds[3]],
        aspect="auto",
    )
    axis.scatter(
        [float(mainshock["longitude"])],
        [float(mainshock["latitude"])],
        marker="*",
        s=80,
        c="white",
        edgecolors="black",
        label="Mainshock",
    )
    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")
    axis.set_title(f"log10 relative risk at {as_of.strftime('%Y-%m-%d %H:%M')} UTC")
    axis.legend(loc="upper right")
    colorbar = figure.colorbar(picture, ax=axis)
    colorbar.set_label("log10 relative risk")
    figure.tight_layout()
    figure.savefig(path, dpi=120)
    plt.close(figure)


def _plot_capture(rate, counts, top20: float, path: Path) -> None:
    share, captured = capture_curve(rate, counts)
    figure, axis = plt.subplots(figsize=(8, 5))
    axis.plot(share, captured, label="Highest rate first")
    axis.plot([0.0, 1.0], [0.0, 1.0], linestyle="--", color="gray", label="Flat map")
    if np.isfinite(top20):
        axis.scatter([0.2], [top20], zorder=3, label=f"Top 20% captures {top20:.0%}")
    axis.set_xlabel("Fraction of cells flagged")
    axis.set_ylabel("Fraction of magnitude 4.5+ events captured")
    axis.set_title("Where the next day's larger events fall")
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=120)
    plt.close(figure)


def _plot_likelihood(metrics: dict, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7, 5))
    labels = ["Baseline only", "Fitted rate"]
    values = [metrics["log_likelihood_baseline"], metrics["log_likelihood_full"]]
    bars = axis.bar(labels, values)
    axis.set_ylim(min(values) * 1.12, 0)
    for bar, value in zip(bars, values):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.0f}",
            ha="center",
            va="top",
        )
    axis.set_ylabel("Poisson log-likelihood (higher is better)")
    verdict = "fitted rate is higher" if metrics["full_beats_baseline"] else "baseline is higher"
    axis.set_title(f"Ten days after the mainshock: {verdict}")
    figure.tight_layout()
    figure.savefig(path, dpi=120)
    plt.close(figure)
