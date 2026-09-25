"use client";

import { usePathname } from "next/navigation";
import { isMapMode, type MapModeId } from "@/config/layers";
import { findModeByPathname } from "@/config/modes";

export function useMapMode(): MapModeId | null {
  const mode = findModeByPathname(usePathname())?.id;
  return mode && isMapMode(mode) ? mode : null;
}
