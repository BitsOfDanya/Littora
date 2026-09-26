"use client";

import { useSyncExternalStore } from "react";
import { useCurrentAnalysis } from "./use-analysis";

const KEY = "littora:start-hint";
const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) !== "hidden";
  } catch {
    return true;
  }
}

function hide(): void {
  try {
    window.localStorage.setItem(KEY, "hidden");
  } catch {
    return;
  } finally {
    listeners.forEach((listener) => listener());
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const STEPS = [
  "Выберите дату на ленте снимков внизу",
  "Нажмите «Запустить анализ» справа",
  "Щёлкните зону — карточка с флагами и сравнением с судном",
];

export function StartHint() {
  const visible = useSyncExternalStore(subscribe, read, () => false);
  const analysis = useCurrentAnalysis().data ?? null;
  if (!visible || analysis) return null;
  return (
    <div
      role="note"
      className="pointer-events-auto fixed top-[58px] left-1/2 z-30 flex max-w-[min(760px,calc(100%-24px))] -translate-x-1/2 items-center gap-3 rounded-[2px] border border-line-control bg-surface-panel px-3 py-2 text-[12px] leading-4 shadow-lg"
    >
      <span className="shrink-0 font-semibold text-text-primary">С чего начать</span>
      <ol className="flex flex-wrap gap-x-3 gap-y-0.5 text-text-secondary">
        {STEPS.map((step, index) => (
          <li key={step}>
            <span className="font-mono text-text-primary">{index + 1}</span> {step}
          </li>
        ))}
      </ol>
      <span className="hidden shrink-0 text-text-tertiary xl:inline">
        ? — помощь · I — лупа · R — линейка
      </span>
      <button
        type="button"
        onClick={hide}
        className="shrink-0 text-text-secondary underline hover:text-text-primary"
      >
        Понятно
      </button>
    </div>
  );
}
