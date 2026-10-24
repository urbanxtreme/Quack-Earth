/**
 * Quack Earth - Seismic Risk Anticipation API Client
 * Real-time API Client connecting to USGS via the Backend engine
 */

export interface SystemStatus {
  status: 'ok' | 'error' | string;
  mode: 'online' | 'offline' | string;
  cached_events: number;
  local_events_added: number;
  last_catalog_update: string | null;
  model: string;
}

export interface RiskZone {
  lat: number;
  lon: number;
  risk_score: number;
  relative_to_baseline: number;
  expected_events: number;
  risk_level?: string;
  probability_24h?: number;
  probability_7d?: number;
  public_zone?: string;
}

export interface SectorGuidance {
  lat: number;
  lon: number;
  probability_24h: number;
  public_zone: string;
  probability_m5_24h?: number;
  probability_m6_24h?: number;
  direction: string;
  distance_km: number;
  place: string;
  action: string;
  excavation: string;
  cells?: number;
}

export interface GuidanceData {
  as_of: string;
  peak: {
    lat: number;
    lon: number;
    probability_24h: number;
    public_zone: string;
    probability_m5_24h?: number;
    probability_m6_24h?: number;
  };
  limit: string;
  sectors: SectorGuidance[];
}

export interface RiskResponse {
  time_window: string;
  min_magnitude: number;
  center?: { lat: number; lon: number };
  baseline_rate: number;
  zones: RiskZone[];
  generated_at: string;
  verdict?: string;
  guidance?: GuidanceData;
  public_zone?: string;
  excavation_action?: string;
}

export interface EventCorroboration {
  status: 'usgs_verified' | 'sensor_corroborated' | 'crowd_report' | string;
  label: string;
  confidence: number;
  station_count?: number;
}

export interface EarthquakeEvent {
  id: string;
  time: string;
  lat: number;
  lon: number;
  magnitude: number;
  depth_km?: number;
  source?: string;
  place?: string;
  note?: string;
  corroboration?: EventCorroboration;
}

export interface ScenarioItem {
  id: string;
  name: string;
  short_name: string;
  tag: string;
  tag_color: string;
  center: { lat: number; lon: number };
  zoom: number;
  description: string;
  incident_date: string;
  peak_magnitude: number;
  event_count?: number;
  events?: EarthquakeEvent[];
}

export interface ScenariosResponse {
  count: number;
  scenarios: ScenarioItem[];
}

export interface EventsResponse {
  count: number;
  events: EarthquakeEvent[];
}

export interface LocalEventPayload {
  lat: number;
  lon: number;
  magnitude: number;
  time?: string;
  source?: string;
  note?: string;
}

export interface LocalEventResponse {
  status: string;
  event_id: string;
  message: string;
  nearby_risk_updated: boolean;
}

export interface RefreshCatalogResponse {
  status: string;
  events_fetched?: number;
  last_catalog_update?: string;
  message?: string;
}

export interface RiskGridPoint {
  lat: number;
  lon: number;
  risk_score: number;
  risk_level?: string;
  relative_risk?: number;
}

export interface RiskGridResponse {
  time_window: string;
  grid: RiskGridPoint[];
}

// Base endpoint configuration
const API_BASE = 'https://quack-earth.onrender.com/api';

/**
 * Fetch System Status from Backend
 */
