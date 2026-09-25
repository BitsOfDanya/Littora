"use client";

import { type ReactNode, useRef } from "react";
import type { WorkspaceModeId } from "@/config/modes";
import { useViewportPadding } from "@/features/map/use-viewport-padding";
import { useSystemEventsWatcher } from "@/features/system/system-events";
import { useLayerVisible } from "@/state/map-layers-store";
import { ShortcutSheet } from "./keyboard/shortcut-sheet";
import { useGlobalHotkeys } from "./keyboard/use-global-hotkeys";
import { InspectorDock } from "./layout/inspector-dock";
import { RailFrame } from "./layout/rail-frame";
import { type ShellLayout, useShellLayout } from "./layout/use-environment";
import { Viewport } from "./layout/viewport";
import { useActiveMode } from "./orientation/modes";
import { useDefaultFit } from "./orientation/use-default-fit";
import { useDemoArea } from "./orientation/use-demo-area";
import { useDocumentTitle } from "./orientation/use-document-title";
import { useSelectionFocus } from "./orientation/use-selection-focus";
import { useUrlSync } from "./orientation/use-url-sync";
import { useQueueToggle } from "./queue/use-queue";
import { ShellSlotsProvider, useRegionOccupied, useRegionTarget } from "./shell-slots";
import { StatusBar } from "./status/status-bar";
import { ModeTabBar, ModeTabs } from "./top-bar/mode-tabs";
import { TopBar } from "./top-bar/top-bar";
import styles from "./workspace-shell.module.css";

const PHONE_TOOLS_INSET = { right: 56 } as const;
const NO_MINIMUM = {} as const;

function useShellEffects(layout: ShellLayout, modeId: WorkspaceModeId | undefined) {
  useGlobalHotkeys({ onToggleQueue: useQueueToggle(modeId, layout) });
  useUrlSync();
  useDocumentTitle();
  useDefaultFit();
  useDemoArea();
  useSystemEventsWatcher();
}

function SideRegion() {
  const registerTarget = useRegionTarget("side");
  const occupied = useRegionOccupied("side");
  return (
    <aside
      ref={registerTarget}
      aria-label="Боковая панель"
      data-occupied={occupied}
      className={styles.side}
    />
  );
}

function StepperRegion({ hidden }: { hidden: boolean }) {
  const registerTarget = useRegionTarget("stepper");
  const occupied = useRegionOccupied("stepper");
  return (
    <div
      ref={registerTarget}
      role="region"
      aria-label="Шаг по времени"
      data-empty={hidden || !occupied}
      className={styles.stepper}
    />
  );
}

function ShellLayoutView() {
  const viewportRef = useRef<HTMLDivElement>(null);
  const layout = useShellLayout();
  const modeId = useActiveMode()?.id;
  const isPhone = layout === "phone";
  const frameVisible = useLayerVisible("graticule");

  useViewportPadding(viewportRef, {
    minimum: isPhone ? PHONE_TOOLS_INSET : NO_MINIMUM,
    keepVisible: useSelectionFocus(),
  });
  useShellEffects(layout, modeId);

  return (
    <div className={styles.root} data-mode={modeId} data-frame={frameVisible ? "on" : "off"}>
      <div className={styles.top}>
        <TopBar />
      </div>
      <div className={styles.modes}>
        <ModeTabs variant="row" />
      </div>
      <SideRegion />
      <Viewport viewportRef={viewportRef} mode={modeId} layout={layout} />
      {isPhone ? null : (
        <InspectorDock modeKey={modeId} placement={layout === "tablet" ? "row" : "column"} />
      )}
      {isPhone ? null : <RailFrame mode={modeId} layout={layout} />}
      {isPhone ? null : (
        <div className={styles.status}>
          <StatusBar />
        </div>
      )}
      {isPhone ? <StepperRegion hidden={modeId === "models"} /> : null}
      {isPhone ? (
        <div className={styles.dock}>
          <ModeTabBar />
        </div>
      ) : null}
      <ShortcutSheet />
    </div>
  );
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  return (
    <ShellSlotsProvider>
      <ShellLayoutView />
      {children}
    </ShellSlotsProvider>
  );
}
