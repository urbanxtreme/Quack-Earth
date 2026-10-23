import { useEffect, useRef, useState, useCallback } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import * as pmtiles from "pmtiles";
import { layers, namedFlavor } from "@protomaps/basemaps";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { FeatureCollection } from "geojson";

// Configure MapLibre Web Worker for Vite
maplibregl.setWorkerUrl(maplibreWorkerUrl);

interface MapViewerProps {
  onBack: () => void;
  initialPlace?: string;
}

interface GeocodedLocation {
  name: string;
  lat: number;
  lon: number;
}

interface HeatmapStats {
  locationName: string;
  centerLat: number;
  centerLon: number;
}

interface MapEventProperties {
  id: string;
  time: string;
  lat: number;
  lon: number;
  magnitude: number | null;
  depth_km?: number;
  source: string;
}

interface MapEventFeature {
  type: "Feature";
  id?: string;
  geometry: {
    type: "Point";
    coordinates: [number, number];
  };
  properties: MapEventProperties;
}

interface MapEventsResponse {
  type: "FeatureCollection";
  features: MapEventFeature[];
  count: number;
  data_as_of: string | null;
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

  // 1. Try local Vite proxy first (includes User-Agent header)
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
    // Fall through to fallback
  }

  // 2. Direct Nominatim fallback
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
    // Fall through to presets
  }

  // 3. Predefined coordinates dictionary fallback for global seismic and landmark places
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
    santiago: { name: "Santiago, Chile", lat: -33.4489, lon: -70.6693 },
    nepal: { name: "Nepal", lat: 28.3949, lon: 84.124 },
    kathmandu: { name: "Kathmandu, Nepal", lat: 27.7172, lon: 85.324 },
    turkey: { name: "Turkey", lat: 38.9637, lon: 35.2433 },
    istanbul: { name: "Istanbul, Turkey", lat: 41.0082, lon: 28.9784 },
    indonesia: { name: "Indonesia", lat: -0.7893, lon: 113.9213 },
    jakarta: { name: "Jakarta, Indonesia", lat: -6.2088, lon: 106.8456 },
    iceland: { name: "Iceland", lat: 64.9631, lon: -19.0208 },
    reykjavik: { name: "Reykjavik, Iceland", lat: 64.1466, lon: -21.9426 },
    "new delhi": { name: "New Delhi, Delhi, India", lat: 28.6139, lon: 77.209 },
    india: { name: "India", lat: 20.5937, lon: 78.9629 },
    london: { name: "London, England, UK", lat: 51.5074, lon: -0.1278 },
    "new york": { name: "New York, USA", lat: 40.7128, lon: -74.006 },
    hawaii: { name: "Hawaii, USA", lat: 19.8968, lon: -155.5828 },
    mexico: { name: "Mexico", lat: 23.6345, lon: -102.5528 },
    "mexico city": { name: "Mexico City, Mexico", lat: 19.4326, lon: -99.1332 },
    taiwan: { name: "Taiwan", lat: 23.6978, lon: 120.9605 },
    alaska: { name: "Alaska, USA", lat: 64.2008, lon: -149.4937 },
  };

  for (const [key, val] of Object.entries(presets)) {
    if (normalized.includes(key) || key.includes(normalized)) {
      return val;
    }
  }

  return null;
}

