"use client";

import {
  type CSSProperties,
  type PointerEvent,
  useRef,
  useState,
  type WheelEvent as ReactWheelEvent,
} from "react";
import type { Map as MapLibreMap } from "maplibre-gl";
import { formatLatitude, formatLongitude } from "@/lib/format/coordinates";
import { GROUND_INK } from "../palette";
import { useMainMap } from "../use-main-map";
import { useGround } from "../use-map-palette";
import { viewportProjector } from "./viewport-projector";

type BandSide = "top" | "bottom" | "left" | "right";

type RuleState = { side: BandSide; offset: number; label: string };

const TAG_GAP_PX = 6;
const TOP_TAG_CLEARANCE_PX = 42;
const TAG_INK = { dark: "#0A0E11", light: "#FFFFFF" } as const;

const BAND_PLACEMENT: Readonly<Record<BandSide, (band: number) => CSSProperties>> = {
  top: (band) => ({ top: 0, left: band, right: band, height: band }),
  bottom: (band) => ({ bottom: 0, left: band, right: band, height: band }),
  left: (band) => ({ left: 0, top: band, bottom: band, width: band }),
  right: (band) => ({ right: 0, top: band, bottom: band, width: band }),
};

const isMeridianSide = (side: BandSide) => side === "top" || side === "bottom";

function ruleLine(rule: RuleState, band: number): CSSProperties {
  return isMeridianSide(rule.side)
    ? { left: rule.offset, top: band, bottom: band, width: 1 }
    : { top: rule.offset, left: band, right: band, height: 1 };
}

function ruleTag(rule: RuleState, band: number): CSSProperties {
  const inset = band + TAG_GAP_PX;
  if (rule.side === "top")
    return { left: rule.offset + TAG_GAP_PX, top: band + TOP_TAG_CLEARANCE_PX };
  if (rule.side === "bottom") return { left: rule.offset + TAG_GAP_PX, bottom: inset };
  if (rule.side === "left")
    return { top: rule.offset - TAG_GAP_PX, left: inset, transform: "translateY(-100%)" };
  return { top: rule.offset - TAG_GAP_PX, right: inset, transform: "translateY(-100%)" };
}

function forwardWheelTo(map: MapLibreMap | undefined) {
  return (event: ReactWheelEvent<HTMLDivElement>) => {
    if (!map) return;
    const { deltaX, deltaY, deltaMode, clientX, clientY, ctrlKey, shiftKey, altKey, metaKey } =
      event.nativeEvent;
    map.getCanvas().dispatchEvent(
      new WheelEvent("wheel", {
        deltaX,
        deltaY,
        deltaMode,
        clientX,
        clientY,
        ctrlKey,
        shiftKey,
        altKey,
        metaKey,
        bubbles: true,
        cancelable: true,
      }),
    );
  };
}

export function FrameRule({ band }: { band: number }) {
  const map = useMainMap();
  const ground = useGround();
  const selection = GROUND_INK[ground].selection;
  const rootRef = useRef<HTMLDivElement>(null);
  const [rule, setRule] = useState<RuleState | null>(null);

  const track = (side: BandSide) => (event: PointerEvent<HTMLDivElement>) => {
    const root = rootRef.current;
    if (!map || !root || event.pointerType !== "mouse") return;
    const box = root.getBoundingClientRect();
    const x = event.clientX - box.left;
    const y = event.clientY - box.top;
    const projector = viewportProjector(map, root);
    const meridian = isMeridianSide(side);
    const point = projector.unproject(meridian ? x : box.width / 2, meridian ? box.height / 2 : y);
    setRule({
      side,
      offset: Math.round(meridian ? x : y),
      label: meridian ? formatLongitude(point.lng, "dm") : formatLatitude(point.lat, "dm"),
    });
  };

  if (band <= 0) return null;

  return (
    <div ref={rootRef} className="pointer-events-none absolute inset-0">
      {(Object.keys(BAND_PLACEMENT) as BandSide[]).map((side) => (
        <div
          key={side}
          aria-hidden
          className="pointer-events-auto absolute cursor-crosshair"
          style={BAND_PLACEMENT[side](band)}
          onPointerMove={track(side)}
          onPointerLeave={() => setRule(null)}
          onWheel={forwardWheelTo(map)}
        />
      ))}
      {rule ? (
        <>
          <div
            aria-hidden
            className="absolute"
            style={{ ...ruleLine(rule, band), background: selection }}
          />
          <p
            className="absolute px-1.5 py-0.5 font-mono text-[11px] leading-[14px] font-medium whitespace-nowrap"
            style={{ ...ruleTag(rule, band), background: selection, color: TAG_INK[ground] }}
          >
            {rule.label}
          </p>
        </>
      ) : null}
    </div>
  );
}
