import type { EarthquakeEvent } from "./api";

export type ShockRole = "mainshock" | "aftershock" | "foreshock";

/** Largest shock is the mainshock. A later shock within 1.0 magnitude, at M7 or above, is a doublet mainshock. */
export function shockRole(event: EarthquakeEvent, events: EarthquakeEvent[]): ShockRole {
  if (events.length === 0) return "mainshock";
  const peak = events.reduce((best, item) => (item.magnitude > best.magnitude ? item : best));
  if (event.id === peak.id) return "mainshock";
  const peakTime = new Date(peak.time).getTime();
  const eventTime = new Date(event.time).getTime();
  if (event.magnitude >= peak.magnitude - 1 && event.magnitude >= 7) return "mainshock";
  if (eventTime < peakTime) return "foreshock";
  return "aftershock";
}

export function shockLabel(role: ShockRole): string {
  if (role === "mainshock") return "Mainshock";
  if (role === "foreshock") return "Foreshock";
  return "Aftershock";
}

const IMPACT_MAGNITUDE = 5;
const DAY_MS = 24 * 60 * 60 * 1000;

function distanceKm(a: EarthquakeEvent, b: EarthquakeEvent): number {
  const dy = (a.lat - b.lat) * 111.32;
  const dx = (a.lon - b.lon) * 111.32 * Math.cos(((a.lat + b.lat) / 2) * (Math.PI / 180));
  return Math.hypot(dx, dy);
}

/** Search radius grows with the mainshock, and stays at least 50 km. */
export function impactRadiusKm(magnitude: number): number {
  return Math.max(50, 10 ** (0.5 * magnitude - 1.5));
}

/**
 * The active impact, if the loaded catalog has one.
 * The largest shock of magnitude 5 or above is the anchor. Quakes within its
 * radius, from 3 days before to 14 days after, are its foreshocks and aftershocks.
 * A distant quake is left out, so a global live feed is not one sequence.
 */
export function impactSequence(events: EarthquakeEvent[]): EarthquakeEvent[] {
  const anchors = events.filter((event) => event.magnitude >= IMPACT_MAGNITUDE);
  if (anchors.length === 0) return [];

  let best: EarthquakeEvent[] = [];
  const ranked = [...anchors].sort((a, b) => b.magnitude - a.magnitude || a.time.localeCompare(b.time));
  for (const anchor of ranked) {
    const radius = impactRadiusKm(anchor.magnitude);
    const origin = new Date(anchor.time).getTime();
    const members = events.filter((event) => {
      const deltaDays = (new Date(event.time).getTime() - origin) / DAY_MS;
      if (deltaDays < -3 || deltaDays > 14) return false;
      return distanceKm(event, anchor) <= radius;
    });
    const bestPeak = best.reduce((max, event) => Math.max(max, event.magnitude), 0);
    if (members.length > best.length || (members.length === best.length && anchor.magnitude > bestPeak)) {
      best = members;
    }
  }
  return best;
}