export default function MapViewer({ onBack, initialPlace }: MapViewerProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const centerMarkerRef = useRef<maplibregl.Marker | null>(null);
  const eventMarkersRef = useRef<maplibregl.Marker[]>([]);
  const currentHeatmapDataRef = useRef<FeatureCollection | null>(null);

  const [mapLoaded, setMapLoaded] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTheme, setActiveTheme] = useState<"light" | "dark" | "grayscale">("light");

  const [searchInput, setSearchInput] = useState<string>(initialPlace || "");
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [searchFeedback, setSearchFeedback] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null);
  const [activeLocation, setActiveLocation] = useState<GeocodedLocation | null>(null);
  const [heatmapStats, setHeatmapStats] = useState<HeatmapStats | null>(null);
  const [isHeatmapCardMinimized, setIsHeatmapCardMinimized] = useState<boolean>(false);
  const [eventMarkerCount, setEventMarkerCount] = useState<number>(0);
  const [isLoadingEvents, setIsLoadingEvents] = useState<boolean>(false);

  const [viewportInfo, setViewportInfo] = useState<{ lng: string; lat: string; zoom: string }>({
    lng: "0.00",
    lat: "20.00",
    zoom: "2.5",
  });

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

  // Attach a single, clean heatmap layer around the place center
  const applyHeatmapLayer = useCallback((geojson: FeatureCollection) => {
    const map = mapRef.current;
    if (!map) return;

    currentHeatmapDataRef.current = geojson;

    const source = map.getSource("heatmap-source") as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(geojson);
      return;
    }

    // Add GeoJSON source with the single center point
    map.addSource("heatmap-source", {
      type: "geojson",
      data: geojson,
    });

    // Add a single cohesive Heatmap Layer centered around that point
    map.addLayer({
      id: "earthquake-heat",
      type: "heatmap",
      source: "heatmap-source",
      paint: {
        "heatmap-weight": 1,
        "heatmap-intensity": [
          "interpolate",
          ["linear"],
          ["zoom"],
          0, 1,
          5, 1.2,
          8, 1.6,
          12, 2.2,
        ],
        // Smooth radial thermal gradient
        "heatmap-color": [
          "interpolate",
          ["linear"],
          ["heatmap-density"],
          0, "rgba(0, 0, 0, 0)",
          0.2, "rgba(56, 189, 248, 0.45)",
          0.45, "rgba(250, 204, 21, 0.75)",
          0.7, "rgba(251, 146, 60, 0.88)",
          0.9, "rgba(239, 68, 68, 0.95)",
          1.0, "rgba(185, 28, 28, 1)",
        ],
        // Smooth radial size expanding with map zoom
        "heatmap-radius": [
          "interpolate",
          ["exponential", 2],
          ["zoom"],
          2, 25,
          4, 50,
          6, 90,
          8, 160,
          10, 260,
          12, 440,
        ],
        "heatmap-opacity": 0.82,
      },
    });
  }, []);

  const loadEarthquakeMarkers = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;

    const bounds = map.getBounds();
    const params = new URLSearchParams({
      min_lat: bounds.getSouth().toString(),
      max_lat: bounds.getNorth().toString(),
      min_lon: bounds.getWest().toString(),
      max_lon: bounds.getEast().toString(),
      hours: "168",
      min_magnitude: "2.5",
      limit: "500",
    });

    setIsLoadingEvents(true);
    try {
      const response = await fetch(`/api/v1/map/events?${params.toString()}`);
      const data = (await response.json()) as MapEventsResponse;
      if (!response.ok) {
        throw new Error("Unable to load earthquake markers");
      }

      eventMarkersRef.current.forEach((marker) => marker.remove());
      eventMarkersRef.current = data.features.map((feature) => {
        const magnitude = feature.properties.magnitude ?? 0;
        const size = Math.max(10, Math.min(28, 10 + magnitude * 2));
        const markerElement = document.createElement("div");
        markerElement.className = "earthquake-marker";
        markerElement.style.width = `${size}px`;
        markerElement.style.height = `${size}px`;
        markerElement.style.backgroundColor = magnitude >= 5
          ? "var(--heat-red)"
          : magnitude >= 4
            ? "var(--heat-orange)"
            : "var(--heat-yellow)";

        const popupContent = document.createElement("div");
        popupContent.className = "earthquake-popup";
        const title = document.createElement("strong");
        title.textContent = `Magnitude ${magnitude.toFixed(1)}`;
        const details = document.createElement("p");
        details.textContent = [
          new Date(feature.properties.time).toLocaleString(),
          `Depth: ${feature.properties.depth_km?.toFixed(1) ?? "—"} km`,
          `Source: ${feature.properties.source}`,
        ].join(" · ");
        popupContent.append(title, details);

        return new maplibregl.Marker({ element: markerElement })
          .setLngLat(feature.geometry.coordinates)
          .setPopup(new maplibregl.Popup({ offset: 12 }).setDOMContent(popupContent))
          .addTo(map);
      });
      setEventMarkerCount(data.count);
    } catch (error: unknown) {
      console.warn("Could not load earthquake markers:", error);
      setEventMarkerCount(0);
    } finally {
      setIsLoadingEvents(false);
    }
  }, []);

  // Main function: geocode location, center map, and create single heatmap around it
  const handleGenerateHeatmap = useCallback(async (placeQuery: string) => {
    const trimmed = placeQuery.trim();
    if (!trimmed) {
      setSearchFeedback("Please enter a place name");
      return;
    }

    setIsSearching(true);
    setSearchFeedback("Locating place & generating heatmap...");

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
        // Fly camera directly to the place as center
        map.flyTo({
          center: [location.lon, location.lat],
          zoom: 7.5,
          speed: 1.4,
          curve: 1.2,
          essential: true,
        });

        // Add or update center epicenter marker
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
            <span class="popup-tag">Heatmap Center</span>
          </div>`
        );

        const marker = new maplibregl.Marker({ element: markerEl })
          .setLngLat([location.lon, location.lat])
          .setPopup(popup)
          .addTo(map);

        centerMarkerRef.current = marker;
      }

      // Single feature: exactly ONE point at the place center
      const geojson: FeatureCollection = {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: {
              mag: 6.0,
            },
            geometry: {
              type: "Point",
              coordinates: [location.lon, location.lat],
            },
          },
        ],
      };

      applyHeatmapLayer(geojson);

      setHeatmapStats({
        locationName: location.name,
        centerLat: location.lat,
        centerLon: location.lon,
      });
      setIsHeatmapCardMinimized(false);

      setSearchFeedback(`Heatmap centered on ${location.name.split(",")[0]}`);
      setTimeout(() => setSearchFeedback(null), 4000);
    } catch (err: unknown) {
      console.error("Heatmap generation error:", err);
      setSearchFeedback("Failed to generate heatmap. Please retry.");
    } finally {
      setIsSearching(false);
    }
  }, [applyHeatmapLayer]);

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
        void loadEarthquakeMarkers();

        // If an initial place was passed or provided, generate heatmap immediately
        if (initialPlace) {
          handleGenerateHeatmap(initialPlace);
        } else {
          // Default single heatmap centered on Tokyo
          handleGenerateHeatmap("Tokyo");
        }
      });

      // Re-apply heatmap layer when style changes (e.g. theme toggle)
      map.on("style.load", () => {
        if (currentHeatmapDataRef.current) {
          applyHeatmapLayer(currentHeatmapDataRef.current);
        }
      });

      const timeoutId = setTimeout(() => {
        setMapLoaded(true);
        if (mapRef.current) {
          mapRef.current.resize();
        }
      }, 2000);

      map.on("error", (e: maplibregl.ErrorEvent) => {
        console.warn("MapLibre event error:", e);
      });

      map.on("move", () => {
        const center = map.getCenter();
        const zoom = map.getZoom();
        setViewportInfo({
          lng: center.lng.toFixed(2),
          lat: center.lat.toFixed(2),
          zoom: zoom.toFixed(1),
        });
        map.on("moveend", () => {
          void loadEarthquakeMarkers();
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
        clearTimeout(timeoutId);
        window.removeEventListener("resize", handleResize);
        if (centerMarkerRef.current) {
          centerMarkerRef.current.remove();
        }
        eventMarkersRef.current.forEach((marker) => marker.remove());
        eventMarkersRef.current = [];
        map.remove();
        mapRef.current = null;
        maplibregl.removeProtocol("pmtiles");
      };
    } catch (err: unknown) {
      console.error("Failed to initialize map:", err);
      setLoadError(err instanceof Error ? err.message : "Failed to initialize map");
    }
  }, [activeTheme, applyHeatmapLayer, handleGenerateHeatmap, initialPlace, loadEarthquakeMarkers]);

  // Update theme dynamically
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
    setSearchFeedback("Synchronizing earthquake data with USGS...");
    try {
      const response = await fetch("/api/v1/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days_back: 30, min_magnitude: 2.5 }),
      });
      const data = (await response.json()) as {
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
      setSearchFeedback(
        `USGS catalog synchronized${data.message ? `: ${data.message}` : ""}`,
      );
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
      handleGenerateHeatmap(searchInput);
    }
  };

  const presetPlaces = ["Tokyo", "San Francisco", "Kochi", "Chile", "Nepal", "Turkey"];

  return (
    <div className="map-view-container">
      {/* Top Floating Header & Controls */}
      <header className="map-top-bar">
        <div className="map-top-left">
          <button className="btn-secondary" onClick={onBack} title="Return to home screen">
            <span className="btn-icon">←</span> Back
          </button>
          <div className="brand-badge">
            <span className="brand-dot" />
            <span className="brand-title">Quack Earth</span>
            <span className="badge-tech">PMTiles v4</span>
          </div>
        </div>

        {/* Floating Location Search Input Box */}
        <div className="map-search-wrapper">
          <form className="search-form" onSubmit={onSearchSubmit}>
            <div className="search-input-group">
              <span className="search-icon">🔍</span>
              <input
                type="text"
                className="search-input"
                placeholder="Enter place name (e.g. Tokyo, San Francisco, Kochi)..."
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
                {isSearching ? <span className="btn-spinner" /> : <span>Create Heatmap</span>}
              </button>
            </div>
          </form>

          {/* Quick preset location tags */}
          <div className="search-presets">
            <span className="presets-label">Quick:</span>
            {presetPlaces.map((place) => (
              <button
                key={place}
                type="button"
                className={`preset-chip ${activeLocation?.name.includes(place) ? "active" : ""}`}
                onClick={() => {
                  setSearchInput(place);
                  handleGenerateHeatmap(place);
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
            title="Download the latest earthquake catalog from USGS"
          >
            {isSyncing ? <span className="btn-spinner" /> : "↻"}{" "}
            {isSyncing ? "Syncing..." : "Sync USGS"}
          </button>
        </div>
      </header>

      {/* Heatmap Legend and Active Center Info Overlay */}
      {heatmapStats && (
        <aside className={`heatmap-info-card ${isHeatmapCardMinimized ? "minimized" : ""}`}>
          <div className="heatmap-info-header">
            <span className="heatmap-fire-icon">🔥</span>
            <div>
              <h3 className="heatmap-location-title">{heatmapStats.locationName}</h3>
              <p className="heatmap-coords">
                Center: {heatmapStats.centerLat.toFixed(3)}°, {heatmapStats.centerLon.toFixed(3)}°
              </p>
            </div>
            <div className="heatmap-card-actions">
              <button
                className="heatmap-card-action"
                type="button"
                onClick={() => setIsHeatmapCardMinimized((current) => !current)}
                aria-label={isHeatmapCardMinimized ? "Expand location information" : "Minimize location information"}
                title={isHeatmapCardMinimized ? "Expand" : "Minimize"}
              >
                {isHeatmapCardMinimized ? "+" : "−"}
              </button>
              <button
                className="heatmap-card-action close"
                type="button"
                onClick={() => setHeatmapStats(null)}
                aria-label="Close location information"
                title="Close"
              >
                ×
              </button>
            </div>
          </div>

          {!isHeatmapCardMinimized && <div className="heatmap-card-content">
          <div className="heatmap-legend">
            <div className="legend-label-row">
              <span>Low</span>
              <span>Single Center Heatmap</span>
              <span>High</span>
            </div>
            <div className="legend-gradient-bar" />
          </div>

          <div className="heatmap-metrics-row">
            <div className="metric-item">
              <span className="metric-val">1 Center</span>
              <span className="metric-lbl">Target Epicenter</span>
            </div>
            <div className="metric-item">
              <span className="metric-val">Radial</span>
              <span className="metric-lbl">Gradient</span>
            </div>
            <div className="metric-item">
              <span className="metric-val">{isLoadingEvents ? "..." : eventMarkerCount}</span>
              <span className="metric-lbl">Earthquakes Shown</span>
            </div>
          </div>
          {lastSyncTime && (
            <p className="heatmap-sync-time">
              Catalog synced: {new Date(lastSyncTime).toLocaleString()}
            </p>
          )}
          </div>}
        </aside>
      )}

      {/* Bottom Coordinates Chip */}
      <footer className="map-bottom-bar">
        <div className="coord-chip">
          <span>Lat: {viewportInfo.lat}°</span>
          <span>Lng: {viewportInfo.lng}°</span>
          <span>Zoom: {viewportInfo.zoom}</span>
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
