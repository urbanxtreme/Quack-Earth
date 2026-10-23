import { useEffect, useRef, useState, useCallback } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import * as pmtiles from "pmtiles";
import { layers, namedFlavor } from "@protomaps/basemaps";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { FeatureCollection, Point } from "geojson";
import type { EarthquakeEvent } from "./api";

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

// Proxied through Vite dev server to guarantee 100% CORS & HTTP Range support
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

  // 1. Try local Vite proxy first
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
    // Fallback
  }

  // 3. Predefined coordinates dictionary fallback
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

export default function MapViewer({
  onBack,
  initialPlace,
  events = [],
  selectedEvent,
  onSelectEvent,
  onMapClick,
  targetCoords,
}: MapViewerProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const centerMarkerRef = useRef<maplibregl.Marker | null>(null);
  const clickMarkerRef = useRef<maplibregl.Marker | null>(null);
  const currentHeatmapDataRef = useRef<FeatureCollection | null>(null);

  const [mapLoaded, setMapLoaded] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTheme, setActiveTheme] = useState<"light" | "dark" | "grayscale">("dark");

  const [searchInput, setSearchInput] = useState<string>(initialPlace || "");
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [searchFeedback, setSearchFeedback] = useState<string | null>(null);
  const [activeLocation, setActiveLocation] = useState<GeocodedLocation | null>(null);
  const [heatmapStats, setHeatmapStats] = useState<HeatmapStats | null>(null);
  const [showEventsLayer, setShowEventsLayer] = useState<boolean>(true);
  const [showHeatmapLayer, setShowHeatmapLayer] = useState<boolean>(true);

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

      // Events outer glow / aura
      map.addLayer({
        id: "events-glow",
        type: "circle",
        source: "events-source",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["get", "mag"],
            2.0, 8,
            4.0, 14,
            6.0, 24,
            7.5, 36,
          ],
          "circle-color": [
            "step",
            ["get", "mag"],
            "rgba(56, 189, 248, 0.25)",
            4.0, "rgba(250, 204, 21, 0.35)",
            5.5, "rgba(251, 146, 60, 0.45)",
            6.5, "rgba(239, 68, 68, 0.55)",
          ],
          "circle-blur": 0.6,
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
              <span class="popup-tag">${props.source === "user_report" ? "Local Report" : "USGS"}</span>
            </div>`
          )
          .addTo(map);
      });

      // Cursor hover feedback
      map.on("mouseenter", "events-circles", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "events-circles", () => {
        map.getCanvas().style.cursor = "";
      });
    }
  }, [buildEventsGeoJSON, onSelectEvent]);

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

    map.addSource("heatmap-source", {
      type: "geojson",
      data: geojson,
    });

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
            <span class="popup-tag">Single Heatmap Focus</span>
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

        // Initial single heatmap center
        if (initialPlace) {
          handleGenerateHeatmap(initialPlace);
        } else {
          handleGenerateHeatmap("Tokyo");
        }

        // Render events
        if (events.length > 0) {
          updateEventsLayer(events);
        }
      });

      // Click on map to inspect coordinates or trigger risk evaluation
      map.on("click", (e) => {
        // Prevent if clicking on marker layer
        const features = map.queryRenderedFeatures(e.point, { layers: ["events-circles"] });
        if (features && features.length > 0) return;

        const coords = { lat: e.lngLat.lat, lon: e.lngLat.lng };
        if (onMapClick) {
          onMapClick(coords);
        }

        // Update click marker
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

      // Re-apply layers when style loads
      map.on("style.load", () => {
        if (currentHeatmapDataRef.current) {
          applyHeatmapLayer(currentHeatmapDataRef.current);
        }
        if (events.length > 0) {
          updateEventsLayer(events);
        }
      });

      const timeoutId = setTimeout(() => {
        setMapLoaded(true);
        if (mapRef.current) {
          mapRef.current.resize();
        }
      }, 2000);

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
        clearTimeout(timeoutId);
        window.removeEventListener("resize", handleResize);
        if (centerMarkerRef.current) centerMarkerRef.current.remove();
        if (clickMarkerRef.current) clickMarkerRef.current.remove();
        map.remove();
        mapRef.current = null;
        maplibregl.removeProtocol("pmtiles");
      };
    } catch (err: unknown) {
      console.error("Failed to initialize map:", err);
      setLoadError(err instanceof Error ? err.message : "Failed to initialize map");
    }
  }, []);

  // Sync events layer when events prop changes
  useEffect(() => {
    if (mapLoaded && mapRef.current) {
      updateEventsLayer(events);
    }
  }, [events, mapLoaded, updateEventsLayer]);

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

  // Toggle layer visibilities
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    if (map.getLayer("earthquake-heat")) {
      map.setLayoutProperty("earthquake-heat", "visibility", showHeatmapLayer ? "visible" : "none");
    }
  }, [showHeatmapLayer, mapLoaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    if (map.getLayer("events-circles")) {
      map.setLayoutProperty("events-circles", "visibility", showEventsLayer ? "visible" : "none");
    }
    if (map.getLayer("events-glow")) {
      map.setLayoutProperty("events-glow", "visibility", showEventsLayer ? "visible" : "none");
    }
  }, [showEventsLayer, mapLoaded]);

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
                {isSearching ? <span className="btn-spinner" /> : <span>Center Heatmap</span>}
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
          {/* Layer toggles */}
          <div className="layer-toggle-group">
            <button
              type="button"
              className={`layer-btn ${showHeatmapLayer ? "active" : ""}`}
              onClick={() => setShowHeatmapLayer((prev) => !prev)}
              title="Toggle Heatmap Layer"
            >
              🔥 Heatmap
            </button>
            <button
              type="button"
              className={`layer-btn ${showEventsLayer ? "active" : ""}`}
              onClick={() => setShowEventsLayer((prev) => !prev)}
              title="Toggle Earthquake Event Dots"
            >
              ⚡ Events ({events.length})
            </button>
          </div>

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
            Reset
          </button>
        </div>
      </header>

      {/* Heatmap Legend and Active Center Info Overlay */}
      {heatmapStats && (
        <aside className="heatmap-info-card">
          <div className="heatmap-info-header">
            <span className="heatmap-fire-icon">🔥</span>
            <div>
              <h3 className="heatmap-location-title">{heatmapStats.locationName}</h3>
              <p className="heatmap-coords">
                Center: {heatmapStats.centerLat.toFixed(3)}°, {heatmapStats.centerLon.toFixed(3)}°
              </p>
            </div>
          </div>

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
              <span className="metric-val">Auto</span>
              <span className="metric-lbl">Zoom Radius</span>
            </div>
          </div>
        </aside>
      )}

      {/* Bottom Coordinates & Hint Chip */}
      <footer className="map-bottom-bar">
        <div className="coord-chip">
          <span>Lat: {viewportInfo.lat}°</span>
          <span>Lng: {viewportInfo.lng}°</span>
          <span>Zoom: {viewportInfo.zoom}</span>
          <span className="click-hint">💡 Tip: Click anywhere to evaluate risk</span>
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
