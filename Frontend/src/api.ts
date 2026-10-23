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
}

export interface RiskResponse {
  time_window: string;
  min_magnitude: number;
  center?: { lat: number; lon: number };
  baseline_rate: number;
  zones: RiskZone[];
  generated_at: string;
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
const API_BASE = '/api';

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
  time_window?: '24h' | '7d';
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
