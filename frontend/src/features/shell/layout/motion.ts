"use client";

import { type RefObject, useLayoutEffect, useRef } from "react";

export const EASE_STD = "cubic-bezier(.2,0,.38,.9)";
export const EASE_EXIT = "cubic-bezier(.2,0,1,.9)";
export const ENTER_MS = 150;
export const EXIT_MS = 110;
export const CROSSFADE_OFFSET_MS = 40;

export function reducedMotionPreferred(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function useModeCrossfade(
  elementRef: RefObject<HTMLElement | null>,
  modeKey: string | undefined,
): void {
  const previousRef = useRef(modeKey);

  useLayoutEffect(() => {
    const previous = previousRef.current;
    previousRef.current = modeKey;
    const element = elementRef.current;
    if (!element || previous === undefined || previous === modeKey || reducedMotionPreferred())
      return;
    if (element.offsetParent === null) return;
    const animation = element.animate([{ opacity: 0 }, { opacity: 1 }], {
      duration: ENTER_MS,
      delay: CROSSFADE_OFFSET_MS,
      easing: EASE_STD,
      fill: "backwards",
    });
    return () => animation.cancel();
  }, [elementRef, modeKey]);
}
