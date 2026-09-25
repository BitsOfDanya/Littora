"use client";

import { type RefCallback, useCallback, useState } from "react";

export function useElementWidth<T extends HTMLElement>(): [RefCallback<T>, number] {
  const [width, setWidth] = useState(0);
  const ref = useCallback((element: T | null) => {
    if (!element) return;
    setWidth(Math.round(element.getBoundingClientRect().width));
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}
