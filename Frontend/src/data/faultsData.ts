import type { FeatureCollection, LineString } from "geojson";

export const FALLBACK_FAULTS_GEOJSON: FeatureCollection<LineString> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: "fault-eafz-pazarcik",
      geometry: {
        type: "LineString",
        coordinates: [
          [36.35, 36.65],
          [36.85, 37.05],
          [37.25, 37.45],
          [37.85, 37.95],
          [38.45, 38.35],
        ],
      },
      properties: {
        name: "East Anatolian Fault - Pazarcık & Amanos Segments",
        type: "left-lateral strike-slip",
        region: "Turkey / Middle East",
        slip_rate_mm_yr: 10.0,
        confidence: "verified_active",
        rupture_history: "2023-02-06 M7.8 Kahramanmaraş mainshock rupture plane",
      },
    },
    {
      type: "Feature",
      id: "fault-cardak-surugu",
      geometry: {
        type: "LineString",
        coordinates: [
          [36.40, 38.00],
          [36.95, 38.05],
          [37.45, 38.10],
          [37.90, 38.02],
          [38.30, 37.95],
        ],
      },
      properties: {
        name: "Çardak - Sürgü Fault Zone",
        type: "left-lateral strike-slip",
        region: "Turkey",
        slip_rate_mm_yr: 4.5,
        confidence: "verified_active",
        rupture_history: "2023-02-06 M7.5 Ekinözü doublet rupture plane",
      },
    },
    {
      type: "Feature",
      id: "fault-dead-sea-transform",
      geometry: {
        type: "LineString",
        coordinates: [
          [35.00, 29.50],
          [35.40, 31.00],
          [35.60, 32.50],
          [36.00, 34.50],
          [36.20, 36.20],
        ],
      },
      properties: {
        name: "Dead Sea Transform (DST) Fault System",
        type: "left-lateral strike-slip",
        region: "Levant / Middle East",
        slip_rate_mm_yr: 4.0,
        confidence: "verified_active",
        rupture_history: "Major historical plate boundary rupture zone",
      },
    },
    {
      type: "Feature",
      id: "fault-nafz-marmara",
      geometry: {
        type: "LineString",
        coordinates: [
          [26.50, 40.50],
          [28.50, 40.80],
          [29.50, 40.75],
          [31.00, 40.85],
          [34.50, 41.00],
          [39.50, 40.00],
        ],
      },
      properties: {
        name: "North Anatolian Fault Zone (NAFZ)",
        type: "right-lateral strike-slip",
        region: "Turkey / Marmara",
        slip_rate_mm_yr: 24.0,
        confidence: "verified_active",
        rupture_history: "1999 İzmit M7.6 and ongoing seismic gap risk",
      },
    },
    {
      type: "Feature",
      id: "fault-san-andreas-central",
      geometry: {
        type: "LineString",
        coordinates: [
          [-124.00, 40.00],
          [-122.50, 37.75],
          [-121.00, 36.50],
          [-119.50, 35.00],
          [-117.50, 34.00],
          [-115.50, 33.00],
        ],
      },
      properties: {
        name: "San Andreas Fault System (SAF)",
        type: "right-lateral strike-slip",
        region: "California, USA",
        slip_rate_mm_yr: 30.0,
        confidence: "verified_active",
        rupture_history: "1906 San Francisco M7.9, 1857 Fort Tejon M7.9",
      },
    },
    {
      type: "Feature",
      id: "fault-japan-trench",
      geometry: {
        type: "LineString",
        coordinates: [
          [143.50, 41.00],
          [143.80, 39.50],
          [143.50, 38.00],
          [142.50, 36.00],
          [141.50, 34.50],
        ],
      },
      properties: {
        name: "Japan Trench Subduction Megathrust",
        type: "subduction megathrust",
        region: "Northeast Japan",
        slip_rate_mm_yr: 80.0,
        confidence: "verified_active",
        rupture_history: "2011 Tohoku-Oki M9.1 megathrust rupture plane",
      },
    },
    {
      type: "Feature",
      id: "fault-tokyo-sagami-trough",
      geometry: {
        type: "LineString",
        coordinates: [
          [139.10, 35.10],
          [139.50, 35.25],
          [139.90, 35.40],
          [140.40, 35.10],
        ],
      },
      properties: {
        name: "Sagami Trough & Tokyo Bay Fault System",
        type: "oblique subduction / thrust",
        region: "Kanto / Tokyo, Japan",
        slip_rate_mm_yr: 30.0,
        confidence: "verified_active",
        rupture_history: "1923 Great Kanto M7.9 earthquake",
      },
    },
  ],
};
