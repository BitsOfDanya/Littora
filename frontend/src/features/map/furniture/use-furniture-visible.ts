"use client";

import { usePathname } from "next/navigation";
import { findModeByPathname } from "@/config/modes";

export function useMapFurnitureVisible(): boolean {
  const mode = findModeByPathname(usePathname() ?? "");
  return mode !== undefined && mode.id !== "models";
}