export async function getSystemStatus(): Promise<SystemStatus> {
  const res = await fetch(`${API_BASE}/status`, { signal: AbortSignal.timeout(5000) });
  if (!res.ok) {
    throw new Error(`Status request failed with HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Calculate short-term risk scores via Backend engine
 */
export async function calculateRisk(params: {
  lat?: number;
  lon?: number;
  radius_km?: number;
  time_window?: '24h' | '72h' | '7d';
  min_magnitude?: number;
}): Promise<RiskResponse> {
  const query = new URLSearchParams();
  if (params.lat !== undefined) query.set("lat", params.lat.toString());
  if (params.lon !== undefined) query.set("lon", params.lon.toString());
  if (params.radius_km !== undefined) query.set("radius_km", params.radius_km.toString());
  if (params.time_window) query.set("time_window", params.time_window);
  if (params.min_magnitude !== undefined) query.set("min_magnitude", params.min_magnitude.toString());

  const res = await fetch(`${API_BASE}/risk?${query.toString()}`, { signal: AbortSignal.timeout(8000) });
  if (!res.ok) {
    throw new Error(`Risk calculation failed with HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Retrieve recent earthquakes directly from USGS catalog
 */
export async function getRecentEvents(params?: {
  hours?: number;
  min_magnitude?: number;
  limit?: number;
}): Promise<EventsResponse> {
  const query = new URLSearchParams();
  if (params?.hours) query.set("hours", params.hours.toString());
  if (params?.min_magnitude) query.set("min_magnitude", params.min_magnitude.toString());
  if (params?.limit) query.set("limit", params.limit.toString());

  const res = await fetch(`${API_BASE}/events?${query.toString()}`, { signal: AbortSignal.timeout(10000) });
  if (!res.ok) {
    throw new Error(`Events fetch failed with HTTP ${res.status}`);
  }
  const data = await res.json();
  return {
    count: data.count ?? data.events?.length ?? 0,
    events: Array.isArray(data.events) ? data.events : [],
  };
}

/**
 * Submit a local user report / sensor event
 */
export async function submitLocalEvent(payload: LocalEventPayload): Promise<LocalEventResponse> {
  const res = await fetch(`${API_BASE}/local-event`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(5000),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.message || errorData.error || `Report submission failed (${res.status})`);
  }
  return await res.json();
}

/**
 * Trigger live USGS Catalog Sync
 */
export async function refreshCatalog(options?: { min_magnitude?: number; days_back?: number }): Promise<RefreshCatalogResponse> {
  const res = await fetch(`${API_BASE}/refresh-catalog`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options || {}),
    signal: AbortSignal.timeout(20000),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.message || errorData.error || `Catalog sync failed with HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Fetch Risk Grid for Heatmaps from backend
 */
export async function getRiskGrid(params: {
  min_lat: number;
  max_lat: number;
  min_lon: number;
  max_lon: number;
  resolution?: number;
  time_window?: '24h' | '7d';
  min_magnitude?: number;
}): Promise<RiskGridResponse> {
  const query = new URLSearchParams({
    min_lat: params.min_lat.toString(),
    max_lat: params.max_lat.toString(),
    min_lon: params.min_lon.toString(),
    max_lon: params.max_lon.toString(),
    resolution: (params.resolution || 0.2).toString(),
    time_window: params.time_window || "24h"
  });
  if (params.min_magnitude !== undefined) {
    query.set("min_magnitude", params.min_magnitude.toString());
  }

  const res = await fetch(`${API_BASE}/risk/grid?${query.toString()}`, { signal: AbortSignal.timeout(10000) });
  if (!res.ok) {
    throw new Error(`Risk grid fetch failed with HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Fetch list of emergency scenario presets
 */
export async function getScenarios(): Promise<ScenariosResponse> {
  const res = await fetch(`${API_BASE}/scenarios`, { signal: AbortSignal.timeout(6000) });
  if (!res.ok) {
    throw new Error(`Scenarios fetch failed with HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Fetch full scenario details including timeline events
 */
export async function getScenarioDetails(scenarioId: string): Promise<ScenarioItem> {
  const res = await fetch(`${API_BASE}/scenarios/${encodeURIComponent(scenarioId)}`, { signal: AbortSignal.timeout(6000) });
  if (!res.ok) {
    throw new Error(`Scenario details fetch failed with HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Fetch civil-defense situation verdict
 */
export async function getRiskVerdict(params: {
  lat?: number;
  lon?: number;
  min_lat?: number;
  max_lat?: number;
  min_lon?: number;
  max_lon?: number;
  time_window?: '24h' | '7d';
  min_magnitude?: number;
}): Promise<{
  verdict: string;
  guidance: GuidanceData;
  public_zone: string;
  excavation_action: string;
  probability_24h?: number;
  as_of?: string;
}> {
  const query = new URLSearchParams();
  if (params.lat !== undefined) query.set("lat", params.lat.toString());
  if (params.lon !== undefined) query.set("lon", params.lon.toString());
  if (params.min_lat !== undefined) query.set("min_lat", params.min_lat.toString());
  if (params.max_lat !== undefined) query.set("max_lat", params.max_lat.toString());
  if (params.min_lon !== undefined) query.set("min_lon", params.min_lon.toString());
  if (params.max_lon !== undefined) query.set("max_lon", params.max_lon.toString());
  if (params.time_window) query.set("time_window", params.time_window);
  if (params.min_magnitude !== undefined) query.set("min_magnitude", params.min_magnitude.toString());

  const res = await fetch(`${API_BASE}/risk/verdict?${query.toString()}`, { signal: AbortSignal.timeout(8000) });
  if (!res.ok) {
    throw new Error(`Risk verdict fetch failed with HTTP ${res.status}`);
  }
  return await res.json();
}

