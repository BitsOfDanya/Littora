import type { LngLat } from "@/domain/geo";
import { formatNumber } from "./numbers";

export type CoordinateFormat = "dd" | "dm" | "dms";

const HEMISPHERES = {
  lat: { positive: "с. ш.", negative: "ю. ш." },
  lng: { positive: "в. д.", negative: "з. д." },
} as const;

function hemisphere(axis: keyof typeof HEMISPHERES, value: number): string {
  return value >= 0 ? HEMISPHERES[axis].positive : HEMISPHERES[axis].negative;
}

function formatAxis(
  axis: keyof typeof HEMISPHERES,
  value: number,
  format: CoordinateFormat,
): string {
  const absolute = Math.abs(value);
  const suffix = hemisphere(axis, value);
  if (format === "dd") return `${formatNumber(absolute, 4)}° ${suffix}`;
  const degrees = Math.floor(absolute);
  const minutesTotal = (absolute - degrees) * 60;
  if (format === "dm")
    return `${degrees}°${formatNumber(minutesTotal, 2).padStart(5, "0")}′ ${suffix}`;
  const minutes = Math.floor(minutesTotal);
  const seconds = (minutesTotal - minutes) * 60;
  return `${degrees}°${String(minutes).padStart(2, "0")}′${formatNumber(seconds, 1).padStart(4, "0")}″ ${suffix}`;
}

export function formatLatitude(lat: number, format: CoordinateFormat = "dd"): string {
  return formatAxis("lat", lat, format);
}

export function formatLongitude(lng: number, format: CoordinateFormat = "dd"): string {
  return formatAxis("lng", lng, format);
}

export function formatLngLat([lng, lat]: LngLat, format: CoordinateFormat = "dd"): string {
  return `${formatLatitude(lat, format)}  ${formatLongitude(lng, format)}`;
}
