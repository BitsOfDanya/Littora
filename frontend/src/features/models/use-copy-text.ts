"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type CopyState = "idle" | "copied" | "failed";

const CONFIRM_MS = 1200;

function copyWithSelection(text: string): boolean {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }
  area.remove();
  return copied;
}

export function useCopyText(): [CopyState, (text: string) => void] {
  const [state, setState] = useState<CopyState>("idle");
  const timerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  const settle = useCallback((next: CopyState) => {
    setState(next);
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current =
      next === "copied" ? window.setTimeout(() => setState("idle"), CONFIRM_MS) : null;
  }, []);

  const copy = useCallback(
    (text: string) => {
      const fallback = () => settle(copyWithSelection(text) ? "copied" : "failed");
      if (!navigator.clipboard?.writeText) {
        fallback();
        return;
      }
      navigator.clipboard.writeText(text).then(() => settle("copied"), fallback);
    },
    [settle],
  );

  return [state, copy];
}
