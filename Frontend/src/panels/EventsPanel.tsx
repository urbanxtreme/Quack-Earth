import { useState, useMemo } from "react";
import type { EarthquakeEvent } from "../api";

interface EventsPanelProps {
  events: EarthquakeEvent[];
  selectedEventId: string | null;
  onSelectEvent: (event: EarthquakeEvent) => void;
  isLoading: boolean;
  timeWindowHours: number;
  setTimeWindowHours: (hours: number) => void;
  minMagnitude: number;
  setMinMagnitude: (mag: number) => void;
}

export default function EventsPanel({
  events,
  selectedEventId,
  onSelectEvent,
  isLoading,
  timeWindowHours,
  setTimeWindowHours,
  minMagnitude,
  setMinMagnitude,
}: EventsPanelProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const filteredEvents = useMemo(() => {
    return events.filter((e) => {
      const matchMag = e.magnitude >= minMagnitude;
      const matchSearch =
        searchQuery.trim() === "" ||
        (e.place && e.place.toLowerCase().includes(searchQuery.toLowerCase())) ||
        e.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        e.source?.toLowerCase().includes(searchQuery.toLowerCase());
      return matchMag && matchSearch;
    });
  }, [events, minMagnitude, searchQuery]);

  const getMagColorClass = (mag: number) => {
    if (mag >= 6.5) return "mag-critical";
    if (mag >= 5.0) return "mag-high";
    if (mag >= 4.0) return "mag-medium";
    return "mag-low";
  };

  const formatRelativeTime = (isoString: string) => {
    try {
      const diffMs = Date.now() - new Date(isoString).getTime();
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
      if (diffHours < 1) {
        const diffMins = Math.max(1, Math.floor(diffMs / (1000 * 60)));
        return `${diffMins}m ago`;
      }
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      return `${diffDays}d ago`;
    } catch {
      return isoString;
    }
  };

  return (
    <div className="glass-panel events-panel">
      <div className="panel-header">
        <div className="panel-title-row">
          <span className="panel-icon">⚡</span>
          <h2 className="panel-title">Seismic Events</h2>
          <span className="count-pill">{filteredEvents.length}</span>
        </div>
        <p className="panel-subtitle">Catalog of cached USGS & edge sensor detections</p>
      </div>

      {/* Filter Controls */}
      <div className="filter-controls">
        <div className="time-filter-group">
          <span className="control-label">Time Window</span>
          <div className="button-toggle-row">
            {[24, 48, 72, 168].map((hours) => (
              <button
                key={hours}
                type="button"
                className={`toggle-chip ${timeWindowHours === hours ? "active" : ""}`}
                onClick={() => setTimeWindowHours(hours)}
              >
                {hours === 168 ? "7d" : `${hours}h`}
              </button>
            ))}
          </div>
        </div>

        <div className="magnitude-filter-group">
          <div className="mag-slider-header">
            <span className="control-label">Min Magnitude</span>
            <span className="mag-value-display font-mono">M {minMagnitude.toFixed(1)}+</span>
          </div>
          <input
            type="range"
            min="2.0"
            max="7.0"
            step="0.5"
            value={minMagnitude}
            onChange={(e) => setMinMagnitude(parseFloat(e.target.value))}
            className="styled-range"
            id="magnitude-filter-slider"
          />
          <div className="range-ticks">
            <span>2.0</span>
            <span>3.5</span>
            <span>5.0</span>
            <span>7.0</span>
          </div>
        </div>

        <div className="events-search-bar">
          <span className="search-symbol">🔎</span>
          <input
            type="text"
            className="glass-input-sm"
            placeholder="Filter by location, ID, or source..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="clear-btn-sm" onClick={() => setSearchQuery("")}>
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Events List */}
      <div className="events-list-container">
        {isLoading ? (
          <div className="panel-loader">
            <div className="pulse-loader" />
            <span>Fetching seismic records...</span>
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">🌐</span>
            <p className="empty-text">No events match the selected criteria.</p>
            <button
              className="btn-glass btn-sm"
              onClick={() => {
                setMinMagnitude(2.0);
                setTimeWindowHours(168);
                setSearchQuery("");
              }}
            >
              Reset Filters
            </button>
          </div>
        ) : (
          <ul className="events-list">
            {filteredEvents.map((event) => {
              const isSelected = selectedEventId === event.id;
              const magClass = getMagColorClass(event.magnitude);

              return (
                <li
                  key={event.id}
                  className={`event-card ${isSelected ? "selected" : ""} ${event.source === "user_report" ? "local-event" : ""}`}
                  onClick={() => onSelectEvent(event)}
                  tabIndex={0}
                  role="button"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      onSelectEvent(event);
                    }
                  }}
                >
                  <div className={`mag-badge ${magClass}`}>
                    <span className="mag-unit">M</span>
                    <span className="mag-num font-mono">{event.magnitude.toFixed(1)}</span>
                  </div>

                  <div className="event-info">
                    <div className="event-title-line">
                      <span className="event-place">
                        {event.place || `Lat: ${event.lat.toFixed(2)}°, Lon: ${event.lon.toFixed(2)}°`}
                      </span>
                    </div>

                    <div className="event-meta-line font-mono">
                      <span className="meta-time">{formatRelativeTime(event.time)}</span>
                      {event.depth_km !== undefined && (
                        <span className="meta-depth">Depth: {event.depth_km} km</span>
                      )}
                      <span className={`source-pill ${event.source === "user_report" ? "pill-user" : "pill-usgs"}`}>
                        {event.source === "user_report" ? "Local" : "USGS"}
                      </span>
                    </div>
                  </div>

                  <div className="event-action-arrow">→</div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
