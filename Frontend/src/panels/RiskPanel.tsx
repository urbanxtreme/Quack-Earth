import { useState } from "react";
import type { RiskResponse, EarthquakeEvent } from "../api";

interface RiskPanelProps {
  riskData: RiskResponse | null;
  isLoading: boolean;
  activeLocationName?: string;
  selectedCoordinates: { lat: number; lon: number } | null;
  timeWindow: "24h" | "72h" | "7d";
  setTimeWindow: (tw: "24h" | "72h" | "7d") => void;
  onRecalculate: () => void;
  onOpenSitRep?: () => void;
  selectedMainshock?: EarthquakeEvent | null;
  sequenceDetails?: {
    confidence?: string;
    foreshock_count?: number;
    aftershock_count?: number;
    search_radius_km?: number;
    omori_fit?: {
      k?: number;
      c_days?: number;
      p?: number;
      method?: string;
    };
    geometry?: {
      strike_deg?: number;
    };
  } | null;
  isSeqLoading?: boolean;
}

export default function RiskPanel({
  riskData,
  isLoading,
  activeLocationName,
  selectedCoordinates,
  timeWindow,
  setTimeWindow,
  onRecalculate,
  onOpenSitRep,
  selectedMainshock,
  sequenceDetails,
  isSeqLoading,
}: RiskPanelProps) {
  const [radiusKm, setRadiusKm] = useState<number>(50);

  const primaryZone = riskData?.zones?.[0];
  const riskScore = primaryZone?.risk_score ?? 0;
  const relativeBaseline = primaryZone?.relative_to_baseline ?? 1.0;
  const expectedEvents = primaryZone?.expected_events ?? 0;
  const baselineRate = riskData?.baseline_rate ?? 0.018;

  // Civil defense verdict and guidance from engine
  const publicZone = riskData?.public_zone || primaryZone?.public_zone || "usual";
  const verdictText = riskData?.verdict;
  const guidance = riskData?.guidance;
  const excavationAction = riskData?.excavation_action || (riskScore >= 0.7 ? "pause" : riskScore >= 0.4 ? "open-area checks" : "continue");

  // Determine alert category & styling
  const getRiskCategory = (score: number) => {
    if (score >= 0.85) {
      return {
        label: "CRITICAL ALERT",
        colorClass: "risk-critical",
        colorHex: "#ef4444",
        advice: "Substantial probability of aftershock or clustered activity. Keep emergency go-bags accessible and secure heavy overhead objects.",
        statusPill: "Immediate Precaution",
      };
    }
    if (score >= 0.7) {
      return {
        label: "HIGH ANTICIPATION",
        colorClass: "risk-high",
        colorHex: "#f97316",
        advice: "Heightened seismic rate relative to regional background. Review utility shutoffs and confirm family check-in plans.",
        statusPill: "Elevated Readiness",
      };
    }
    if (score >= 0.45) {
      return {
        label: "ELEVATED RISK",
        colorClass: "risk-elevated",
        colorHex: "#eab308",
        advice: "Clustered foreshocks or regional stress recorded. Maintain situational awareness and keep alert devices charged.",
        statusPill: "Advisory Active",
      };
    }
    if (score >= 0.2) {
      return {
        label: "MODERATE BACKGROUND",
        colorClass: "risk-moderate",
        colorHex: "#06b6d4",
        advice: "Low-to-moderate background activity within expected regional variation. Standard preparedness recommended.",
        statusPill: "Nominal Caution",
      };
    }
    return {
      label: "LOW / STABLE",
      colorClass: "risk-low",
      colorHex: "#10b981",
      advice: "Seismic baseline steady. No anomalous swarm or acceleration detected in the active time window.",
      statusPill: "Baseline Normal",
    };
  };

  const riskCat = getRiskCategory(riskScore);
  const strokeDasharray = 2 * Math.PI * 52;
  const strokeDashoffset = strokeDasharray * (1 - Math.min(Math.max(riskScore, 0), 1));

  return (
    <div className="glass-panel risk-panel">
      <div className="panel-header">
        <div className="panel-title-row">
          <span className="panel-icon">📊</span>
          <h2 className="panel-title">Risk Anticipation</h2>
          <span className={`status-pill ${riskCat.colorClass}`}>{riskCat.statusPill}</span>
        </div>
        <p className="panel-subtitle">Probabilistic short-term cluster & rate model</p>
      </div>

      {/* Target Location Metadata */}
      <div className="risk-target-card">
        <div className="target-icon-wrap">
          <span className="target-icon">📍</span>
        </div>
        <div className="target-details">
          <div className="target-name">
            {activeLocationName || "Global / Selected Epicenter"}
          </div>
          <div className="target-coords font-mono">
            {selectedCoordinates
              ? `${selectedCoordinates.lat.toFixed(4)}°N, ${selectedCoordinates.lon.toFixed(4)}°E`
              : "Click on map or search place"}
          </div>
        </div>
      </div>

      {/* AI Civil Defense Commander Directive Card */}
      <div className={`civil-defense-directive-card zone-${publicZone.toLowerCase()}`}>
        <div className="directive-header-row">
          <div className="directive-badge-cluster">
            <span className="directive-tag font-mono">
              <span className="directive-radar-dot" />
              AI CIVIL PROTECTION DIRECTIVE
            </span>
            <div className="directive-pill-row">
              <span className={`directive-zone-pill zone-${publicZone.toLowerCase()}`}>
                ZONE: {publicZone.toUpperCase()}
              </span>
              <span className={`excavation-pill action-${excavationAction.toLowerCase().replace(/\s+/g, '-')}`}>
                EXCAVATION: {excavationAction.toUpperCase()}
              </span>
            </div>
          </div>
        </div>

        {verdictText ? (
          <p className="directive-verdict-text">{verdictText}</p>
        ) : (
          <p className="directive-verdict-text">
            Evaluating Omori aftershock probabilities and background rate models for the next 24 hours.
          </p>
        )}

        <div className="directive-authority-banner">
          <span className="authority-icon">⚠️</span>
          <span className="authority-text font-mono">
            Mandatory Incident Limit: Field incident commander decides binding evacuation.
          </span>
        </div>
      </div>

      {/* Time Window & Radius selector */}
      <div className="risk-controls-grid">
        <div className="control-item">
          <div className="control-header">
            <span className="control-label">Horizon</span>
          </div>
          <div className="button-toggle-row">
            <button
              type="button"
              className={`toggle-chip ${timeWindow === "24h" ? "active" : ""}`}
              onClick={() => setTimeWindow("24h")}
            >
              24h
            </button>
            <button
              type="button"
              className={`toggle-chip ${timeWindow === "72h" ? "active" : ""}`}
              onClick={() => setTimeWindow("72h")}
            >
              72h
            </button>
            <button
              type="button"
              className={`toggle-chip ${timeWindow === "7d" ? "active" : ""}`}
              onClick={() => setTimeWindow("7d")}
            >
              7d
            </button>
          </div>
        </div>

        <div className="control-item">
          <div className="control-header">
            <span className="control-label">Radius</span>
            <span className="control-val-badge font-mono">{radiusKm} km</span>
          </div>
          <div className="slider-track-wrap">
            <input
              type="range"
              min="25"
              max="150"
              step="25"
              value={radiusKm}
              onChange={(e) => setRadiusKm(parseInt(e.target.value, 10))}
              className="styled-range"
            />
          </div>
        </div>
      </div>

      {/* Circular Gauge Display */}
      <div className="gauge-container">
        {isLoading ? (
          <div className="gauge-loader">
            <div className="pulse-loader" />
            <span className="loading-text">Computing Omori hazard...</span>
          </div>
        ) : (
          <div className="gauge-wrapper">
            <svg className="gauge-svg" viewBox="0 0 140 140">
              <circle
                className="gauge-bg"
                cx="70"
                cy="70"
                r="52"
                strokeWidth="10"
              />
              <circle
                className={`gauge-progress ${riskCat.colorClass}`}
                cx="70"
                cy="70"
                r="52"
                strokeWidth="10"
                strokeDasharray={strokeDasharray}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                transform="rotate(-90 70 70)"
              />
            </svg>
            <div className="gauge-content">
              <span className="gauge-percent font-mono">
                {(riskScore * 100).toFixed(0)}
                <span className="gauge-percent-symbol">%</span>
              </span>
              <span className="gauge-label font-mono">Risk Index</span>
            </div>
          </div>
        )}

        <div className="gauge-meta">
          <div className="meta-badge-row">
            <span className={`cat-label font-bold ${riskCat.colorClass}`}>
              {riskCat.label}
            </span>
          </div>
          <p className="gauge-sub">
            Model rate is{" "}
            <strong className="text-highlight">
              {relativeBaseline.toFixed(1)}x
            </strong>{" "}
            historical regional baseline.
          </p>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="risk-metrics-row">
        <div className="metric-box">
          <span className="metric-title">Baseline Rate</span>
          <span className="metric-val font-mono">{baselineRate.toFixed(4)}/d</span>
        </div>
        <div className="metric-box">
          <span className="metric-title">Expected M4+</span>
          <span className="metric-val font-mono">{expectedEvents.toFixed(2)}</span>
        </div>
        <div className="metric-box">
          <span className="metric-title">Relative Ratio</span>
          <span className="metric-val font-mono text-cyan">
            {relativeBaseline.toFixed(1)}×
          </span>
        </div>
      </div>

      {/* Sequence Breakdown & Modified Omori-Utsu Model Parameters */}
      {(selectedMainshock || sequenceDetails) && (
        <div className="sequence-analysis-card">
          <div className="sequence-header-row">
            <h4 className="sequence-title">
              <span>🔬 Sequence & Omori Law</span>
            </h4>
            <span className="count-pill">
              {isSeqLoading ? "Fitting..." : sequenceDetails?.confidence ? `${sequenceDetails.confidence.toUpperCase()}` : "ACTIVE"}
            </span>
          </div>

          {selectedMainshock && (
            <div className="seq-mainshock-meta font-mono text-xs text-muted">
              ★ Mainshock: M{selectedMainshock.magnitude} ({selectedMainshock.place || "Epicenter"})
            </div>
          )}

          <div className="sequence-stats-grid">
            <div className="seq-stat-box">
              <span className="seq-stat-val font-mono">{sequenceDetails?.foreshock_count ?? 0}</span>
              <span className="seq-stat-lbl">Foreshocks</span>
            </div>
            <div className="seq-stat-box">
              <span className="seq-stat-val font-mono text-purple">{sequenceDetails?.aftershock_count ?? 0}</span>
              <span className="seq-stat-lbl">Aftershocks</span>
            </div>
            <div className="seq-stat-box">
              <span className="seq-stat-val font-mono text-cyan">
                {sequenceDetails?.search_radius_km ? `${sequenceDetails.search_radius_km.toFixed(0)} km` : "Adaptive"}
              </span>
              <span className="seq-stat-lbl">Search Radius</span>
            </div>
          </div>

          <div className="omori-formula-box">
            <div className="omori-formula-title font-mono">r(t) = K / (t + c)^p</div>
            <div className="omori-param-row font-mono">
              <span>K = {sequenceDetails?.omori_fit?.k?.toFixed(2) ?? "1.85"}</span>
              <span>c = {sequenceDetails?.omori_fit?.c_days?.toFixed(3) ?? "0.080"}d</span>
              <span>p = {sequenceDetails?.omori_fit?.p?.toFixed(2) ?? "1.05"}</span>
            </div>
            <div className="omori-param-row font-mono omori-param-sub">
              <span>Method: {sequenceDetails?.omori_fit?.method === "maximum_likelihood_estimation" ? "MLE Fitted" : "Regional Prior"}</span>
              {sequenceDetails?.geometry?.strike_deg !== undefined && (
                <span>Strike θ: {sequenceDetails.geometry.strike_deg.toFixed(1)}°</span>
              )}
            </div>
          </div>

          <div className="legend-disclaimer">
            💡 Decay parameters estimate statistical aftershock frequency under inhomogeneous Poisson assumptions.
          </div>
        </div>
      )}

      {/* Ranked Emergency Sectors */}
      {guidance?.sectors && guidance.sectors.length > 0 && (
        <div className="sectors-card">
          <div className="sectors-header">
            <div className="sectors-title-wrap">
              <span className="sectors-icon">🎯</span>
              <h4 className="sectors-title">Emergency Response Sectors</h4>
            </div>
            <span className="sectors-count font-mono">
              {guidance.sectors.length} {guidance.sectors.length === 1 ? "sector" : "sectors"}
            </span>
          </div>
          <div className="sectors-list">
            {guidance.sectors.map((sec, idx) => (
              <div key={idx} className={`sector-item zone-${sec.public_zone.toLowerCase()}`}>
                <div className="sector-info-row">
                  <div className="sector-place-wrap">
                    <span className="sector-bullet-indicator" />
                    <span className="sector-place">{sec.place}</span>
                  </div>
                  <div className="sector-badges-cluster">
                    <span className={`sector-zone-badge zone-${sec.public_zone.toLowerCase()}`}>
                      {sec.public_zone.toUpperCase()}
                    </span>
                    <span className={`sector-excavation action-${sec.excavation.toLowerCase().replace(/\s+/g, '-')}`}>
                      {sec.excavation.toUpperCase()}
                    </span>
                  </div>
                </div>
                
                <div className="sector-details-row font-mono">
                  <span className="sector-stat-chip">
                    <span className="chip-key">P(M4+):</span>
                    <span className="chip-val font-bold">{(sec.probability_24h * 100).toFixed(1)}%</span>
                  </span>
                  {sec.probability_m5_24h !== undefined && (
                    <span className="sector-stat-chip">
                      <span className="chip-key">P(M5+):</span>
                      <span className="chip-val font-bold">{(sec.probability_m5_24h * 100).toFixed(1)}%</span>
                    </span>
                  )}
                </div>
                
                <p className="sector-action-text">{sec.action}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actionable Guidance Card */}
      <div className={`guidance-card ${riskCat.colorClass}`}>
        <div className="guidance-header">
          <span className="guidance-icon">🛡️</span>
          <h4 className="guidance-title">Field Recommendation</h4>
        </div>
        <p className="guidance-text">{riskCat.advice}</p>
      </div>

      {/* Actions */}
      <div className="panel-actions-grid">
        <button
          type="button"
          className="btn-primary-glass"
          onClick={onRecalculate}
          disabled={isLoading}
        >
          {isLoading ? <span className="btn-spinner" /> : "⚡ Recalculate Hazard Window"}
        </button>

        {onOpenSitRep && (
          <button
            type="button"
            className="btn-sitrep-export"
            onClick={onOpenSitRep}
            title="Generate and print an official Incident Situation Report"
          >
            📋 Generate Incident SitRep (PDF/Print)
          </button>
        )}
      </div>
    </div>
  );
}
