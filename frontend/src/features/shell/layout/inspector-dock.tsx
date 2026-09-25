"use client";

import { type RefObject, useCallback, useLayoutEffect, useRef } from "react";
import { useRegionOccupied, useRegionTarget } from "../shell-slots";
import styles from "../workspace-shell.module.css";
import {
  EASE_EXIT,
  EASE_STD,
  ENTER_MS,
  EXIT_MS,
  reducedMotionPreferred,
  useModeCrossfade,
} from "./motion";

type InspectorDockProps = { modeKey: string | undefined; placement: "column" | "row" };

function enterKeyframes(placement: InspectorDockProps["placement"]): Keyframe[] {
  return placement === "column"
    ? [
        { opacity: 0, transform: "translateX(16px)" },
        { opacity: 1, transform: "none" },
      ]
    : [{ opacity: 0 }, { opacity: 1 }];
}

function useInspectorPresence(
  elementRef: RefObject<HTMLElement | null>,
  occupied: boolean,
  placement: InspectorDockProps["placement"],
) {
  const openRef = useRef(false);

  useLayoutEffect(() => {
    const element = elementRef.current;
    if (!element) return;
    const wasOpen = openRef.current;
    openRef.current = occupied;
    const reduced = reducedMotionPreferred();
    if (occupied) {
      element.dataset.state = "open";
      if (wasOpen || reduced) return;
      const enter = element.animate(enterKeyframes(placement), {
        duration: ENTER_MS,
        easing: EASE_STD,
      });
      return () => enter.cancel();
    }
    if (!wasOpen || reduced) {
      element.dataset.state = "closed";
      return;
    }
    element.dataset.state = "closing";
    const exit = element.animate([{ opacity: 1 }, { opacity: 0 }], {
      duration: EXIT_MS,
      easing: EASE_EXIT,
      fill: "forwards",
    });
    exit.onfinish = () => {
      element.dataset.state = "closed";
      exit.cancel();
    };
    return () => {
      exit.onfinish = null;
      exit.cancel();
    };
  }, [elementRef, occupied, placement]);
}

export function InspectorDock({ modeKey, placement }: InspectorDockProps) {
  const registerTarget = useRegionTarget("inspector");
  const occupied = useRegionOccupied("inspector");
  const elementRef = useRef<HTMLElement | null>(null);
  const setElement = useCallback(
    (element: HTMLElement | null) => {
      elementRef.current = element;
      registerTarget(element);
    },
    [registerTarget],
  );

  useInspectorPresence(elementRef, occupied, placement);
  useModeCrossfade(elementRef, modeKey);

  return <aside ref={setElement} aria-label="Инспектор" className={styles.inspector} />;
}
