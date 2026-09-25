"use client";

import { useCallback, useEffect } from "react";
import { useStatusHintStore } from "@/features/shell/status-hint-store";

export const REPORT_BASE_HINT = "Отчёт валидации · карта затемнена · 1–4 — вернуться к карте";

export function useReportBaseHint(): void {
  const setHint = useStatusHintStore((state) => state.setHint);
  useEffect(() => {
    setHint(REPORT_BASE_HINT);
    return () => setHint(null);
  }, [setHint]);
}

export function useReportHint(): { show: (hint: string) => void; restore: () => void } {
  const setHint = useStatusHintStore((state) => state.setHint);
  const show = useCallback((hint: string) => setHint(hint), [setHint]);
  const restore = useCallback(() => setHint(REPORT_BASE_HINT), [setHint]);
  return { show, restore };
}
