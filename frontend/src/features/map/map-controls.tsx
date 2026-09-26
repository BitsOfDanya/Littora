"use client";

import type { ReactNode } from "react";
import { findAoi } from "@/config/aois";
import { useHotkey } from "@/features/shell/hotkeys";
import { useLayerVisible, useMapLayersStore } from "@/state/map-layers-store";
import { useShellUiStore } from "@/state/shell-ui-store";
import { useWorkspaceStore } from "@/state/workspace-store";
import { IconButton } from "@/ui/button";
import { cn } from "@/ui/cn";
import {
  IconFitArea,
  IconGraticule,
  IconLayers,
  IconMinus,
  IconNorth,
  IconPlus,
  IconProbe,
  IconRuler,
} from "@/ui/icons";
import { Tooltip } from "@/ui/tooltip";
import { fitAoi } from "./camera";
import { resetNorth, zoomBy } from "./camera-motion";
import { useIsPhoneWidth } from "./furniture/use-frame-width";
import { useMapFurnitureVisible } from "./furniture/use-furniture-visible";
import { usePixelProbeStore } from "./probe/pixel-probe";
import { useRulerStore } from "./ruler/ruler-store";
import { useMapViewStore } from "./state/map-view-store";
import { useMainMap } from "./use-main-map";

type ToolProps = {
  label: string;
  shortcut?: string;
  ariaKeys?: string;
  large: boolean;
  pressed?: boolean;
  plannedReason?: string;
  onPress?: () => void;
  children: ReactNode;
};

function Tool({
  label,
  shortcut,
  ariaKeys,
  large,
  pressed,
  plannedReason,
  onPress,
  children,
}: ToolProps) {
  const planned = plannedReason !== undefined;
  return (
    <Tooltip
      content={planned ? `${label} — ${plannedReason}` : label}
      shortcut={large ? undefined : shortcut}
      side="left"
    >
      <IconButton
        label={label}
        title={undefined}
        size={large ? "lg" : "md"}
        pressed={pressed}
        aria-keyshortcuts={ariaKeys ?? shortcut}
        aria-disabled={planned || undefined}
        onClick={planned ? undefined : onPress}
        className={cn(
          "rounded-none border-0",
          planned &&
            "cursor-not-allowed border border-dashed border-line-control text-text-disabled hover:bg-surface-panel hover:text-text-disabled",
        )}
      >
        {children}
      </IconButton>
    </Tooltip>
  );
}

function ToolGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      role="group"
      aria-label={label}
      className="flex flex-col divide-y divide-line-hairline border border-line-control bg-surface-panel"
    >
      {children}
    </div>
  );
}

function useMapToolActions() {
  const map = useMainMap();
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const toggleLayer = useMapLayersStore((state) => state.toggleLayer);
  const toggleRuler = useRulerStore((state) => state.toggle);
  const deactivateRuler = useRulerStore((state) => state.deactivate);
  const toggleProbe = usePixelProbeStore((state) => state.toggle);
  const setProbe = usePixelProbeStore((state) => state.setActive);
  return {
    zoomIn: () => map && zoomBy(map, 1),
    zoomOut: () => map && zoomBy(map, -1),
    fitArea: () => {
      const aoi = findAoi(aoiId);
      if (map && aoi) fitAoi(map, aoi);
    },
    northUp: () => map && resetNorth(map),
    toggleGraticule: () => toggleLayer("graticule"),
    toggleRuler: () => {
      setProbe(false);
      toggleRuler();
    },
    toggleProbe: () => {
      deactivateRuler();
      toggleProbe();
    },
  };
}

function useMapToolHotkeys(actions: ReturnType<typeof useMapToolActions>, enabled: boolean): void {
  useHotkey(["Equal", "NumpadAdd"], actions.zoomIn, { enabled });
  useHotkey("Equal", actions.zoomIn, { enabled, shift: true });
  useHotkey(["Minus", "NumpadSubtract"], actions.zoomOut, { enabled });
  useHotkey("KeyF", actions.fitArea, { enabled });
  useHotkey("KeyN", actions.northUp, { enabled });
  useHotkey("KeyG", actions.toggleGraticule, { enabled });
  useHotkey("KeyR", actions.toggleRuler, { enabled });
  useHotkey("KeyI", actions.toggleProbe, { enabled });
}

type MapControlsProps = {
  onOpenLayers?: () => void;
};

export function MapControls({ onOpenLayers }: MapControlsProps) {
  const visible = useMapFurnitureVisible();
  const phone = useIsPhoneWidth();
  const bearing = useMapViewStore((state) => state.bearing);
  const graticuleOn = useLayerVisible("graticule");
  const rulerOn = useRulerStore((state) => state.active);
  const probeOn = usePixelProbeStore((state) => state.active);
  const actions = useMapToolActions();
  const modalOpen = useShellUiStore((state) => state.shortcutSheetOpen);

  useMapToolHotkeys(actions, visible && !modalOpen);

  if (!visible) return null;

  return (
    <div
      role="toolbar"
      aria-label="Инструменты карты"
      aria-orientation="vertical"
      className="pointer-events-auto flex flex-col gap-2"
    >
      {phone ? (
        <ToolGroup label="Слои">
          <Tool
            label="Слои"
            large
            onPress={onOpenLayers}
            plannedReason={onOpenLayers ? undefined : "панель слоёв появится в нижнем листе"}
          >
            <IconLayers size={20} />
          </Tool>
        </ToolGroup>
      ) : null}
      <ToolGroup label="Масштаб">
        <Tool label="Приблизить" shortcut="+" ariaKeys="+" large={phone} onPress={actions.zoomIn}>
          <IconPlus size={phone ? 20 : 16} />
        </Tool>
        <Tool label="Отдалить" shortcut="−" ariaKeys="-" large={phone} onPress={actions.zoomOut}>
          <IconMinus size={phone ? 20 : 16} />
        </Tool>
      </ToolGroup>
      <ToolGroup label="Вид">
        <Tool label="Показать район" shortcut="F" large={phone} onPress={actions.fitArea}>
          <IconFitArea size={phone ? 20 : 16} />
        </Tool>
        <Tool label="Север вверх" shortcut="N" large={phone} onPress={actions.northUp}>
          <IconNorth size={phone ? 20 : 16} style={{ transform: `rotate(${-bearing}deg)` }} />
        </Tool>
      </ToolGroup>
      {phone ? null : (
        <ToolGroup label="Инструменты">
          <Tool
            label="Сетка и рамка"
            shortcut="G"
            large={false}
            pressed={graticuleOn}
            onPress={actions.toggleGraticule}
          >
            <IconGraticule />
          </Tool>
          <Tool
            label="Лупа: значения пикселя"
            shortcut="I"
            large={false}
            pressed={probeOn}
            onPress={actions.toggleProbe}
          >
            <IconProbe />
          </Tool>
          <Tool
            label="Линейка"
            shortcut="R"
            large={false}
            pressed={rulerOn}
            onPress={actions.toggleRuler}
          >
            <IconRuler />
          </Tool>
        </ToolGroup>
      )}
    </div>
  );
}
