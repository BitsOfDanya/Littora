"use client";

import { type ReactNode, useMemo } from "react";
import { MapProvider } from "react-map-gl/maplibre";
import { findAoi } from "@/config/aois";
import { findBasemap } from "@/config/basemaps";
import { EntryGate } from "@/features/gate/entry-gate";
import { GateAnnouncer, GateInert, GateMapSettle } from "@/features/gate/gate-stage";
import { MapStage } from "@/features/map/map-stage";
import { useMapLayersStore } from "@/state/map-layers-store";
import { usePreferencesStore } from "@/state/preferences-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { ThemeSync } from "./theme-sync";

export function StageRoot({ children }: { children: ReactNode }) {
  const aoi = findAoi(useWorkspaceStore.getState().aoiId);
  const basemapId = useMapLayersStore((state) => state.basemapId);
  const theme = usePreferencesStore((state) => state.theme);
  const mapStyle = useMemo(() => findBasemap(basemapId).style(theme), [basemapId, theme]);

  return (
    <MapProvider>
      <ThemeSync />
      <main className="relative h-dvh w-full overflow-clip bg-surface-app">
        <GateMapSettle>
          {aoi ? (
            <MapStage mapStyle={mapStyle} initialCenter={aoi.center} initialZoom={aoi.zoom} />
          ) : null}
        </GateMapSettle>
        <GateInert>{children}</GateInert>
        <EntryGate />
        <GateAnnouncer />
      </main>
    </MapProvider>
  );
}
