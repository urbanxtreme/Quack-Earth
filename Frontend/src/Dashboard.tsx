import { useState, useEffect, useCallback } from "react";
import MapViewer from "./MapViewer";
import EventsPanel from "./panels/EventsPanel";
import RiskPanel from "./panels/RiskPanel";
import ReportEventPanel from "./panels/ReportEventPanel";
import SystemStatus from "./panels/SystemStatus";
import SitRepModal from "./SitRepModal";
import { PRESET_SCENARIOS } from "./scenarios";
import {
  getSystemStatus,
  getRecentEvents,
  calculateRisk,
  type SystemStatus as SystemStatusType,
  type EarthquakeEvent,
  type RiskResponse,
} from "./api";

interface DashboardProps {
  onBackToLanding?: () => void;
  initialPlace?: string;
}

export type ActiveTab = "map" | "events" | "risk" | "report" | "status";

export default function Dashboard({ onBackToLanding, initialPlace }: DashboardProps) {
  // Navigation & UI state
  const [activeTab, setActiveTab] = useState<ActiveTab>("events");
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
  const [isSitRepOpen, setIsSitRepOpen] = useState<boolean>(false);
  const [activeScenarioId, setActiveScenarioId] = useState<string>("live_usgs");

  // Data states
  const [status, setStatus] = useState<SystemStatusType | null>(null);
  const [events, setEvents] = useState<EarthquakeEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EarthquakeEvent | null>(null);
  const [selectedMainshock, setSelectedMainshock] = useState<EarthquakeEvent | null>(null);
  const [riskData, setRiskData] = useState<RiskResponse | null>(null);

  // Filter & coordinate states
  const [timeWindowHours, setTimeWindowHours] = useState<number>(24);
  const [minMagnitude, setMinMagnitude] = useState<number>(3.0);
  const [riskTimeWindow, setRiskTimeWindow] = useState<"24h" | "72h" | "7d">("24h");
  const [inspectedCoords, setInspectedCoords] = useState<{ lat: number; lon: number } | null>({
    lat: 35.6762,
    lon: 139.6503,
  });
  const [activeLocationLabel, setActiveLocationLabel] = useState<string>("Tokyo, Japan");

  // Loading states
  const [isEventsLoading, setIsEventsLoading] = useState<boolean>(false);
  const [isRiskLoading, setIsRiskLoading] = useState<boolean>(false);

  // Fetch system status
  const loadStatus = useCallback(async () => {
    try {
      const data = await getSystemStatus();
      setStatus(data);
    } catch (err) {
      console.warn("Status fetch error:", err);
    }
  }, []);

  // Fetch recent events
  const loadEvents = useCallback(async () => {
    setIsEventsLoading(true);
    try {
      const res = await getRecentEvents({
        hours: timeWindowHours,
        min_magnitude: minMagnitude,
        limit: 100,
      });
      setEvents(res.events || []);
    } catch (err) {
      console.error("Events fetch error:", err);
    } finally {
      setIsEventsLoading(false);
    }
  }, [timeWindowHours, minMagnitude]);

  // Recalculate risk for currently inspected coordinates
  const loadRisk = useCallback(async (coords?: { lat: number; lon: number }, mainshock?: EarthquakeEvent | null) => {
    const target = coords || inspectedCoords || { lat: 35.6762, lon: 139.6503 };
    const ms = mainshock !== undefined ? mainshock : selectedMainshock;
    setIsRiskLoading(true);
    try {
      const res = await calculateRisk({
        lat: target.lat,
        lon: target.lon,
        time_window: riskTimeWindow,
        min_magnitude: 4.0,
        mainshock_id: ms?.id,
      });
      setRiskData(res);
    } catch (err) {
      console.error("Risk calc error:", err);
    } finally {
      setIsRiskLoading(false);
    }
  }, [inspectedCoords, riskTimeWindow, selectedMainshock]);

  // Handle Scenario switching
  const handleSelectScenario = useCallback((scenarioId: string) => {
    setActiveScenarioId(scenarioId);
    const scenario = PRESET_SCENARIOS.find((s) => s.id === scenarioId);
    if (!scenario) return;

    if (scenario.id === "live_usgs") {
      setSelectedMainshock(null);
      loadEvents();
      loadStatus();
      loadRisk({ lat: 35.6762, lon: 139.6503 }, null);
      setInspectedCoords({ lat: 35.6762, lon: 139.6503 });
      setActiveLocationLabel("Tokyo, Japan (USGS Global)");
      return;
    }

    if (scenario.events && scenario.events.length > 0) {
      setEvents(scenario.events);
      const mainEvent = scenario.events[0];
      setSelectedEvent(mainEvent);
      setSelectedMainshock(mainEvent);
      setInspectedCoords(scenario.center);
      setActiveLocationLabel(scenario.name);
      loadRisk(scenario.center, mainEvent);
    }
  }, [loadEvents, loadStatus, loadRisk]);

  // Initial load
  useEffect(() => {
    loadStatus();
    loadEvents();
    loadRisk();
  }, [loadStatus, loadEvents, loadRisk]);

  // Handle selecting an event from list
  const handleSelectEvent = (event: EarthquakeEvent) => {
    setSelectedEvent(event);
    setInspectedCoords({ lat: event.lat, lon: event.lon });
    setActiveLocationLabel(event.place || `M${event.magnitude} Event`);
    loadRisk({ lat: event.lat, lon: event.lon });
  };

  // Handle map click
  const handleMapClick = (coords: { lat: number; lon: number }) => {
    setInspectedCoords(coords);
    setActiveLocationLabel(`Custom Coordinates: ${coords.lat.toFixed(2)}°, ${coords.lon.toFixed(2)}°`);
    loadRisk(coords);
    if (activeTab === "map") {
      setActiveTab("risk");
    }
  };

  // Maximum magnitude in current catalog
  const maxMagnitude = events.reduce((max, e) => (e.magnitude > max ? e.magnitude : max), 0);

  return (
    <div className="dashboard-root">
      {/* Top Header Bar */}
      <header className="dashboard-header">
        <div className="header-brand-section">
          {onBackToLanding && (
            <button
              type="button"
              className="btn-glass-icon"
              onClick={onBackToLanding}
              title="Return to welcome screen"
            >
              ←
            </button>
          )}
          <div className="brand-title-group">
            <div className="brand-logo-icon">🌍</div>
            <div>
              <div className="brand-name-row">
                <h1 className="brand-name">QUACK EARTH</h1>
                <span className="version-tag">EDGE-V1</span>
              </div>
              <p className="brand-tagline">Seismic Hazard & Risk Anticipation Engine</p>
            </div>
          </div>
        </div>

        {/* Global Scenario Selector & SitRep Trigger */}
        <div className="header-scenario-selector">
          <span className="scenario-label font-mono">INCIDENT:</span>
          <select
            className="header-scenario-dropdown font-mono"
            value={activeScenarioId}
            onChange={(e) => handleSelectScenario(e.target.value)}
            title="Switch between live USGS feed and critical disaster simulation scenarios"
          >
            {PRESET_SCENARIOS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.short_name} ({s.tag})
              </option>
            ))}
          </select>
        </div>

        {/* Global Live Stat Badges */}
        <div className="header-metrics">
          <div className="metric-badge">
            <span className="metric-dot" />
            <span className="metric-label">Mode:</span>
            <span className="metric-value font-mono">
              {activeScenarioId !== "live_usgs"
                ? "SCENARIO REPLAY"
                : status?.mode === "online"
                ? "USGS ONLINE"
                : "OFFLINE EDGE"}
            </span>
          </div>

          <div className="metric-badge">
            <span className="metric-label">Active Events:</span>
            <span className="metric-value font-mono text-cyan">{events.length}</span>
          </div>

          {maxMagnitude > 0 && (
            <div className="metric-badge">
              <span className="metric-label">Peak:</span>
              <span className="metric-value font-mono text-orange">M {maxMagnitude.toFixed(1)}</span>
            </div>
          )}

          <button
            type="button"
            className="btn-sitrep-header"
            onClick={() => setIsSitRepOpen(true)}
            title="Generate and print an official Incident Situation Report"
          >
            📋 SitRep Briefing
          </button>
        </div>

        {/* Primary Navigation Tabs */}
        <nav className="header-nav-tabs">
          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "map" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("map");
              if (window.innerWidth <= 768) {
                setIsSidebarOpen(false);
              }
            }}
          >
            <span className="nav-icon">🗺️</span>
            <span className="nav-text">Map</span>
          </button>

          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "events" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("events");
              setIsSidebarOpen(true);
            }}
          >
            <span className="nav-icon">⚡</span>
            <span className="nav-text">Events</span>
            {events.length > 0 && <span className="tab-counter">{events.length}</span>}
          </button>

          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "risk" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("risk");
              setIsSidebarOpen(true);
            }}
          >
            <span className="nav-icon">📊</span>
            <span className="nav-text">
              <span className="nav-text-full">Risk Anticipation</span>
              <span className="nav-text-short">Risk</span>
            </span>
          </button>

          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "report" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("report");
              setIsSidebarOpen(true);
            }}
          >
            <span className="nav-icon">📝</span>
            <span className="nav-text">Report</span>
          </button>

          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "status" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("status");
              setIsSidebarOpen(true);
            }}
          >
            <span className="nav-icon">⚙️</span>
            <span className="nav-text">Status</span>
          </button>
        </nav>

        {/* Sidebar Toggle */}
        <button
          type="button"
          className={`sidebar-toggle-btn ${isSidebarOpen ? "expanded" : "collapsed"}`}
          onClick={() => setIsSidebarOpen((prev) => !prev)}
          title={isSidebarOpen ? "Collapse Panel" : "Expand Panel"}
        >
          <span className="sidebar-toggle-text-full">{isSidebarOpen ? "Hide Panel ❯" : "❮ Show Panel"}</span>
          <span className="sidebar-toggle-text-short">{isSidebarOpen ? "✕" : "▤"}</span>
        </button>
      </header>

      {/* Main Content Workspace */}
      <div className="dashboard-body">
        {/* Map Container */}
        <div className={`dashboard-map-area ${!isSidebarOpen ? "full-width" : ""}`}>
          <MapViewer
            initialPlace={initialPlace}
            events={events}
            selectedEvent={selectedEvent}
            onSelectEvent={(ev) => {
              handleSelectEvent(ev);
              setActiveTab("events");
              setIsSidebarOpen(true);
            }}
            onMapClick={handleMapClick}
            targetCoords={inspectedCoords}
            activeScenarioId={activeScenarioId}
            onSelectScenario={handleSelectScenario}
            selectedMainshock={selectedMainshock}
            onSelectMainshock={setSelectedMainshock}
            forecastWindow={riskTimeWindow}
            onChangeForecastWindow={(w) => {
              setRiskTimeWindow(w);
              const hrs = w === "24h" ? 24 : w === "72h" ? 72 : 168;
              setTimeWindowHours(hrs);
            }}
            minMagnitude={minMagnitude}
            onChangeMinMagnitude={setMinMagnitude}
            isOffline={status?.mode === "offline"}
            onSyncSuccess={() => {
              loadEvents();
              loadStatus();
              loadRisk();
            }}
          />
        </div>

        {/* Right Glassmorphism Sidebar Panel */}
        {isSidebarOpen && (
          <aside className="dashboard-sidebar-panel">
            {/* Mobile Sheet Handle & Header */}
            <div className="mobile-drawer-header">
              <div className="drawer-drag-pill" />
              <button
                type="button"
                className="drawer-close-btn"
                onClick={() => setIsSidebarOpen(false)}
                title="Close drawer"
              >
                ✕ Close
              </button>
            </div>
            <div className="sidebar-tab-content">
              {activeTab === "events" && (
                <EventsPanel
                  events={events}
                  selectedEventId={selectedEvent?.id || null}
                  onSelectEvent={handleSelectEvent}
                  isLoading={isEventsLoading}
                  timeWindowHours={timeWindowHours}
                  setTimeWindowHours={setTimeWindowHours}
                  minMagnitude={minMagnitude}
                  setMinMagnitude={setMinMagnitude}
                />
              )}

              {activeTab === "risk" && (
                <RiskPanel
                  riskData={riskData}
                  isLoading={isRiskLoading}
                  activeLocationName={activeLocationLabel}
                  selectedCoordinates={inspectedCoords}
                  timeWindow={riskTimeWindow}
                  setTimeWindow={(tw) => {
                    setRiskTimeWindow(tw);
                    const hrs = tw === "24h" ? 24 : tw === "72h" ? 72 : 168;
                    setTimeWindowHours(hrs);
                  }}
                  onRecalculate={() => loadRisk()}
                  onOpenSitRep={() => setIsSitRepOpen(true)}
                  selectedMainshock={selectedMainshock}
                />
              )}

              {activeTab === "report" && (
                <ReportEventPanel
                  currentMapCenter={inspectedCoords || { lat: 35.6762, lon: 139.6503 }}
                  onEventSubmitted={() => {
                    loadEvents();
                    loadStatus();
                    loadRisk();
                    setActiveTab("events");
                  }}
                />
              )}

              {activeTab === "status" && (
                <SystemStatus
                  status={status}
                  onRefreshSuccess={() => {
                    loadStatus();
                    loadEvents();
                  }}
                />
              )}

              {activeTab === "map" && (
                <div className="glass-panel map-summary-panel">
                  <div className="panel-header">
                    <span className="panel-icon">🗺️</span>
                    <h2 className="panel-title">Map Controller</h2>
                  </div>
                  <p className="panel-subtitle">Interactive Protomaps PMTiles Vector Basemap</p>
                  <div className="instruction-card">
                    <h4>💡 Quick Actions</h4>
                    <ul>
                      <li>Select any disaster scenario from the top dropdown to review incident replays.</li>
                      <li>Use the 72-Hour Timeline Scrubber at the bottom of the map to watch aftershocks spawn.</li>
                      <li>Click anywhere on the globe to inspect coordinates and evaluate short-term seismic hazard.</li>
                      <li>Click "SitRep Briefing" to print an official Civil Protection Directive.</li>
                    </ul>
                  </div>
                  <div className="panel-actions">
                    <button
                      type="button"
                      className="btn-primary-glass full-width"
                      onClick={() => setActiveTab("risk")}
                    >
                      Inspect Hazard for Current Target →
                    </button>
                  </div>
                </div>
              )}
            </div>
          </aside>
        )}
      </div>

      {/* Emergency SitRep Modal */}
      <SitRepModal
        isOpen={isSitRepOpen}
        onClose={() => setIsSitRepOpen(false)}
        riskData={riskData}
        locationName={activeLocationLabel}
        coordinates={inspectedCoords}
        events={events}
      />
    </div>
  );
}
