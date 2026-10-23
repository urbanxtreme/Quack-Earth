import { useState } from "react";
import type { SystemStatus as SystemStatusType } from "../api";
import { refreshCatalog } from "../api";

interface SystemStatusProps {
  status: SystemStatusType | null;
  onRefreshSuccess?: () => void;
}

export default function SystemStatus({ status, onRefreshSuccess }: SystemStatusProps) {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setFeedback(null);
    try {
      const res = await refreshCatalog({ min_magnitude: 2.5, days_back: 14 });
      if (res.status === "updated") {
        setFeedback(`Catalog synced: +${res.events_fetched ?? 0} events`);
        onRefreshSuccess?.();
      } else {
        setFeedback(res.message || "Using edge cache");
      }
    } catch {
      setFeedback("Sync failed - running offline");
    } finally {
      setIsRefreshing(false);
      setTimeout(() => setFeedback(null), 4000);
    }
  };

  const isOnline = status?.mode === "online";

  return (
    <div className="glass-card status-card">
      <div className="card-header">
        <div className="status-title-group">
          <span className={`status-indicator-dot ${isOnline ? "online" : "offline"}`} />
          <h3 className="card-title">System Edge Status</h3>
        </div>
        <span className={`badge ${isOnline ? "badge-success" : "badge-warning"}`}>
          {status?.mode ? status.mode.toUpperCase() : "OFFLINE"}
        </span>
      </div>

      <div className="stats-grid">
        <div className="stat-item">
          <span className="stat-label">Cached Events</span>
          <span className="stat-value font-mono">{status?.cached_events ?? "—"}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Local Reports</span>
          <span className="stat-value font-mono text-cyan">{status?.local_events_added ?? "0"}</span>
        </div>
        <div className="stat-item full-width">
          <span className="stat-label">Model Pipeline</span>
          <span className="stat-value text-sm font-mono">{status?.model ?? "omori-style-v1"}</span>
        </div>
        {status?.last_catalog_update && (
          <div className="stat-item full-width">
            <span className="stat-label">Last Catalog Update</span>
            <span className="stat-subtext font-mono">
              {new Date(status.last_catalog_update).toLocaleString()}
            </span>
          </div>
        )}
      </div>

      <div className="card-footer">
        <button
          type="button"
          className="btn-glass btn-sync"
          onClick={handleRefresh}
          disabled={isRefreshing}
          id="refresh-catalog-btn"
        >
          {isRefreshing ? (
            <>
              <span className="btn-spinner" /> Syncing with USGS...
            </>
          ) : (
            <>
              <span className="btn-icon">🔄</span> Sync USGS Catalog
            </>
          )}
        </button>
        {feedback && <div className="feedback-banner">{feedback}</div>}
      </div>
    </div>
  );
}
