"use client";

import { type RefObject, useEffect, useRef } from "react";
import { useEscapeLayer } from "../keyboard/escape-stack";

type DismissOptions = {
  onDismiss: () => void;
  returnFocusTo?: RefObject<HTMLElement | null>;
};

export function useDismissable(
  containerRef: RefObject<HTMLElement | null>,
  open: boolean,
  { onDismiss, returnFocusTo }: DismissOptions,
): void {
  const dismissRef = useRef(onDismiss);

  useEffect(() => {
    dismissRef.current = onDismiss;
  });

  useEscapeLayer(open, () => {
    dismissRef.current();
    returnFocusTo?.current?.focus();
  });

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) dismissRef.current();
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [open, containerRef]);
}
