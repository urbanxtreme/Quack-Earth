import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import * as pmtiles from "pmtiles";
import { layers, namedFlavor } from "@protomaps/basemaps";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { FeatureCollection, Point } from "geojson";
import type { EarthquakeEvent } from "./api";
import { shockLabel, shockRole } from "./shockRole";

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
  onSyncSuccess,
  activeScenarioId = "live_usgs",
}: MapViewerProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const centerMarkerRef = useRef<maplibregl.Marker | null>(null);
  const clickMarkerRef = useRef<maplibregl.Marker | null>(null);
  const shockMarkersRef = useRef<maplibregl.Marker[]>([]);
  const displayedEventsRef = useRef<EarthquakeEvent[]>([]);
  const catalogEventsRef = useRef<EarthquakeEvent[]>([]);
  const onSelectEventRef = useRef(onSelectEvent);
  onSelectEventRef.current = onSelectEvent;
  const currentHeatmapDataRef = useRef<FeatureCollection | null>(null);

  const [mapLoaded, setMapLoaded] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTheme, setActiveTheme] = useState<"light" | "dark" | "grayscale">("dark");

  const [searchInput, setSearchInput] = useState<string>(initialPlace || "");
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [searchFeedback, setSearchFeedback] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null);
  const [heatmapStats, setHeatmapStats] = useState<HeatmapStats | null>(null);

  // Timeline Scrubbing state
  const [timelinePercent, setTimelinePercent] = useState<number>(100);
  const [isPlayingTimeline, setIsPlayingTimeline] = useState<boolean>(false);

  // Chronologically sorted events
  const sortedEvents = useMemo(() => {
    return [...events].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
  }, [events]);

  // Events filtered by scrubber position
  const displayedEvents = useMemo(() => {
    if (timelinePercent >= 100 || sortedEvents.length <= 1) {
      return sortedEvents;
    }
    const tMin = new Date(sortedEvents[0].time).getTime();
    const tMax = new Date(sortedEvents[sortedEvents.length - 1].time).getTime();
    if (tMax <= tMin) return sortedEvents;
    const cutoff = tMin + (tMax - tMin) * (timelinePercent / 100);
    return sortedEvents.filter((e) => new Date(e.time).getTime() <= cutoff);
  }, [sortedEvents, timelinePercent]);

  displayedEventsRef.current = displayedEvents;
  catalogEventsRef.current = events;

  const isSimulation = activeScenarioId !== "live_usgs";
  const aftershockCount = useMemo(
    () => events.filter((event) => shockRole(event, events) === "aftershock").length,
    [events],
  );

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
  const [showEventsLayer, setShowEventsLayer] = useState<boolean>(true);
  const [showHeatmapLayer, setShowHeatmapLayer] = useState<boolean>(true);
  const [isLegendExpanded, setIsLegendExpanded] = useState<boolean>(true);

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

        const wanted = String(props.id ?? "");
        const foundEvent = displayedEventsRef.current.find((ev) => ev.id === wanted);
        if (foundEvent && onSelectEvent) {
          onSelectEvent(foundEvent);
        }
        const role = foundEvent ? shockRole(foundEvent, catalogEventsRef.current) : "mainshock";
        const roleName = shockLabel(role);

        new maplibregl.Popup({ offset: 15 })
          .setLngLat([coords[0], coords[1]])
          .setHTML(
            `<div class="${role === "aftershock" ? "aftershock-popup" : "epicenter-popup"}">
              <h4>${roleName} M ${props.mag}</h4>
              <p>${props.place}</p>
              <p><strong>Depth:</strong> ${props.depth} km</p>
              <p><strong>Time:</strong> ${new Date(props.time).toLocaleString()}</p>
              <span class="popup-tag ${role}-tag">${roleName}</span>
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

    const beforeLayerId = map.getLayer("events-glow") ? "events-glow" : undefined;
    map.addLayer(
      {
        id: "earthquake-heat",
        type: "heatmap",
        source: "heatmap-source",
        paint: {
          "heatmap-weight": [
            "interpolate",
            ["linear"],
            ["coalesce", ["get", "mag"], 4],
            2, 0.5,
            5, 1.0,
            7.5, 2.0,
          ],
          "heatmap-intensity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            1, 0.7,
            5, 1.0,
            9, 1.3,
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
            1, 2,
            3, 8,
            5, 32,
            7, 128,
            9, 320,
            12, 500,
          ],
          "heatmap-opacity": 0.82,
        },
      },
      beforeLayerId
    );
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

      // setActiveLocation(location);

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

      // Generate heatmap directly from real live earthquake events from USGS
      const geojson = buildEventsGeoJSON(events);
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

        // Initial single heatmap center if specified
        if (initialPlace) {
          handleGenerateHeatmap(initialPlace);
        }

        // Render events
        if (events.length > 0) {
          updateEventsLayer(events);
        }
      });

      // Click on map to inspect coordinates or trigger risk evaluation
      map.on("click", (e) => {
        // Prevent if clicking on marker layer
        if (map.getLayer("events-circles")) {
          const features = map.queryRenderedFeatures(e.point, { layers: ["events-circles"] });
          if (features && features.length > 0) return;
        }

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
  }, [activeTheme, applyHeatmapLayer, handleGenerateHeatmap, initialPlace]);

  // Sync events and heatmap layer when displayedEvents changes
  useEffect(() => {
    if (mapLoaded && mapRef.current) {
      updateEventsLayer(displayedEvents);
      if (displayedEvents.length > 0) {
        applyHeatmapLayer(buildEventsGeoJSON(displayedEvents));
      }
    }
  }, [displayedEvents, mapLoaded, updateEventsLayer, applyHeatmapLayer, buildEventsGeoJSON]);

  // Keep the scrubber at the end when a new simulation is chosen, so every aftershock is on the map.
  useEffect(() => {
    setTimelinePercent(100);
    setIsPlayingTimeline(false);
  }, [activeScenarioId]);

  // Choosing one shock later in the sequence reveals it instead of leaving it behind the scrubber.
  useEffect(() => {
    if (!selectedEvent || sortedEvents.length < 2) return;
    const tMin = new Date(sortedEvents[0].time).getTime();
    const tMax = new Date(sortedEvents[sortedEvents.length - 1].time).getTime();
    if (tMax <= tMin) return;
    const ratio = (new Date(selectedEvent.time).getTime() - tMin) / (tMax - tMin);
    const needed = Math.min(100, Math.max(0, ratio * 100));
    setTimelinePercent((prev) => (prev < needed ? needed : prev));
  }, [selectedEvent, sortedEvents]);

  // Frame the whole simulation sequence once, so later aftershocks are inside the view.
  const sequenceKey = isSimulation ? events.map((event) => event.id).join("|") : "";
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !sequenceKey) return;
    const bounds = new maplibregl.LngLatBounds();
    events.forEach((event) => bounds.extend([event.lon, event.lat]));
    if (bounds.isEmpty()) return;
    map.fitBounds(bounds, { padding: 90, maxZoom: 8, duration: 800 });
  }, [sequenceKey, mapLoaded, events]);

  // Draw one labeled marker per shock in a simulation. The selected aftershock stays open.
  useEffect(() => {
    const map = mapRef.current;
    shockMarkersRef.current.forEach((marker) => marker.remove());
    shockMarkersRef.current = [];
    if (!map || !mapLoaded || !isSimulation) return;

    const visible = [...displayedEvents];
    if (selectedEvent && !visible.some((event) => event.id === selectedEvent.id)) {
      visible.push(selectedEvent);
    }

    visible.forEach((event) => {
      const role = shockRole(event, events);
      const selected = selectedEvent?.id === event.id;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `shock-marker role-${role}${selected ? " is-selected" : ""}`;
      button.dataset.shockId = event.id;
      button.dataset.shockRole = role;
      button.setAttribute("aria-label", `${shockLabel(role)} magnitude ${event.magnitude.toFixed(1)}`);
      button.innerHTML = `<span class="shock-mag">${event.magnitude.toFixed(1)}</span>`;
      button.addEventListener("click", (clickEvent) => {
        clickEvent.stopPropagation();
        onSelectEventRef.current?.(event);
      });

      const popup = new maplibregl.Popup({ offset: 18, closeButton: true }).setHTML(
        `<div class="${role}-popup">
          <h4>${shockLabel(role)} M${event.magnitude.toFixed(1)}</h4>
          <p>${event.place || "Simulation sequence"}</p>
          <p><strong>Time:</strong> ${new Date(event.time).toLocaleString()}</p>
          <span class="popup-tag ${role}-tag">${shockLabel(role)} in this simulation</span>
        </div>`
      );
      const marker = new maplibregl.Marker({ element: button, anchor: "center" })
        .setLngLat([event.lon, event.lat])
        .setPopup(popup)
        .addTo(map);
      if (selected) marker.togglePopup();
      shockMarkersRef.current.push(marker);
    });
  }, [displayedEvents, selectedEvent, mapLoaded, isSimulation, events]);

  const lastFlownEventId = useRef<string | null>(null);
  useEffect(() => {
    lastFlownEventId.current = null;
  }, [activeScenarioId]);

  // Fly to a shock the user picked. The first selection in a simulation is framed by fitBounds instead.
  useEffect(() => {
    if (!selectedEvent || !mapRef.current || !mapLoaded) return;
    if (isSimulation && lastFlownEventId.current === null) {
      lastFlownEventId.current = selectedEvent.id;
      return;
    }
    if (lastFlownEventId.current === selectedEvent.id) return;
    lastFlownEventId.current = selectedEvent.id;
    mapRef.current.flyTo({
      center: [selectedEvent.lon, selectedEvent.lat],
      zoom: isSimulation ? 8.2 : 7.0,
      speed: 1.5,
      curve: 1.3,
      essential: true,
    });
  }, [selectedEvent, mapLoaded, isSimulation, activeScenarioId]);

  // Sync external target coordinates
  useEffect(() => {
    if (targetCoords && mapRef.current) {
      const coveredByShock =
        isSimulation &&
        selectedEvent &&
        Math.abs(selectedEvent.lat - targetCoords.lat) < 0.02 &&
        Math.abs(selectedEvent.lon - targetCoords.lon) < 0.02;
      if (coveredByShock) {
        if (clickMarkerRef.current) {
          clickMarkerRef.current.remove();
          clickMarkerRef.current = null;
        }
        return;
      }
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
  }, [targetCoords, selectedEvent, isSimulation]);

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
        status?: string;
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

      if (onSyncSuccess) {
        onSyncSuccess();
      }
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

  // const presetPlaces = ["Turkey", "Tokyo", "San Francisco", "Chile", "Nepal", "Kochi"];

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
                placeholder="Enter place name"
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
              {/* <button
                type="submit"
                className="btn-search-submit"
                disabled={isSearching || !searchInput.trim()}
                id="generate-heatmap-button"
              >
                {isSearching ? <span className="btn-spinner" /> : <span>🔍</span>}
              </button> */}
            </div>
          </form>

          {/* Quick Presets */}
          {/* <div className="search-presets">
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
          </div> */}

          {/* Live Feedback Toast */}
          {searchFeedback && (
            <div className="search-feedback-toast">
              <span>{searchFeedback}</span>
            </div>
          )}
        </div>

        <div className="map-top-right">
          {/* Mainshock Selector Dropdown */}
          {/* <div className="mainshock-selector-group">
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
                {effectiveMainshock ? `★ Mainshock: M${effectiveMainshock.magnitude.toFixed(1)} (${effectiveMainshock.place?.slice(0, 18)}...)` : "-- Select Real USGS Earthquake --"}
              </option>
              {events
                .filter((ev) => ev.magnitude >= 4.0)
                .sort((a, b) => b.magnitude - a.magnitude)
                .map((ev) => (
                  <option key={ev.id} value={ev.id}>
                    {ev.source === "user_report" ? "[Local]" : "[USGS]"} M{ev.magnitude.toFixed(1)} - {ev.place?.slice(0, 26) || ev.id}
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
          </div> */}

          {/* Forecast Horizon Window Toggle */}
          {/* <div className="forecast-window-selector">
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
          </div> */}

          {/* Minimum Magnitude Slider */}
          {/* <div className="mag-toolbar-slider">
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
          </div> */}

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
            Reset View
          </button>
          <button
            className="btn-sync"
            onClick={() => void handleSyncCatalog()}
            disabled={isSyncing}
            title="Download live earthquake catalog from USGS"
          >
            {isSyncing ? <span className="btn-spinner" /> : "↻"}{" "}
            {isSyncing ? "Syncing..." : "Sync USGS"}
          </button>
        </div>
      </header>

      {/* Heatmap Legend and Active Center Info Overlay */}
      {heatmapStats && (
        <aside className={`heatmap-info-card ${!isLegendExpanded ? "minimized" : ""}`}>
          <div
            className="heatmap-info-header"
            onClick={() => setIsLegendExpanded((prev) => !prev)}
            role="button"
            tabIndex={0}
            title={isLegendExpanded ? "Click to minimize card" : "Click to expand card"}
          >
            <span className="heatmap-fire-icon">🔥</span>
            <div className="heatmap-header-titles">
              <h3 className="heatmap-location-title">{heatmapStats.locationName}</h3>
              <p className="heatmap-coords">
                {heatmapStats.centerLat.toFixed(3)}°, {heatmapStats.centerLon.toFixed(3)}°
              </p>
            </div>
            <button
              type="button"
              className="card-collapse-btn"
              aria-label={isLegendExpanded ? "Minimize card" : "Expand card"}
            >
              {isLegendExpanded ? "▾" : "▴"}
            </button>
          </div>

          {isLegendExpanded && (
            <>
              <div className="heatmap-legend">
                <div className="legend-label-row">
                  <span>Low</span>
                  <span>Thermal Intensity</span>
                  <span>High</span>
                </div>
                <div className="legend-gradient-bar" />
              </div>

              <div className="heatmap-metrics-row">
                <div className="metric-item">
                  <span className="metric-val">1 Center</span>
                  <span className="metric-lbl">Epicenter</span>
                </div>
                <div className="metric-item">
                  <span className="metric-val">Radial</span>
                  <span className="metric-lbl">Gradient</span>
                </div>
                <div className="metric-item">
                  <span className="metric-val">{events.length}</span>
                  <span className="metric-lbl">Earthquakes</span>
                </div>
              </div>
              {lastSyncTime && (
                <p className="heatmap-sync-time">
                  Catalog synced: {new Date(lastSyncTime).toLocaleTimeString()}
                </p>
              )}
            </>
          )}
        </aside>
      )}

      {/* Unified Mission-Control Timeline & Telemetry Console */}
      <footer className="timeline-scrubber-bar mission-control-console">
        {/* Top Control & Telemetry Row */}
        <div className="timeline-dock-header">
          {/* Left: Playback Controls */}
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
              ⚡ <strong className="text-cyan">{displayedEvents.length}</strong> of {sortedEvents.length} shocks
              {isSimulation && (
                <span className="timeline-pct-tag">{aftershockCount} aftershocks in this sequence</span>
              )}
              <span className="timeline-pct-tag">({timelinePercent.toFixed(0)}%)</span>
            </span>
          </div>

          {/* Right: Viewport Coordinates & Hint */}
          <div className="timeline-dock-coords font-mono">
            <span className="dock-coord-val">{viewportInfo.lat}°N, {viewportInfo.lng}°E</span>
            <span className="dock-zoom-badge">z{viewportInfo.zoom}</span>
            <span className="dock-tip-pill" title="Click anywhere on the map to evaluate site-specific seismic hazard">
              <span className="click-hint-full">💡 Click map for risk</span>
              <span className="click-hint-short">💡 Click for risk</span>
            </span>
          </div>
        </div>

        {/* Bottom: Sequence Range Track */}
        <div className="timeline-slider-container">
          <div className="timeline-slider-track-row">
            <span className="timeline-edge-label font-mono">T-0 (Sequence Start)</span>
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
