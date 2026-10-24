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
