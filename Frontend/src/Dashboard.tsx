import { useState, useEffect, useCallback, useRef } from "react";
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

export default function Dashboard({initialPlace }: DashboardProps) {
  // Navigation & UI state
  const [activeTab, setActiveTab] = useState<ActiveTab>("events");
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
  const [isSitRepOpen, setIsSitRepOpen] = useState<boolean>(false);
  const [activeScenarioId, setActiveScenarioId] = useState<string>("live_usgs");

  // Data states
  const [status, setStatus] = useState<SystemStatusType | null>(null);
  const [events, setEvents] = useState<EarthquakeEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EarthquakeEvent | null>(null);
  const [riskData, setRiskData] = useState<RiskResponse | null>(null);

  // Filter & coordinate states
  const [timeWindowHours, setTimeWindowHours] = useState<number>(72);
  const [minMagnitude, setMinMagnitude] = useState<number>(3.0);
  const [riskTimeWindow, setRiskTimeWindow] = useState<"24h" | "72h" | "7d">("24h");
  const [inspectedCoords, setInspectedCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [activeLocationLabel, setActiveLocationLabel] = useState<string>("Global USGS Real-Time Feed");

  // Loading states
  const [isEventsLoading, setIsEventsLoading] = useState<boolean>(false);
  const [isRiskLoading, setIsRiskLoading] = useState<boolean>(false);
  const scenarioIdRef = useRef(activeScenarioId);
  const eventsRequestRef = useRef(0);

  // Fetch system status
  const loadStatus = useCallback(async () => {
    try {
      const data = await getSystemStatus();
      setStatus(data);
    } catch (err) {
      console.warn("Status fetch error:", err);
    }
  }, []);

  // Fetch recent events. A simulation sequence stays on screen until Live USGS is chosen again.
  const loadEvents = useCallback(async () => {
    if (scenarioIdRef.current !== "live_usgs") return;
    const ticket = ++eventsRequestRef.current;
    setIsEventsLoading(true);
    try {
      const res = await getRecentEvents({
        hours: timeWindowHours,
        min_magnitude: minMagnitude,
        limit: 500,
      });
      if (ticket !== eventsRequestRef.current || scenarioIdRef.current !== "live_usgs") return;
      setEvents(res.events || []);
    } catch (err) {
      console.error("Events fetch error:", err);
    } finally {
      if (ticket === eventsRequestRef.current) setIsEventsLoading(false);
    }
  }, [timeWindowHours, minMagnitude]);

  // Recalculate risk for currently inspected coordinates
  const loadRisk = useCallback(async (coords?: { lat: number; lon: number }) => {
    const target = coords || inspectedCoords;
    if (!target) return;
    setIsRiskLoading(true);
    try {
      const res = await calculateRisk({
        lat: target.lat,
        lon: target.lon,
        time_window: riskTimeWindow,
        min_magnitude: 4.0,
      });
      setRiskData(res);
    } catch (err) {
      console.error("Risk calc error:", err);
    } finally {
      setIsRiskLoading(false);
    }
  }, [inspectedCoords, riskTimeWindow]);

  // Handle Scenario switching
  const handleSelectScenario = useCallback((scenarioId: string) => {
    scenarioIdRef.current = scenarioId;
    eventsRequestRef.current += 1;
    setActiveScenarioId(scenarioId);
    const scenario = PRESET_SCENARIOS.find((s) => s.id === scenarioId);
    if (!scenario) return;

    if (scenario.id === "live_usgs") {
      loadEvents();
      loadStatus();
      setInspectedCoords(null);
      setActiveLocationLabel("Global USGS Real-Time Feed");
      setSelectedEvent(null);
      setRiskData(null);
      return;
    }

    if (scenario.events && scenario.events.length > 0) {
      setEvents(scenario.events);
      const mainEvent = scenario.events.reduce((best, item) =>
        item.magnitude > best.magnitude ? item : best
      );
      setSelectedEvent(mainEvent);
      setInspectedCoords(scenario.center);
      setActiveLocationLabel(scenario.name);
      setActiveTab("events");
      setIsSidebarOpen(true);
      setIsEventsLoading(false);
      loadRisk({ lat: mainEvent.lat, lon: mainEvent.lon });
    }
  }, [loadEvents, loadStatus, loadRisk]);

  // Initial load
  useEffect(() => {
    loadStatus();
    loadEvents();
  }, [loadStatus, loadEvents]);

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


          {maxMagnitude > 0 && (
            <div className="btn-sitrep-header">
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
          {/* <button
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
          </button> */}

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

          {/* <button
            type="button"
            className={`nav-tab-btn ${activeTab === "status" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("status");
              setIsSidebarOpen(true);
            }}
          >
            <span className="nav-icon">⚙️</span>
            <span className="nav-text">Status</span>
          </button> */}
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
                  setTimeWindow={setRiskTimeWindow}
                  onRecalculate={() => loadRisk()}
                  onOpenSitRep={() => setIsSitRepOpen(true)}
                  selectedMainshock={selectedEvent}
                />
              )}

              {activeTab === "report" && (
                <ReportEventPanel
                  currentMapCenter={inspectedCoords || { lat: 20.0, lon: 0.0 }}
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
