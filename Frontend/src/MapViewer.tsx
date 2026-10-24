import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import * as pmtiles from "pmtiles";
import { layers, namedFlavor } from "@protomaps/basemaps";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { FeatureCollection, Point, LineString } from "geojson";
import {
  getFaults,
  getEventSequence,
  type EarthquakeEvent,
  type SequenceDetailsResponse,
} from "./api";
import { FALLBACK_FAULTS_GEOJSON } from "./data/faultsData";

// Configure MapLibre Web Worker for Vite
maplibregl.setWorkerUrl(maplibreWorkerUrl);

export interface MapViewerProps {
  onBack?: () => void;
  initialPlace?: string;
  events?: EarthquakeEvent[];
  selectedEvent?: EarthquakeEvent | null;
  onSelectEvent?: (event: EarthquakeEvent) => void;
  onMapClick?: (coords: { lat: number; lon: number }) => void;
  targetCoords?: { lat: number; lon: number; label?: string } | null;
  onSyncSuccess?: () => void;
  activeScenarioId?: string;
  onSelectScenario?: (scenarioId: string) => void;
  selectedMainshock?: EarthquakeEvent | null;
  onSelectMainshock?: (event: EarthquakeEvent | null) => void;
  forecastWindow?: "24h" | "72h" | "7d";
  onChangeForecastWindow?: (window: "24h" | "72h" | "7d") => void;
  minMagnitude?: number;
  onChangeMinMagnitude?: (mag: number) => void;
  isOffline?: boolean;
}

interface GeocodedLocation {
  name: string;
  lat: number;
  lon: number;
}

// Proxied through Vite dev server to guarantee 100% CORS & HTTP Range support on any local port
const getPmtilesUrl = () => {
  if (typeof window !== "undefined") {
    return `${window.location.origin}/pmtiles-proxy/v4.pmtiles`;
  }
  return "https://latest.protomaps.com/v4.pmtiles";
};

