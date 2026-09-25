"use client";

import { motion, useReducedMotion } from "motion/react";
import { type ReactNode, useId, useRef } from "react";
import type { MapModeId } from "@/config/layers";
import { useCartoucheWidth, useFrameWidth } from "@/features/map/furniture/use-frame-width";
import { useRegisterOverlayRect } from "@/features/map/overlay-rects";
import { useObjectHotkeys } from "@/features/objects/use-object-hotkeys";
import { useHotkey } from "@/features/shell/hotkeys";
import { useCartoucheStore } from "@/state/cartouche-store";
import { useShellUiStore } from "@/state/shell-ui-store";
import { CartoucheHeader, type TabIds } from "./cartouche-header";
import { LegendFooter } from "./cartouche-footer";
import { CollapsedStrip } from "./collapsed-strip";
import type { RowDensity } from "./layer-row";
import { LegendView } from "./legend-view";
import { ObjectsFooter, ObjectsTab, useObjectsCount } from "./objects-tab";
import { SheetDemoSwitch } from "./sheet-demo-switch";
import { useCartoucheCollapse } from "./use-cartouche-collapse";
import { useHydrated } from "./use-hydrated";
import { useMapMode } from "./use-map-mode";
import { MEDIA, useMediaQuery } from "./use-media-query";

export type CartoucheVariant = "overlay" | "sheet";

const FURNITURE_GAP_PX = 12;
const MODE_FADE = { duration: 0.15, ease: [0.2, 0, 0.38, 0.9] } as const;

function useTabIds(): TabIds {
  const legend = useId();
  const objects = useId();
  const panel = useId();
  return { legend, objects, panel };
}

type CartouchePanelProps = {
  mode: MapModeId;
  density: RowDensity;
  onCollapse?: () => void;
  footerLead?: ReactNode;
};

function CartouchePanel({ mode, density, onCollapse, footerLead }: CartouchePanelProps) {
  const tab = useCartoucheStore((state) => state.tab);
  const setTab = useCartoucheStore((state) => state.setTab);
  const showAll = useCartoucheStore((state) => state.showAllLayers);
  const objectsCount = useObjectsCount();
  const ids = useTabIds();
  const reducedMotion = useReducedMotion();

  return (
    <>
      <CartoucheHeader
        tab={tab}
        onTab={setTab}
        objectsCount={objectsCount}
        ids={ids}
        density={density}
        onCollapse={onCollapse}
      />
      <div
        id={ids.panel}
        role="tabpanel"
        aria-labelledby={tab === "legend" ? ids.legend : ids.objects}
        className="min-h-0 flex-1 [scrollbar-width:thin] overflow-y-auto overscroll-contain"
      >
        <motion.div
          key={mode}
          initial={reducedMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={MODE_FADE}
        >
          {tab === "legend" ? (
            <LegendView mode={mode} showAll={showAll} density={density} />
          ) : (
            <ObjectsTab density={density} />
          )}
        </motion.div>
      </div>
      {tab === "legend" ? (
        <LegendFooter mode={mode} density={density} lead={footerLead} />
      ) : (
        <ObjectsFooter density={density} lead={footerLead} />
      )}
    </>
  );
}

function CartoucheOverlay({ mode }: { mode: MapModeId }) {
  const ref = useRef<HTMLElement>(null);
  const tabletUp = useMediaQuery(MEDIA.tabletUp);
  const frame = useFrameWidth();
  const width = useCartoucheWidth();
  const objectsCount = useObjectsCount();
  const { collapsed, toggle, expand } = useCartoucheCollapse(mode);
  const setTab = useCartoucheStore((state) => state.setTab);
  const requestTableFocus = useCartoucheStore((state) => state.requestTableFocus);
  const modalOpen = useShellUiStore((state) => state.shortcutSheetOpen);
  const inset = frame + FURNITURE_GAP_PX;
  const hotkeysOn = tabletUp && !modalOpen;

  useRegisterOverlayRect("cartouche", ref, "left", tabletUp && !collapsed);
  useRegisterOverlayRect("cartouche-strip", ref, "top", tabletUp && collapsed);
  useHotkey("KeyL", toggle, { enabled: hotkeysOn });
  useHotkey(
    "KeyO",
    () => {
      expand();
      requestTableFocus();
    },
    { enabled: hotkeysOn },
  );
  useObjectHotkeys(!modalOpen);

  return (
    <section
      ref={ref}
      aria-label="Условные знаки и объекты"
      className="pointer-events-auto absolute z-10 hidden flex-col border border-line-control bg-surface-panel p-[3px] text-text-primary md:flex"
      style={{
        top: inset,
        left: inset,
        width: width || undefined,
        maxHeight: `calc(100% - ${inset * 2}px)`,
      }}
    >
      <div className="flex min-h-0 flex-1 flex-col border border-line-hairline">
        {collapsed ? (
          <CollapsedStrip
            mode={mode}
            objectsCount={objectsCount}
            onExpand={expand}
            onOpenObjects={() => {
              expand();
              setTab("objects");
            }}
          />
        ) : (
          <CartouchePanel mode={mode} density="compact" onCollapse={toggle} />
        )}
      </div>
    </section>
  );
}

function CartoucheSheet({ mode }: { mode: MapModeId }) {
  return (
    <section
      aria-label="Слои и объекты"
      className="flex h-full min-h-0 flex-col bg-surface-panel text-text-primary"
    >
      <CartouchePanel mode={mode} density="touch" footerLead={<SheetDemoSwitch />} />
    </section>
  );
}

type CartoucheProps = { variant?: CartoucheVariant; mode?: MapModeId };

export function Cartouche({ variant = "overlay", mode: modeOverride }: CartoucheProps) {
  const routeMode = useMapMode();
  const hydrated = useHydrated();
  const mode = modeOverride ?? routeMode;
  if (!mode || !hydrated) return null;
  return variant === "sheet" ? <CartoucheSheet mode={mode} /> : <CartoucheOverlay mode={mode} />;
}
