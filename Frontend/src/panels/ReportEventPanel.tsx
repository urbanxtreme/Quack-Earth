import { useState } from "react";
import { submitLocalEvent } from "../api";

interface ReportEventPanelProps {
  currentMapCenter: { lat: number; lon: number };
  onEventSubmitted: () => void;
}

export default function ReportEventPanel({
  currentMapCenter,
  onEventSubmitted,
}: ReportEventPanelProps) {
  const [lat, setLat] = useState<string>(currentMapCenter.lat.toFixed(4));
  const [lon, setLon] = useState<string>(currentMapCenter.lon.toFixed(4));
  const [magnitude, setMagnitude] = useState<string>("4.5");
  const [source, setSource] = useState<string>("user_report");
  const [note, setNote] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const handleUseMapCenter = () => {
    setLat(currentMapCenter.lat.toFixed(4));
    setLon(currentMapCenter.lon.toFixed(4));
    setMessage({
      type: "success",
      text: "Updated coordinates from map center crosshair.",
    });
    setTimeout(() => setMessage(null), 3000);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const parsedLat = parseFloat(lat);
    const parsedLon = parseFloat(lon);
    const parsedMag = parseFloat(magnitude);

    if (isNaN(parsedLat) || parsedLat < -90 || parsedLat > 90) {
      setMessage({ type: "error", text: "Latitude must be between -90 and 90." });
      return;
    }
    if (isNaN(parsedLon) || parsedLon < -180 || parsedLon > 180) {
      setMessage({ type: "error", text: "Longitude must be between -180 and 180." });
      return;
    }
    if (isNaN(parsedMag) || parsedMag < 1.0 || parsedMag > 10.0) {
      setMessage({ type: "error", text: "Magnitude must be between 1.0 and 10.0." });
      return;
    }

    setIsSubmitting(true);
    setMessage(null);

    try {
      const res = await submitLocalEvent({
        lat: parsedLat,
        lon: parsedLon,
        magnitude: parsedMag,
        source,
        note: note.trim() || undefined,
        time: new Date().toISOString(),
      });

      setMessage({
        type: "success",
        text: `Event recorded (${res.event_id || "local"}). Nearby risk updated!`,
      });
      setNote("");
      onEventSubmitted();
    } catch {
      setMessage({
        type: "error",
        text: "Could not submit event. Please check inputs.",
      });
    } finally {
      setIsSubmitting(false);
      setTimeout(() => setMessage(null), 5000);
    }
  };

  return (
    <div className="glass-panel report-panel">
      <div className="panel-header">
        <div className="panel-title-row">
          <span className="panel-icon">📝</span>
          <h2 className="panel-title">Report Local Event</h2>
        </div>
        <p className="panel-subtitle">
          Submit immediate field observations to update offline edge anticipation
        </p>
      </div>

      <form className="report-form" onSubmit={handleSubmit}>
        <div className="form-action-row">
          <button
            type="button"
            className="btn-glass btn-sm"
            onClick={handleUseMapCenter}
            title="Snap coordinates to current map center"
          >
            🎯 Use Map Center ({currentMapCenter.lat.toFixed(2)}°, {currentMapCenter.lon.toFixed(2)}°)
          </button>
        </div>

        <div className="form-row-2col">
          <div className="form-group">
            <label className="form-label" htmlFor="report-lat">
              Latitude (°)
            </label>
            <input
              id="report-lat"
              type="number"
              step="any"
              className="glass-input font-mono"
              placeholder="e.g. 35.6762"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="report-lon">
              Longitude (°)
            </label>
            <input
              id="report-lon"
              type="number"
              step="any"
              className="glass-input font-mono"
              placeholder="e.g. 139.6503"
              value={lon}
              onChange={(e) => setLon(e.target.value)}
              required
            />
          </div>
        </div>

        <div className="form-row-2col">
          <div className="form-group">
            <label className="form-label" htmlFor="report-mag">
              Estimated Magnitude (M)
            </label>
            <input
              id="report-mag"
              type="number"
              step="0.1"
              min="1.0"
              max="9.9"
              className="glass-input font-mono"
              placeholder="e.g. 5.1"
              value={magnitude}
              onChange={(e) => setMagnitude(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="report-source">
              Observation Source
            </label>
            <select
              id="report-source"
              className="glass-input"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="user_report">Field Eyewitness (User)</option>
              <option value="accelerometer">Local Accelerometer / IoT</option>
              <option value="local_station">Community Seismometer</option>
              <option value="macroseismic">Macroseismic Intensity</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="report-notes">
            Observation Notes / Shaking Effects
          </label>
          <textarea
            id="report-notes"
            rows={3}
            className="glass-textarea"
            placeholder="Describe shaking duration, damage, rattling windows, sound, etc..."
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>

        {message && (
          <div className={`form-feedback-banner ${message.type}`}>
            <span className="feedback-icon">{message.type === "success" ? "✓" : "⚠️"}</span>
            <span>{message.text}</span>
          </div>
        )}

        <div className="form-submit-row">
          <button
            type="submit"
            className="btn-primary full-width"
            disabled={isSubmitting}
            id="submit-local-event-btn"
          >
            {isSubmitting ? (
              <>
                <span className="btn-spinner" /> Submitting Report...
              </>
            ) : (
              <>
                <span>Publish Local Observation</span>
                <span className="btn-arrow">→</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