// Geocode location with proxy, direct API, and predefined dictionary fallback
async function geocodePlace(query: string): Promise<GeocodedLocation | null> {
  const trimmed = query.trim();
  if (!trimmed) return null;

  try {
    const res = await fetch(`/nominatim-proxy/search?q=${encodeURIComponent(trimmed)}&format=json&limit=1`);
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        const item = data[0];
        const displayName = item.display_name.split(",").slice(0, 3).join(",");
        return {
          name: displayName,
          lat: parseFloat(item.lat),
          lon: parseFloat(item.lon),
        };
      }
    }
  } catch {
    // Fallback
  }

  try {
    const res = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(trimmed)}&format=json&limit=1`);
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        const item = data[0];
        const displayName = item.display_name.split(",").slice(0, 3).join(",");
        return {
          name: displayName,
          lat: parseFloat(item.lat),
          lon: parseFloat(item.lon),
        };
      }
    }
  } catch {
    // Fallback
  }

  const normalized = trimmed.toLowerCase();
  const presets: Record<string, GeocodedLocation> = {
    kochi: { name: "Kochi, Kerala, India", lat: 9.9312, lon: 76.2673 },
    kerala: { name: "Kerala, India", lat: 10.8505, lon: 76.2711 },
    tokyo: { name: "Tokyo, Japan", lat: 35.6762, lon: 139.6503 },
    japan: { name: "Japan", lat: 36.2048, lon: 138.2529 },
    "san francisco": { name: "San Francisco, California, USA", lat: 37.7749, lon: -122.4194 },
    california: { name: "California, USA", lat: 36.7783, lon: -119.4179 },
    "los angeles": { name: "Los Angeles, California, USA", lat: 34.0522, lon: -118.2437 },
    chile: { name: "Chile", lat: -35.6751, lon: -71.543 },
    turkey: { name: "Kahramanmaraş, Turkey", lat: 37.175, lon: 37.025 },
    istanbul: { name: "Istanbul, Turkey", lat: 41.0082, lon: 28.9784 },
    nepal: { name: "Nepal", lat: 28.3949, lon: 84.124 },
    indonesia: { name: "Indonesia", lat: -0.7893, lon: 113.9213 },
    iceland: { name: "Iceland", lat: 64.9631, lon: -19.0208 },
    "new delhi": { name: "New Delhi, Delhi, India", lat: 28.6139, lon: 77.209 },
  };

  for (const [key, val] of Object.entries(presets)) {
    if (normalized.includes(key) || key.includes(normalized)) {
      return val;
    }
  }

  return null;
}

// Great circle distance in km
function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const rLat1 = (lat1 * Math.PI) / 180;
  const rLon1 = (lon1 * Math.PI) / 180;
  const rLat2 = (lat2 * Math.PI) / 180;
  const rLon2 = (lon2 * Math.PI) / 180;
  const dlat = rLat2 - rLat1;
  const dlon = rLon2 - rLon1;
  const a =
    Math.sin(dlat / 2) ** 2 +
    Math.cos(rLat1) * Math.cos(rLat2) * Math.sin(dlon / 2) ** 2;
  return 6371.0088 * 2 * Math.asin(Math.sqrt(Math.min(1.0, Math.max(0.0, a))));
}

// Helper to generate polygon circle coordinates for rupture zone buffer
function buildCircleGeoJSON(centerLon: number, centerLat: number, radiusKm: number, points: number = 48): FeatureCollection {
  const coords: [number, number][] = [];
  const kmPerDegLat = 111.0;
  const kmPerDegLon = 111.0 * Math.cos((centerLat * Math.PI) / 180.0);
  for (let i = 0; i <= points; i++) {
    const angle = (i * 2 * Math.PI) / points;
    const dx = radiusKm * Math.cos(angle);
    const dy = radiusKm * Math.sin(angle);
    const lon = centerLon + dx / kmPerDegLon;
    const lat = centerLat + dy / kmPerDegLat;
    coords.push([lon, lat]);
  }
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [coords],
        },
        properties: {
          radiusKm,
        },
      },
    ],
  };
}

export default function MapViewer({
  onBack,
  initialPlace,
  events = [],
  selectedEvent,
  onSelectEvent,
  onMapClick,
  targetCoords,
  onSyncSuccess,
  activeScenarioId = "live_usgs",
  onSelectScenario,
  selectedMainshock,
  onSelectMainshock,
  forecastWindow = "24h",
  onChangeForecastWindow,
  minMagnitude = 3.0,
  onChangeMinMagnitude,
  isOffline = false,
}: MapViewerProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const centerMarkerRef = useRef<maplibregl.Marker | null>(null);
  const clickMarkerRef = useRef<maplibregl.Marker | null>(null);
  const mainshockMarkerRef = useRef<maplibregl.Marker | null>(null);

  const [mapLoaded, setMapLoaded] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTheme, setActiveTheme] = useState<"light" | "dark" | "grayscale">("dark");

  const [searchInput, setSearchInput] = useState<string>(initialPlace || "");
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [searchFeedback, setSearchFeedback] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null);
  const [activeLocation, setActiveLocation] = useState<GeocodedLocation | null>(null);

  // Layer visibility toggles
  const [showEventsLayer, setShowEventsLayer] = useState<boolean>(true);
  const [showMainshockLayer, setShowMainshockLayer] = useState<boolean>(true);
  const [showAftershocksLayer, setShowAftershocksLayer] = useState<boolean>(true);
  const [showFaultsLayer, setShowFaultsLayer] = useState<boolean>(true);
  const [showForecastHeatmap, setShowForecastHeatmap] = useState<boolean>(true);
  const [isLegendExpanded, setIsLegendExpanded] = useState<boolean>(true);

  // Local state for forecast window and min magnitude if not controlled externally
  const [internalForecastWindow, setInternalForecastWindow] = useState<"24h" | "72h" | "7d">("24h");
  const [internalMinMagnitude, setInternalMinMagnitude] = useState<number>(3.0);
  const activeWindow = forecastWindow || internalForecastWindow;
  const activeMinMag = minMagnitude !== undefined ? minMagnitude : internalMinMagnitude;

  // Identified sequence aftershocks state
  const [sequenceDetails, setSequenceDetails] = useState<SequenceDetailsResponse | null>(null);
  const [riskGridFeatures, setRiskGridFeatures] = useState<FeatureCollection | null>(null);
  const [faultsData, setFaultsData] = useState<FeatureCollection<LineString>>(FALLBACK_FAULTS_GEOJSON);

  // 72-Hour / Sequence Timeline Scrubbing state
  const [timelinePercent, setTimelinePercent] = useState<number>(100);
  const [isPlayingTimeline, setIsPlayingTimeline] = useState<boolean>(false);

  const [viewportInfo, setViewportInfo] = useState<{ lng: string; lat: string; zoom: string }>({
    lng: "0.00",
    lat: "20.00",
    zoom: "2.5",
  });

  // Effective mainshock: prop if provided, else auto-detect largest event >= 5.0
  const effectiveMainshock = useMemo<EarthquakeEvent | null>(() => {
    if (selectedMainshock) return selectedMainshock;
    if (events.length === 0) return null;
    const sorted = [...events].sort((a, b) => b.magnitude - a.magnitude);
    return sorted[0].magnitude >= 5.0 ? sorted[0] : null;
  }, [selectedMainshock, events]);

  // Chronologically sorted events
  const sortedEvents = useMemo(() => {
    return [...events].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
  }, [events]);

  // Events filtered by scrubber position and minimum magnitude slider
  const displayedEvents = useMemo(() => {
    let filtered = sortedEvents.filter((e) => e.magnitude >= activeMinMag);
    if (timelinePercent >= 100 || filtered.length <= 1) {
      return filtered;
    }
    const tMin = new Date(filtered[0].time).getTime();
    const tMax = new Date(filtered[filtered.length - 1].time).getTime();
    if (tMax <= tMin) return filtered;
    const cutoff = tMin + (tMax - tMin) * (timelinePercent / 100);
    return filtered.filter((e) => new Date(e.time).getTime() <= cutoff);
  }, [sortedEvents, timelinePercent, activeMinMag]);

  // Identified aftershock events (events clustered near effective mainshock)
  const identifiedAftershocks = useMemo<EarthquakeEvent[]>(() => {
    if (!effectiveMainshock) return [];
    const msTime = new Date(effectiveMainshock.time).getTime();
    // Rupture length scaling L ~ 10^(0.5M - 1.8), search radius ~ 3.0 * L, min 35 km
    const rSearchKm = Math.max(35.0, Math.min(350.0, 3.0 * Math.max(5.0, 10 ** (0.5 * effectiveMainshock.magnitude - 1.8))));
    return displayedEvents.filter((e) => {
      if (e.id === effectiveMainshock.id) return false;
      const t = new Date(e.time).getTime();
      if (t < msTime) return false; // Not an aftershock
      const d = haversineKm(effectiveMainshock.lat, effectiveMainshock.lon, e.lat, e.lon);
      return d <= rSearchKm;
    });
  }, [effectiveMainshock, displayedEvents]);

  // Automated playback timer
  useEffect(() => {
    let timer: any = null;
    if (isPlayingTimeline) {
      timer = setInterval(() => {
        setTimelinePercent((prev) => {
          if (prev >= 100) {
            setIsPlayingTimeline(false);
            return 100;
          }
          return Math.min(100, prev + 2.5);
        });
      }, 150);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isPlayingTimeline]);

  // Fetch verified active tectonic faults
  useEffect(() => {
    let cancelled = false;
    getFaults()
      .then((data) => {
        if (!cancelled && data?.features?.length > 0) {
          setFaultsData(data);
        }
      })
      .catch((err) => {
        console.warn("Faults API fetch fallback to built-in cache:", err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Fetch sequence details when mainshock changes
  useEffect(() => {
    if (!effectiveMainshock) {
      setSequenceDetails(null);
      return;
    }
    let cancelled = false;
    getEventSequence(effectiveMainshock.id)
      .then((data) => {
        if (!cancelled) {
          setSequenceDetails(data);
        }
      })
      .catch((err) => {
        console.warn("Sequence analysis fallback:", err);
      });
    return () => {
      cancelled = true;
    };
  }, [effectiveMainshock]);

  // Fetch risk forecast grid GeoJSON for active mainshock and forecast window
  const loadForecastGrid = useCallback(async () => {
    const centerLat = effectiveMainshock ? effectiveMainshock.lat : 36.0;
    const centerLon = effectiveMainshock ? effectiveMainshock.lon : 36.0;
    const delta = 3.5;

    try {
      const res = await fetch(
        `/api/risk/grid?min_lat=${(centerLat - delta).toFixed(2)}&max_lat=${(centerLat + delta).toFixed(2)}&min_lon=${(centerLon - delta).toFixed(2)}&max_lon=${(centerLon + delta).toFixed(2)}&resolution=0.25&time_window=${activeWindow}&min_magnitude=${activeMinMag}${effectiveMainshock ? `&mainshock_id=${encodeURIComponent(effectiveMainshock.id)}` : ""}&format=geojson`
      );
      if (res.ok) {
        const geojson = await res.json();
        setRiskGridFeatures(geojson);
      }
    } catch (err) {
      console.warn("Forecast grid fetch fallback:", err);
    }
  }, [effectiveMainshock, activeWindow, activeMinMag]);

  useEffect(() => {
    loadForecastGrid();
  }, [loadForecastGrid]);

  const getStyleForTheme = (themeName: "light" | "dark" | "grayscale"): maplibregl.StyleSpecification => {
    const spriteVariant = themeName === "dark" ? "dark" : "light";
    const pmtilesUrl = getPmtilesUrl();
    return {
      version: 8,
      glyphs: "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf",
      sprite: `https://protomaps.github.io/basemaps-assets/sprites/v4/${spriteVariant}`,
      sources: {
        protomaps: {
          type: "vector",
          url: `pmtiles://${pmtilesUrl}`,
          attribution:
            '<a href="https://protomaps.com" target="_blank" rel="noreferrer">Protomaps</a> © <a href="https://openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a>',
        },
      },
      layers: layers("protomaps", namedFlavor(themeName), { lang: "en" }),
    };
  };

  // Convert EarthquakeEvent[] to GeoJSON FeatureCollection
  const buildEventsGeoJSON = useCallback((evList: EarthquakeEvent[]): FeatureCollection<Point> => {
    return {
      type: "FeatureCollection",
      features: evList.map((e) => ({
        type: "Feature",
        id: e.id,
        geometry: {
          type: "Point",
          coordinates: [e.lon, e.lat],
        },
        properties: {
          id: e.id,
          mag: e.magnitude,
          place: e.place || "Seismic Event",
          time: e.time,
          depth: e.depth_km ?? 10,
          source: e.source || "usgs",
        },
      })),
    };
  }, []);

  // Update or attach the Events circles layer on the map
  const updateEventsLayer = useCallback((evList: EarthquakeEvent[]) => {
    const map = mapRef.current;
    if (!map) return;

    const geojson = buildEventsGeoJSON(evList);
    const source = map.getSource("events-source") as maplibregl.GeoJSONSource | undefined;

    if (source) {
      source.setData(geojson);
    } else {
      map.addSource("events-source", {
        type: "geojson",
        data: geojson,
      });

      // Events outer glow
      map.addLayer({
        id: "events-glow",
        type: "circle",
        source: "events-source",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["get", "mag"],
            2.0, 5,
            4.0, 8,
            6.0, 12,
            7.5, 16,
          ],
          "circle-color": [
            "step",
            ["get", "mag"],
            "rgba(56, 189, 248, 0.35)",
            4.0, "rgba(250, 204, 21, 0.45)",
            5.5, "rgba(251, 146, 60, 0.55)",
            6.5, "rgba(239, 68, 68, 0.65)",
          ],
          "circle-blur": 0.3,
        },
      });

      // Events solid core marker
      map.addLayer({
        id: "events-circles",
        type: "circle",
        source: "events-source",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["get", "mag"],
            2.0, 4,
            4.0, 7,
            6.0, 12,
            7.5, 18,
          ],
          "circle-color": [
            "step",
            ["get", "mag"],
            "#38bdf8",
            4.0, "#facc15",
            5.5, "#fb923c",
            6.5, "#ef4444",
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 0.95,
        },
      });

      // Click event on earthquake marker
      map.on("click", "events-circles", (e) => {
        if (!e.features || e.features.length === 0) return;
        const feature = e.features[0];
        const props = feature.properties;
        const coords = (feature.geometry as Point).coordinates;

        const foundEvent = evList.find((ev) => ev.id === props.id);
        if (foundEvent && onSelectEvent) {
          onSelectEvent(foundEvent);
        }

        new maplibregl.Popup({ offset: 15 })
          .setLngLat([coords[0], coords[1]])
          .setHTML(
            `<div class="epicenter-popup">
              <h4>M ${props.mag} - ${props.place}</h4>
              <p><strong>Depth:</strong> ${props.depth} km</p>
              <p><strong>Time:</strong> ${new Date(props.time).toLocaleString()}</p>
              <span class="popup-tag">${props.source === "user_report" ? "Local Report" : "USGS ComCat"}</span>
            </div>`
          )
          .addTo(map);
      });

      map.on("mouseenter", "events-circles", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "events-circles", () => {
        map.getCanvas().style.cursor = "";
      });
    }
  }, [buildEventsGeoJSON, onSelectEvent]);

  // Update or attach the Tectonic Faults layer
  const updateFaultsLayer = useCallback((faultsGjson: FeatureCollection<LineString>) => {
    const map = mapRef.current;
    if (!map) return;

    const source = map.getSource("faults-source") as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(faultsGjson);
    } else {
      map.addSource("faults-source", {
        type: "geojson",
        data: faultsGjson,
      });

      // Neon glow underneath
      map.addLayer({
        id: "faults-glow",
        type: "line",
        source: "faults-source",
        paint: {
          "line-color": "#fbbf24",
          "line-width": 6,
          "line-opacity": 0.4,
          "line-blur": 2,
        },
      });

      // Crisp tectonic trace line
      map.addLayer({
        id: "faults-lines",
        type: "line",
        source: "faults-source",
        paint: {
          "line-color": "#f59e0b",
          "line-width": 2.5,
          "line-opacity": 0.9,
          "line-dasharray": [4, 2],
        },
      });

      map.on("click", "faults-lines", (e) => {
        if (!e.features || e.features.length === 0) return;
        const feat = e.features[0];
        const props = feat.properties || {};
        new maplibregl.Popup({ offset: 12 })
          .setLngLat(e.lngLat)
          .setHTML(
            `<div class="fault-popup">
              <h4>⚡ ${props.name || "Tectonic Fault"}</h4>
              <p><strong>Slip Mechanism:</strong> ${props.type || "Strike-slip / Transform"}</p>
              <p><strong>Slip Rate:</strong> ~${props.slip_rate_mm_yr || "10-30"} mm/yr</p>
              <p><strong>Rupture History:</strong> ${props.rupture_history || "Active Holocene plate boundary"}</p>
              <span class="popup-tag fault-tag">Active Tectonic Fault</span>
            </div>`
          )
          .addTo(map);
      });

      map.on("mouseenter", "faults-lines", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "faults-lines", () => {
        map.getCanvas().style.cursor = "";
      });
    }
  }, []);

  // Update or attach the Identified Aftershocks sequence layer
  const updateAftershocksLayer = useCallback((aftershockList: EarthquakeEvent[]) => {
    const map = mapRef.current;
    if (!map) return;

    const geojson = buildEventsGeoJSON(aftershockList);
    const source = map.getSource("aftershocks-source") as maplibregl.GeoJSONSource | undefined;

    if (source) {
      source.setData(geojson);
    } else {
      map.addSource("aftershocks-source", {
        type: "geojson",
        data: geojson,
      });

      // Neon purple aura
      map.addLayer({
        id: "aftershocks-glow",
        type: "circle",
        source: "aftershocks-source",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["get", "mag"],
            3.0, 9,
            5.0, 15,
            7.0, 22,
          ],
          "circle-color": "rgba(192, 132, 252, 0.35)",
          "circle-blur": 0.5,
        },
      });

      // Distinct cyan/violet ring marker
      map.addLayer({
        id: "aftershocks-rings",
        type: "circle",
        source: "aftershocks-source",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["get", "mag"],
            3.0, 6,
            5.0, 11,
            7.0, 17,
          ],
          "circle-color": "rgba(192, 132, 252, 0.15)",
          "circle-stroke-width": 2.5,
          "circle-stroke-color": "#c084fc",
          "circle-opacity": 0.9,
        },
      });

      map.on("click", "aftershocks-rings", (e) => {
        if (!e.features || e.features.length === 0) return;
        const feature = e.features[0];
        const props = feature.properties;
        const coords = (feature.geometry as Point).coordinates;

        new maplibregl.Popup({ offset: 15 })
          .setLngLat([coords[0], coords[1]])
          .setHTML(
            `<div class="aftershock-popup">
              <h4>💫 AFTERSHOCK: M ${props.mag}</h4>
              <p><strong>Place:</strong> ${props.place}</p>
              <p><strong>Depth:</strong> ${props.depth} km</p>
              <p><strong>Time:</strong> ${new Date(props.time).toLocaleString()}</p>
              <span class="popup-tag aftershock-tag">Clustered Omori Sequence</span>
            </div>`
          )
          .addTo(map);
      });

      map.on("mouseenter", "aftershocks-rings", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "aftershocks-rings", () => {
        map.getCanvas().style.cursor = "";
      });
    }
  }, [buildEventsGeoJSON]);

  // Update or attach the Probabilistic Forecast Risk Heatmap & Click Cells
  const updateRiskGridLayer = useCallback((geojson: FeatureCollection) => {
    const map = mapRef.current;
    if (!map) return;

    const source = map.getSource("risk-grid-source") as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(geojson);
    } else {
      map.addSource("risk-grid-source", {
        type: "geojson",
        data: geojson,
      });

      const beforeLayerId = map.getLayer("events-glow") ? "events-glow" : undefined;

      // Probabilistic Heatmap Layer
      map.addLayer(
        {
          id: "risk-forecast-heat",
          type: "heatmap",
          source: "risk-grid-source",
          paint: {
            "heatmap-weight": [
              "interpolate",
              ["linear"],
              ["coalesce", ["get", "risk_score"], 0],
              0, 0,
              0.2, 0.35,
              0.5, 0.75,
              1.0, 1.6,
            ],
            "heatmap-intensity": [
              "interpolate",
              ["linear"],
              ["zoom"],
              2, 0.7,
              6, 1.2,
              10, 1.8,
            ],
            "heatmap-color": [
              "interpolate",
              ["linear"],
              ["heatmap-density"],
              0, "rgba(0, 0, 0, 0)",
              0.15, "rgba(56, 189, 248, 0.35)",
              0.35, "rgba(16, 185, 129, 0.65)",
              0.60, "rgba(234, 179, 8, 0.85)",
              0.85, "rgba(239, 68, 68, 0.95)",
              1.0, "rgba(168, 85, 247, 1.0)",
            ],
            "heatmap-radius": [
              "interpolate",
              ["exponential", 2],
              ["zoom"],
              2, 10,
              5, 30,
              8, 70,
              11, 140,
            ],
            "heatmap-opacity": 0.85,
          },
        },
        beforeLayerId
      );

      // Interactive telemetry click targets for each grid point
      map.addLayer({
        id: "risk-grid-cells",
        type: "circle",
        source: "risk-grid-source",
        paint: {
          "circle-radius": 14,
          "circle-opacity": 0.01,
          "circle-stroke-width": 0,
        },
      });

      map.on("click", "risk-grid-cells", (e) => {
        if (!e.features || e.features.length === 0) return;
        const feat = e.features[0];
        const props = feat.properties || {};
        const coords = (feat.geometry as Point).coordinates;

        const score = typeof props.risk_score === "number" ? props.risk_score : 0;
        const prob = typeof props.probability === "number" ? props.probability : 0;
        const rate = typeof props.expected_rate === "number" ? props.expected_rate : 0;
        const relRisk = typeof props.relative_risk === "number" ? props.relative_risk : 1;

        new maplibregl.Popup({ offset: 12 })
          .setLngLat([coords[0], coords[1]])
          .setHTML(
            `<div class="risk-cell-popup">
              <h4>🔥 Forecast Risk Cell (${activeWindow})</h4>
              <p><strong>Coordinates:</strong> ${coords[1].toFixed(3)}°N, ${coords[0].toFixed(3)}°E</p>
              <p><strong>Expected Rate &lambda;:</strong> ${rate.toFixed(4)} events/day</p>
              <p><strong>Poisson P(M &ge; ${activeMinMag}):</strong> ${(prob * 100).toFixed(1)}%</p>
              <p><strong>Relative Risk:</strong> ${relRisk.toFixed(1)}x baseline</p>
              <p><strong>Risk Index:</strong> ${(score * 100).toFixed(0)}%</p>
              <span class="popup-tag">${(props.risk_level || "elevated").toUpperCase()} SECTOR</span>
            </div>`
          )
          .addTo(map);
      });

      map.on("mouseenter", "risk-grid-cells", () => {
        map.getCanvas().style.cursor = "crosshair";
      });
      map.on("mouseleave", "risk-grid-cells", () => {
        map.getCanvas().style.cursor = "";
      });
    }
  }, [activeWindow, activeMinMag]);

  // Update or attach the Mainshock Beacon & Rupture Zone Buffer
  const updateMainshockBeaconAndBuffer = useCallback((mainshock: EarthquakeEvent | null) => {
    const map = mapRef.current;
    if (!map) return;

    // Remove existing mainshock HTML marker
    if (mainshockMarkerRef.current) {
      mainshockMarkerRef.current.remove();
      mainshockMarkerRef.current = null;
    }

    if (!mainshock || !showMainshockLayer) {
      // Clear rupture buffer source if exists
      const ruptureSource = map.getSource("mainshock-rupture-source") as maplibregl.GeoJSONSource | undefined;
      if (ruptureSource) {
        ruptureSource.setData({ type: "FeatureCollection", features: [] });
      }
      return;
    }

    // 1. Create animated beacon marker element
    const el = document.createElement("div");
    el.className = "mainshock-beacon-marker";
    el.innerHTML = `
      <div class="mainshock-radar-ring"></div>
      <div class="mainshock-radar-ring-outer"></div>
      <div class="mainshock-core-star">★</div>
    `;

    const ruptureKm = Math.max(15.0, 10 ** (0.5 * mainshock.magnitude - 1.8));

    const popup = new maplibregl.Popup({ offset: 25 }).setHTML(
      `<div class="mainshock-popup">
        <h4>★ SEQUENCE MAINSHOCK: M ${mainshock.magnitude}</h4>
        <p><strong>Location:</strong> ${mainshock.place || "Primary Rupture"}</p>
        <p><strong>Origin Time:</strong> ${new Date(mainshock.time).toLocaleString()}</p>
        <p><strong>Depth:</strong> ${mainshock.depth_km ?? 10} km</p>
        <p><strong>Est. Rupture Length:</strong> ~${ruptureKm.toFixed(1)} km</p>
        <span class="popup-tag mainshock-tag">Primary Rupture Beacon</span>
      </div>`
    );

    mainshockMarkerRef.current = new maplibregl.Marker({ element: el })
      .setLngLat([mainshock.lon, mainshock.lat])
      .setPopup(popup)
      .addTo(map);

    // 2. Rupture Zone Buffer Circle Layer
    const bufferGeojson = buildCircleGeoJSON(mainshock.lon, mainshock.lat, ruptureKm * 1.5);
    const ruptureSource = map.getSource("mainshock-rupture-source") as maplibregl.GeoJSONSource | undefined;

    if (ruptureSource) {
      ruptureSource.setData(bufferGeojson);
    } else {
      map.addSource("mainshock-rupture-source", {
        type: "geojson",
        data: bufferGeojson,
      });

      const beforeId = map.getLayer("faults-glow") ? "faults-glow" : undefined;

      map.addLayer(
        {
          id: "mainshock-rupture-fill",
          type: "fill",
          source: "mainshock-rupture-source",
          paint: {
            "fill-color": "#ef4444",
            "fill-opacity": 0.14,
          },
        },
        beforeId
      );

      map.addLayer(
        {
          id: "mainshock-rupture-line",
          type: "line",
          source: "mainshock-rupture-source",
          paint: {
            "line-color": "#ef4444",
            "line-width": 2,
            "line-dasharray": [3, 2],
            "line-opacity": 0.85,
          },
        },
        beforeId
      );
    }
  }, [showMainshockLayer]);

  // Main function: geocode location & center map
  const handleCenterPlace = useCallback(async (placeQuery: string) => {
    const trimmed = placeQuery.trim();
    if (!trimmed) {
      setSearchFeedback("Please enter a place name");
      return;
    }

    setIsSearching(true);
    setSearchFeedback("Locating place & aligning basemap...");

    try {
      const location = await geocodePlace(trimmed);
      if (!location) {
        setSearchFeedback(`Could not locate "${trimmed}". Try another place name.`);
        setIsSearching(false);
        return;
      }

      setActiveLocation(location);

      const map = mapRef.current;
      if (map) {
        map.flyTo({
          center: [location.lon, location.lat],
          zoom: 7.5,
          speed: 1.4,
          curve: 1.2,
          essential: true,
        });

        if (centerMarkerRef.current) {
          centerMarkerRef.current.remove();
        }

        const markerEl = document.createElement("div");
        markerEl.className = "epicenter-marker";
        markerEl.innerHTML = `
          <div class="pulse-ring"></div>
          <div class="pulse-ring-outer"></div>
          <div class="center-dot"></div>
        `;

        const popup = new maplibregl.Popup({ offset: 25, closeButton: false }).setHTML(
          `<div class="epicenter-popup">
            <h4>${location.name}</h4>
            <p><strong>Center:</strong> ${location.lat.toFixed(4)}°, ${location.lon.toFixed(4)}°</p>
            <span class="popup-tag">Seismic Focus</span>
          </div>`
        );

        const marker = new maplibregl.Marker({ element: markerEl })
          .setLngLat([location.lon, location.lat])
          .setPopup(popup)
          .addTo(map);

        centerMarkerRef.current = marker;
      }

      setSearchFeedback(`Basemap centered on ${location.name.split(",")[0]}`);
      setTimeout(() => setSearchFeedback(null), 4000);
    } catch (err: unknown) {
      console.error("Geocoding error:", err);
      setSearchFeedback("Failed to locate place. Please retry.");
    } finally {
      setIsSearching(false);
    }
  }, []);

  // Initial MapLibre mount
  useEffect(() => {
    const protocol = new pmtiles.Protocol();
    maplibregl.addProtocol("pmtiles", protocol.tile);

    if (!mapContainerRef.current) return;

    try {
      const map = new maplibregl.Map({
        container: mapContainerRef.current,
        style: getStyleForTheme(activeTheme),
        center: [0, 20],
        zoom: 2.5,
        attributionControl: false,
      });

      map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
      map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
      map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");

      map.on("load", () => {
        setMapLoaded(true);
        map.resize();

        if (initialPlace) {
          handleCenterPlace(initialPlace);
        } else {
          handleCenterPlace("Turkey");
        }

        if (faultsData) {
          updateFaultsLayer(faultsData);
        }
        if (displayedEvents.length > 0) {
          updateEventsLayer(displayedEvents);
        }
      });

      // Click on map to inspect coordinates or trigger risk evaluation
      map.on("click", (e) => {
        const features = map.queryRenderedFeatures(e.point, {
          layers: ["events-circles", "aftershocks-rings", "faults-lines", "risk-grid-cells"],
        });
        if (features && features.length > 0) return;

        const coords = { lat: e.lngLat.lat, lon: e.lngLat.lng };
        if (onMapClick) {
          onMapClick(coords);
        }

        if (clickMarkerRef.current) {
          clickMarkerRef.current.remove();
        }

        const el = document.createElement("div");
        el.className = "target-crosshair-marker";
        el.innerHTML = `
          <svg width="30" height="30" viewBox="0 0 30 30" fill="none" class="reticle-svg">
            <circle cx="15" cy="15" r="10" stroke="#38bdf8" stroke-width="2" stroke-dasharray="3 3"/>
            <circle cx="15" cy="15" r="3" fill="#38bdf8"/>
            <line x1="15" y1="2" x2="15" y2="8" stroke="#38bdf8" stroke-width="2"/>
            <line x1="15" y1="22" x2="15" y2="28" stroke="#38bdf8" stroke-width="2"/>
            <line x1="2" y1="15" x2="8" y2="15" stroke="#38bdf8" stroke-width="2"/>
            <line x1="22" y1="15" x2="28" y2="15" stroke="#38bdf8" stroke-width="2"/>
          </svg>
        `;

        clickMarkerRef.current = new maplibregl.Marker({ element: el })
          .setLngLat([coords.lon, coords.lat])
          .addTo(map);
      });

      map.on("move", () => {
        const center = map.getCenter();
        const zoom = map.getZoom();
        setViewportInfo({
          lng: center.lng.toFixed(2),
          lat: center.lat.toFixed(2),
          zoom: zoom.toFixed(1),
        });
      });

      mapRef.current = map;

      const handleResize = () => {
        if (mapRef.current) {
          mapRef.current.resize();
        }
      };
      window.addEventListener("resize", handleResize);

      return () => {
        window.removeEventListener("resize", handleResize);
        if (centerMarkerRef.current) centerMarkerRef.current.remove();
        if (clickMarkerRef.current) clickMarkerRef.current.remove();
        if (mainshockMarkerRef.current) mainshockMarkerRef.current.remove();
        map.remove();
        mapRef.current = null;
        maplibregl.removeProtocol("pmtiles");
      };
    } catch (err: unknown) {
      console.error("Failed to initialize map:", err);
      setLoadError(err instanceof Error ? err.message : "Failed to initialize map");
    }
  }, [activeTheme, handleCenterPlace, initialPlace]);

  // Sync events and layers when data changes
  useEffect(() => {
    if (mapLoaded && mapRef.current) {
      updateEventsLayer(displayedEvents);
      updateAftershocksLayer(identifiedAftershocks);
      updateFaultsLayer(faultsData);
      updateMainshockBeaconAndBuffer(effectiveMainshock);
      if (riskGridFeatures) {
        updateRiskGridLayer(riskGridFeatures);
      }
    }
  }, [
    mapLoaded,
    displayedEvents,
    identifiedAftershocks,
    faultsData,
    effectiveMainshock,
    riskGridFeatures,
    updateEventsLayer,
    updateAftershocksLayer,
    updateFaultsLayer,
    updateMainshockBeaconAndBuffer,
    updateRiskGridLayer,
  ]);

  // Toggle layer visibilities in MapLibre
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    if (map.getLayer("risk-forecast-heat")) {
      map.setLayoutProperty("risk-forecast-heat", "visibility", showForecastHeatmap ? "visible" : "none");
    }
    if (map.getLayer("risk-grid-cells")) {
      map.setLayoutProperty("risk-grid-cells", "visibility", showForecastHeatmap ? "visible" : "none");
    }
    if (map.getLayer("faults-lines")) {
      map.setLayoutProperty("faults-lines", "visibility", showFaultsLayer ? "visible" : "none");
    }
    if (map.getLayer("faults-glow")) {
      map.setLayoutProperty("faults-glow", "visibility", showFaultsLayer ? "visible" : "none");
    }
    if (map.getLayer("aftershocks-rings")) {
      map.setLayoutProperty("aftershocks-rings", "visibility", showAftershocksLayer ? "visible" : "none");
    }
    if (map.getLayer("aftershocks-glow")) {
      map.setLayoutProperty("aftershocks-glow", "visibility", showAftershocksLayer ? "visible" : "none");
    }
    if (map.getLayer("events-circles")) {
      map.setLayoutProperty("events-circles", "visibility", showEventsLayer ? "visible" : "none");
    }
    if (map.getLayer("events-glow")) {
      map.setLayoutProperty("events-glow", "visibility", showEventsLayer ? "visible" : "none");
    }
    if (map.getLayer("mainshock-rupture-fill")) {
      map.setLayoutProperty("mainshock-rupture-fill", "visibility", showMainshockLayer ? "visible" : "none");
    }
    if (map.getLayer("mainshock-rupture-line")) {
      map.setLayoutProperty("mainshock-rupture-line", "visibility", showMainshockLayer ? "visible" : "none");
    }
  }, [
    showForecastHeatmap,
    showFaultsLayer,
    showAftershocksLayer,
    showEventsLayer,
    showMainshockLayer,
    mapLoaded,
  ]);

  // Sync selected event camera fly-to
  useEffect(() => {
    if (selectedEvent && mapRef.current) {
      mapRef.current.flyTo({
        center: [selectedEvent.lon, selectedEvent.lat],
        zoom: 7.0,
        speed: 1.5,
        curve: 1.3,
        essential: true,
      });
    }
  }, [selectedEvent]);

  // Sync external target coordinates
  useEffect(() => {
    if (targetCoords && mapRef.current) {
      mapRef.current.flyTo({
        center: [targetCoords.lon, targetCoords.lat],
        zoom: 6.5,
        speed: 1.4,
        essential: true,
      });

      if (clickMarkerRef.current) {
        clickMarkerRef.current.remove();
      }

      const el = document.createElement("div");
      el.className = "target-crosshair-marker";
      el.innerHTML = `
        <svg width="30" height="30" viewBox="0 0 30 30" fill="none" class="reticle-svg">
          <circle cx="15" cy="15" r="10" stroke="#38bdf8" stroke-width="2" stroke-dasharray="3 3"/>
          <circle cx="15" cy="15" r="3" fill="#38bdf8"/>
          <line x1="15" y1="2" x2="15" y2="8" stroke="#38bdf8" stroke-width="2"/>
          <line x1="15" y1="22" x2="15" y2="28" stroke="#38bdf8" stroke-width="2"/>
          <line x1="2" y1="15" x2="8" y2="15" stroke="#38bdf8" stroke-width="2"/>
          <line x1="22" y1="15" x2="28" y2="15" stroke="#38bdf8" stroke-width="2"/>
        </svg>
      `;

      clickMarkerRef.current = new maplibregl.Marker({ element: el })
        .setLngLat([targetCoords.lon, targetCoords.lat])
        .addTo(mapRef.current);
    }
  }, [targetCoords]);

  const switchTheme = (theme: "light" | "dark" | "grayscale") => {
    setActiveTheme(theme);
    if (mapRef.current) {
      mapRef.current.setStyle(getStyleForTheme(theme));
    }
  };

  const handleResetView = () => {
    if (mapRef.current) {
      mapRef.current.flyTo({ center: [0, 20], zoom: 2.5, essential: true });
    }
  };

  const handleSyncCatalog = async () => {
    setIsSyncing(true);
    setSearchFeedback("Downloading live earthquake data from USGS...");
    try {
      const response = await fetch("/api/refresh-catalog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days_back: 30, min_magnitude: 2.5 }),
      });
      const data = (await response.json()) as {
        events_fetched?: number;
        last_catalog_update?: string;
        data_as_of?: string;
        message?: string;
        error?: string;
      };
      if (!response.ok) {
        throw new Error(data.message || data.error || "Catalog synchronization failed");
      }
      const syncedAt = data.last_catalog_update || data.data_as_of || new Date().toISOString();
      setLastSyncTime(syncedAt);
      const countInfo = data.events_fetched !== undefined ? ` (+${data.events_fetched} live quakes)` : "";
      setSearchFeedback(`Live USGS catalog synchronized${countInfo}`);
      onSyncSuccess?.();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Catalog synchronization failed";
      setSearchFeedback(`${message}. Existing cached data was preserved.`);
    } finally {
      setIsSyncing(false);
      setTimeout(() => setSearchFeedback(null), 5000);
    }
  };

  const onSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      handleCenterPlace(searchInput);
    }
  };

  const handleForecastWindowChange = (w: "24h" | "72h" | "7d") => {
    setInternalForecastWindow(w);
    onChangeForecastWindow?.(w);
  };

  const handleMinMagChange = (m: number) => {
    setInternalMinMagnitude(m);
    onChangeMinMagnitude?.(m);
  };

  const presetPlaces = ["Turkey", "Tokyo", "San Francisco", "Chile", "Nepal", "Kochi"];

  return (
    <div className="map-view-container">
      {/* Top Floating Control Bar */}
      <header className="map-top-bar">
        {onBack && (
          <div className="map-top-left">
            <button className="btn-secondary" onClick={onBack} title="Return to overview">
              <span className="btn-icon">←</span> Back
            </button>
            <div className="brand-badge">
              <span className="brand-dot" />
              <span className="brand-title">Quack Earth</span>
              <span className="badge-tech">PMTiles v4</span>
            </div>
          </div>
        )}

        {/* Floating Location Search Input */}
        <div className="map-search-wrapper">
          <form className="search-form" onSubmit={onSearchSubmit}>
            <div className="search-input-group">
              <span className="search-icon">🔍</span>
              <input
                type="text"
                className="search-input"
                placeholder="Enter place name (e.g. Turkey, Tokyo, San Francisco)..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                disabled={isSearching}
                id="place-search-input"
              />
              {searchInput && (
                <button
                  type="button"
                  className="search-clear-btn"
                  onClick={() => setSearchInput("")}
                  title="Clear input"
                >
                  ✕
                </button>
              )}
              <button
                type="submit"
                className="btn-search-submit"
                disabled={isSearching || !searchInput.trim()}
                id="generate-heatmap-button"
              >
                {isSearching ? <span className="btn-spinner" /> : <span>Focus Basemap</span>}
              </button>
            </div>
          </form>

          {/* Quick Presets */}
          <div className="search-presets">
            <span className="presets-label">Quick:</span>
            {presetPlaces.map((place) => (
              <button
                key={place}
                type="button"
                className={`preset-chip ${activeLocation?.name.includes(place) ? "active" : ""}`}
                onClick={() => {
                  setSearchInput(place);
                  handleCenterPlace(place);
                }}
              >
                {place}
              </button>
            ))}
          </div>

          {/* Live Feedback Toast */}
          {searchFeedback && (
            <div className="search-feedback-toast">
              <span>{searchFeedback}</span>
            </div>
          )}
        </div>

        <div className="map-top-right">
          {/* Mainshock Selector Dropdown */}
          <div className="mainshock-selector-group">
            <span className="scenario-label font-mono">MAINSHOCK:</span>
            <select
              className="mainshock-dropdown font-mono"
              value={effectiveMainshock?.id || ""}
              onChange={(e) => {
                const found = events.find((ev) => ev.id === e.target.value);
                onSelectMainshock?.(found || null);
              }}
              title="Select sequence mainshock"
            >
              <option value="">
                {effectiveMainshock ? `★ Auto: M${effectiveMainshock.magnitude.toFixed(1)} (${effectiveMainshock.place?.slice(0, 15)}...)` : "-- Auto: No Mainshock --"}
              </option>
              {events
                .filter((ev) => ev.magnitude >= 4.5)
                .sort((a, b) => b.magnitude - a.magnitude)
                .map((ev) => (
                  <option key={ev.id} value={ev.id}>
                    M{ev.magnitude.toFixed(1)} - {ev.place?.slice(0, 20) || ev.id}
                  </option>
                ))}
            </select>
            {effectiveMainshock && (
              <button
                type="button"
                className="btn-clear-mainshock"
                onClick={() => onSelectMainshock?.(null)}
                title="Clear selected mainshock"
              >
                ✕ Clear
              </button>
            )}
          </div>

          {/* Forecast Horizon Window Toggle */}
          <div className="forecast-window-selector">
            <span className="scenario-label font-mono">WINDOW:</span>
            {(["24h", "72h", "7d"] as const).map((w) => (
              <button
                key={w}
                type="button"
                className={`forecast-window-btn font-mono ${activeWindow === w ? "active" : ""}`}
                onClick={() => handleForecastWindowChange(w)}
                title={`Set aftershock risk forecast window to ${w}`}
              >
                {w}
              </button>
            ))}
          </div>

          {/* Minimum Magnitude Slider */}
          <div className="mag-toolbar-slider">
            <span className="mag-toolbar-label font-mono">Min Mag:</span>
            <span className="mag-toolbar-val font-mono">M{activeMinMag.toFixed(1)}</span>
            <input
              type="range"
              min="2.0"
              max="6.0"
              step="0.5"
              value={activeMinMag}
              onChange={(e) => handleMinMagChange(parseFloat(e.target.value))}
              className="mag-toolbar-input"
              title={`Filter events and forecast to magnitude >= ${activeMinMag.toFixed(1)}`}
            />
          </div>

          {/* Scenario Selector Dropdown */}
          <div className="scenario-selector-group">
            <span className="scenario-label font-mono">SCENARIO:</span>
            <select
              className="scenario-select-dropdown font-mono"
              value={activeScenarioId || "live_usgs"}
              onChange={(e) => onSelectScenario?.(e.target.value)}
              title="Select a disaster scenario or live USGS feed"
            >
              <option value="live_usgs">🌐 Live USGS Streaming Feed</option>
              <option value="turkey_2023">🇹🇷 2023 Turkey M7.8 Doublet</option>
              <option value="tokyo_bay">🇯🇵 Tokyo Bay Fault Swarm</option>
              <option value="ridgecrest_2019">🇺🇸 2019 Ridgecrest Sequence</option>
            </select>
          </div>

          {/* Layer visibility toggles */}
          <div className="layer-toggle-group">
            <button
              type="button"
              className={`layer-btn ${showForecastHeatmap ? "active" : ""}`}
              onClick={() => setShowForecastHeatmap((prev) => !prev)}
              title="Toggle Probabilistic Omori Forecast Heatmap"
            >
              🔥 Forecast
            </button>
            <button
              type="button"
              className={`layer-btn ${showFaultsLayer ? "active" : ""}`}
              onClick={() => setShowFaultsLayer((prev) => !prev)}
              title="Toggle Tectonic Fault Traces"
            >
              ⚡ Faults
            </button>
            <button
              type="button"
              className={`layer-btn ${showAftershocksLayer ? "active" : ""}`}
              onClick={() => setShowAftershocksLayer((prev) => !prev)}
              title="Toggle Identified Aftershock Rings"
            >
              💫 Aftershocks ({identifiedAftershocks.length})
            </button>
            <button
              type="button"
              className={`layer-btn ${showMainshockLayer ? "active" : ""}`}
              onClick={() => setShowMainshockLayer((prev) => !prev)}
              title="Toggle Mainshock Beacon & Rupture Buffer"
            >
              ★ Mainshock
            </button>
            <button
              type="button"
              className={`layer-btn ${showEventsLayer ? "active" : ""}`}
              onClick={() => setShowEventsLayer((prev) => !prev)}
              title="Toggle Observed Quakes"
            >
              • Quakes ({displayedEvents.length})
            </button>
          </div>

          {/* Theme toggles */}
          <div className="theme-toggle-group">
            <button
              className={`theme-btn ${activeTheme === "light" ? "active" : ""}`}
              onClick={() => switchTheme("light")}
              title="Light theme"
            >
              Light
            </button>
            <button
              className={`theme-btn ${activeTheme === "dark" ? "active" : ""}`}
              onClick={() => switchTheme("dark")}
              title="Dark theme"
            >
              Dark
            </button>
            <button
              className={`theme-btn ${activeTheme === "grayscale" ? "active" : ""}`}
              onClick={() => switchTheme("grayscale")}
              title="Grayscale theme"
            >
              Mono
            </button>
          </div>

          <button className="btn-secondary" onClick={handleResetView} title="Reset camera to world overview">
            Reset View
          </button>

          <button
            className="btn-sync"
            onClick={() => void handleSyncCatalog()}
            disabled={isSyncing}
            title="Download live earthquake catalog from USGS"
          >
            {isSyncing ? <span className="btn-spinner" /> : "↻"}{" "}
            {isSyncing ? "Syncing..." : isOffline ? "Offline Cache" : "Sync USGS"}
          </button>
        </div>
      </header>

      {/* Scientific Legend & Forecast HUD */}
      <aside className={`scientific-legend-card ${!isLegendExpanded ? "minimized" : ""}`}>
        <div
          className="legend-card-header"
          onClick={() => setIsLegendExpanded((prev) => !prev)}
          role="button"
          tabIndex={0}
        >
          <h3 className="legend-title">
            <span>🔬 Risk Model & Symbology</span>
            <span className="legend-formula-badge font-mono">{activeWindow}</span>
          </h3>
          <button type="button" className="card-collapse-btn">
            {isLegendExpanded ? "▾" : "▴"}
          </button>
        </div>

        {isLegendExpanded && (
          <>
            <div className="legend-section-heading">Relative Risk Scale (R / R₀)</div>
            <div className="legend-gradient-bar" />
            <div className="legend-label-row">
              <span>Low (&lt;1.5x)</span>
              <span>Elevated</span>
              <span>High (&gt;10x)</span>
            </div>

            <div className="legend-section-heading">Occurrence Probability P(N ≥ 1)</div>
            <div className="legend-symbology-grid font-mono">
              <div className="legend-symbology-item">
                <span className="symbol-icon text-cyan">•</span>
                <span>Low: &lt; 5%</span>
              </div>
              <div className="legend-symbology-item">
                <span className="symbol-icon text-emerald">•</span>
                <span>Moderate: 5% - 20%</span>
              </div>
              <div className="legend-symbology-item">
                <span className="symbol-icon text-orange">•</span>
                <span>Elevated: 20% - 50%</span>
              </div>
              <div className="legend-symbology-item">
                <span className="symbol-icon text-red">•</span>
                <span>Critical: &gt; 50%</span>
              </div>
            </div>

            <div className="legend-section-heading">Map Symbology</div>
            <div className="legend-symbology-grid">
              <div className="legend-symbology-item">
                <span className="symbol-icon text-red">★</span>
                <span>Sequence Mainshock Beacon</span>
              </div>
              <div className="legend-symbology-item">
                <span className="symbol-icon text-purple">💫</span>
                <span>Identified Aftershock Ring</span>
              </div>
              <div className="legend-symbology-item">
                <span className="symbol-line-fault" />
                <span>Active Tectonic Fault Trace</span>
              </div>
              <div className="legend-symbology-item">
                <span className="symbol-icon text-cyan">•</span>
                <span>Observed Earthquakes (USGS)</span>
              </div>
            </div>

            {effectiveMainshock && (
              <div className="heatmap-metrics-row" style={{ marginTop: "10px" }}>
                <div className="metric-item">
                  <span className="metric-val font-mono">M{effectiveMainshock.magnitude.toFixed(1)}</span>
                  <span className="metric-lbl">Mainshock</span>
                </div>
                <div className="metric-item">
                  <span className="metric-val font-mono">{identifiedAftershocks.length}</span>
                  <span className="metric-lbl">Aftershocks</span>
                </div>
                <div className="metric-item">
                  <span className="metric-val font-mono">
                    {sequenceDetails?.omori_fit?.p ? `p=${sequenceDetails.omori_fit.p.toFixed(2)}` : "Omori"}
                  </span>
                  <span className="metric-lbl">Decay Rate</span>
                </div>
              </div>
            )}

            <p className="legend-disclaimer">
              ⚠️ Scientific Notice: Probabilistic aftershock forecasting based on the modified Omori-Utsu decay law and inhomogeneous Poisson processes. Not a deterministic prediction of exact times or locations.
            </p>
            {lastSyncTime && (
              <p style={{ fontSize: "0.64rem", color: "var(--text-dim)", marginTop: "6px", fontFamily: "var(--font-mono)" }}>
                Catalog synced: {new Date(lastSyncTime).toLocaleTimeString()}
              </p>
            )}
          </>
        )}
      </aside>

      {/* Unified Mission-Control Timeline & Telemetry Console */}
      <footer className="timeline-scrubber-bar mission-control-console">
        <div className="timeline-dock-header">
          {/* Playback Controls */}
          <div className="timeline-controls-left">
            <button
              type="button"
              className={`btn-timeline-play ${isPlayingTimeline ? "active" : ""}`}
              onClick={() => {
                if (timelinePercent >= 100) {
                  setTimelinePercent(0);
                }
                setIsPlayingTimeline((prev) => !prev);
              }}
              title={isPlayingTimeline ? "Pause sequence playback" : "Play earthquake sequence playback"}
            >
              {isPlayingTimeline ? "⏸ Pause" : "▶ Play Sequence"}
            </button>
            <button
              type="button"
              className="btn-timeline-reset"
              onClick={() => {
                setIsPlayingTimeline(false);
                setTimelinePercent(100);
              }}
              title="Reset scrubber to latest"
            >
              ↺ Latest
            </button>
          </div>

          {/* Center: Shock Counter Telemetry */}
          <div className="timeline-dock-center">
            <span className="timeline-shock-badge font-mono">
              ⚡ <strong className="text-cyan">{displayedEvents.length}</strong> shocks (
              <span className="text-purple">{identifiedAftershocks.length} aftershocks</span>)
              <span className="timeline-pct-tag">[{timelinePercent.toFixed(0)}%]</span>
            </span>
          </div>

          {/* Right: Viewport Coordinates & Hint */}
          <div className="timeline-dock-coords font-mono">
            <span className="dock-coord-val">{viewportInfo.lat}°N, {viewportInfo.lng}°E</span>
            <span className="dock-zoom-badge">z{viewportInfo.zoom}</span>
            <span className="dock-tip-pill" title="Click anywhere on the map to evaluate site-specific seismic hazard">
              <span className="click-hint-full">💡 Click map for risk</span>
              <span className="click-hint-short">💡 Risk inspect</span>
            </span>
          </div>
        </div>

        {/* Timeline Slider Track */}
        <div className="timeline-slider-container">
          <div className="timeline-slider-track-row">
            <span className="timeline-edge-label font-mono">T-0 (Start)</span>
            <div className="timeline-range-wrapper">
              <input
                type="range"
                min="0"
                max="100"
                step="1"
                value={timelinePercent}
                onChange={(e) => {
                  setIsPlayingTimeline(false);
                  setTimelinePercent(parseFloat(e.target.value));
                }}
                className="styled-range timeline-range-slider"
                title={`Timeline sequence position: ${timelinePercent.toFixed(0)}%`}
              />
            </div>
            <span className="timeline-edge-label font-mono">Latest (100%)</span>
          </div>
        </div>
      </footer>

      {/* Loading Overlay */}
      {!mapLoaded && !loadError && (
        <div className="map-loading-overlay">
          <div className="spinner" />
          <p className="loading-text">Loading PMTiles basemap archive...</p>
        </div>
      )}

      {/* Error Banner */}
      {loadError && (
        <div className="map-error-banner">
          <p>Error initializing map: {loadError}</p>
        </div>
      )}

      {/* MapLibre WebGL Canvas Container */}
      <div ref={mapContainerRef} className="map-canvas-container" id="map-container" />
    </div>
  );
}
