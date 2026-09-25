"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { useMap } from "react-map-gl/maplibre";
import { MAIN_MAP_ID } from "./map-constants";

export function useMainMap(): MapLibreMap | undefined {
  return useMap()[MAIN_MAP_ID]?.getMap();
}
