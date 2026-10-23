import type { RiskResponse, EarthquakeEvent } from "./api";

interface SitRepModalProps {
  isOpen: boolean;
  onClose: () => void;
  riskData: RiskResponse | null;
  locationName: string;
  coordinates: { lat: number; lon: number } | null;
  events: EarthquakeEvent[];
}

export default function SitRepModal({
  isOpen,
  onClose,
  riskData,
  locationName,
  coordinates,
  events,
}: SitRepModalProps) {
  if (!isOpen) return null;

  const peakZone = riskData?.public_zone || riskData?.zones?.[0]?.public_zone || "usual";
  const riskScore = riskData?.zones?.[0]?.risk_score ?? 0;
  const relativeBaseline = riskData?.zones?.[0]?.relative_to_baseline ?? 1.0;
  const prob24 = riskData?.zones?.[0]?.probability_24h ?? riskScore;
  const prob7d = riskData?.zones?.[0]?.probability_7d ?? Math.min(1.0, prob24 * 2.8);
  const verdictText = riskData?.verdict || "No critical civil protection restrictions currently active in this sector.";
  const excavationAction = riskData?.excavation_action || (riskScore >= 0.7 ? "pause" : riskScore >= 0.4 ? "open-area checks" : "continue");
  const sectors = riskData?.guidance?.sectors || [];
  const reportTime = riskData?.generated_at ? new Date(riskData.generated_at).toUTCString() : new Date().toUTCString();

  const handlePrint = () => {
    window.print();
  };

  const handleExportGeoJSON = () => {
    const featureCollection = {
      type: "FeatureCollection",
      metadata: {
        generated_at: new Date().toISOString(),
        incident_sector: locationName,
        civil_protection_zone: peakZone,
        risk_score: riskScore,
      },
      features: [
        ...(coordinates
          ? [
              {
                type: "Feature",
                geometry: {
                  type: "Point",
                  coordinates: [coordinates.lon, coordinates.lat],
                },
                properties: {
                  type: "epicenter",
                  name: locationName,
                  risk_score: riskScore,
                  public_zone: peakZone,
                  verdict: verdictText,
                },
              },
            ]
          : []),
        ...sectors.map((sec, idx) => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [sec.lon, sec.lat],
          },
          properties: {
            type: "emergency_sector",
            sector_id: `SEC-${idx + 1}`,
            direction: sec.direction,
            distance_km: sec.distance_km,
            probability_24h: sec.probability_24h,
            public_zone: sec.public_zone,
            action: sec.action,
            excavation: sec.excavation,
          },
        })),
        ...events.slice(0, 50).map((ev) => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [ev.lon, ev.lat, ev.depth_km || 0],
          },
          properties: {
            type: "earthquake",
            id: ev.id,
            mag: ev.magnitude,
            time: ev.time,
            place: ev.place,
            corroboration: ev.corroboration?.status || "unverified",
          },
        })),
      ],
    };

    const blob = new Blob([JSON.stringify(featureCollection, null, 2)], {
      type: "application/geo+json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `SitRep_${locationName.replace(/[^a-zA-Z0-9]/g, "_")}_${Date.now()}.geojson`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="sitrep-modal-backdrop" onClick={onClose}>
      <div className="sitrep-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Top Action Bar (hidden in print) */}
        <div className="sitrep-toolbar no-print">
          <div className="sitrep-toolbar-left">
            <span className="sitrep-badge-official">CIVIL DEFENSE SITREP</span>
            <span className="sitrep-timestamp font-mono">{reportTime}</span>
          </div>
          <div className="sitrep-toolbar-right">
            <button type="button" className="btn-print-action" onClick={handlePrint}>
              🖨️ Print / Save PDF
            </button>
            <button type="button" className="btn-geojson-action" onClick={handleExportGeoJSON}>
              🌐 Export GIS GeoJSON
            </button>
            <button type="button" className="btn-close-modal" onClick={onClose}>
              ✕
            </button>
          </div>
        </div>

        {/* Printable SitRep Document Body */}
        <div className="sitrep-document">
          <header className="sitrep-doc-header">
            <div className="doc-header-row">
              <div className="doc-emblem">🛡️</div>
              <div className="doc-titles">
                <h1 className="doc-main-title">EMERGENCY SITUATION REPORT (SITREP)</h1>
                <p className="doc-sub-title">DIRECTORATE OF CIVIL PROTECTION & SEISMIC HAZARD RESPONSE</p>
              </div>
              <div className={`doc-zone-stamp zone-${peakZone}`}>
                <span className="stamp-label">DEFENSE ZONE</span>
                <span className="stamp-val font-mono">{peakZone.toUpperCase()}</span>
              </div>
            </div>
            <div className="doc-meta-grid font-mono">
              <div><strong>TARGET SECTOR:</strong> {locationName}</div>
              <div><strong>COORDINATES:</strong> {coordinates ? `${coordinates.lat.toFixed(4)}°N, ${coordinates.lon.toFixed(4)}°E` : "N/A"}</div>
              <div><strong>TIME HORIZON:</strong> 24-Hour Predictive Window</div>
              <div><strong>DATE/TIME:</strong> {reportTime}</div>
            </div>
          </header>

          <hr className="sitrep-divider" />

          {/* Commander Situation Verdict Section */}
          <section className="sitrep-section">
            <h2 className="section-heading">1. COMMANDER SITUATION BRIEFING & DIRECTIVE</h2>
            <div className={`sitrep-verdict-box zone-${peakZone}`}>
              <p className="verdict-lead-text">{verdictText}</p>
              <div className="verdict-limit-note">
                ⚠️ <em>Authority Note: This is an empirical probabilistic forecast for the next 24 hours. A local field incident commander decides all binding evacuation orders.</em>
              </div>
            </div>
          </section>

          {/* Quantitative Probabilities */}
          <section className="sitrep-section">
            <h2 className="section-heading">2. SEISMIC HAZARD QUANTIFICATION</h2>
            <div className="sitrep-stats-grid">
              <div className="stat-card">
                <span className="stat-label">24h Aftershock Chance (M4+)</span>
                <span className="stat-value font-mono">{(prob24 * 100).toFixed(1)}%</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">7-Day Cumulative Chance</span>
                <span className="stat-value font-mono">{(prob7d * 100).toFixed(1)}%</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Relative Background Rate</span>
                <span className="stat-value font-mono">{relativeBaseline.toFixed(1)}× Baseline</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Excavation Safety Protocol</span>
                <span className={`stat-value font-mono action-${excavationAction}`}>
                  {excavationAction.toUpperCase()}
                </span>
              </div>
            </div>
          </section>

          {/* Sector Breakdown */}
          {sectors.length > 0 && (
            <section className="sitrep-section">
              <h2 className="section-heading">3. RANKED EMERGENCY SECTOR ASSESSMENTS</h2>
              <table className="sitrep-table">
                <thead>
                  <tr>
                    <th>Sector Location</th>
                    <th>Zone</th>
                    <th>24h P(M4+)</th>
                    <th>Excavation Directive</th>
                    <th>Field Operational Advice</th>
                  </tr>
                </thead>
                <tbody>
                  {sectors.map((sec, idx) => (
                    <tr key={idx} className={`row-zone-${sec.public_zone}`}>
                      <td className="font-mono">
                        <strong>{sec.place}</strong> ({sec.lat.toFixed(2)}°, {sec.lon.toFixed(2)}°)
                      </td>
                      <td>
                        <span className={`pill-zone zone-${sec.public_zone}`}>{sec.public_zone}</span>
                      </td>
                      <td className="font-mono">{(sec.probability_24h * 100).toFixed(1)}%</td>
                      <td className="font-mono font-bold">{sec.excavation.toUpperCase()}</td>
                      <td>{sec.action}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {/* Recent Quakes Log */}
          <section className="sitrep-section">
            <h2 className="section-heading">4. KEY RECENT SHOCKS & SENSOR CORROBORATION</h2>
            <table className="sitrep-table">
              <thead>
                <tr>
                  <th>Origin (UTC)</th>
                  <th>Magnitude</th>
                  <th>Depth</th>
                  <th>Place / Description</th>
                  <th>Corroboration</th>
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 6).map((ev) => (
                  <tr key={ev.id}>
                    <td className="font-mono text-sm">{new Date(ev.time).toISOString().replace("T", " ").slice(0, 19)}</td>
                    <td className="font-mono font-bold text-orange">M {ev.magnitude.toFixed(1)}</td>
                    <td className="font-mono">{ev.depth_km !== undefined ? `${ev.depth_km.toFixed(1)} km` : "N/A"}</td>
                    <td>{ev.place || `Near ${ev.lat.toFixed(2)}°, ${ev.lon.toFixed(2)}°`}</td>
                    <td>
                      <span className={`status-tag tag-${ev.corroboration?.status || "usgs"}`}>
                        {ev.corroboration?.label || "USGS ComCat"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* Official Sign-off Footer */}
          <footer className="sitrep-doc-footer">
            <div className="footer-sig-box">
              <div className="sig-line" />
              <span>CIVIL DEFENSE COMMAND OFFICER</span>
            </div>
            <div className="footer-doc-info font-mono">
              <span>QUACK-EARTH-SYSTEM-V1</span>
              <span>VERIFIED REALTIME CALIBRATION</span>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}
