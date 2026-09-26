"use client";

import { useSyncExternalStore } from "react";
import { hideHints, readHints, subscribeHints } from "./start-hint";

export function ModeHint({ title, steps }: { title: string; steps: readonly string[] }) {
  const visible = useSyncExternalStore(subscribeHints, readHints, () => false);
  if (!visible) return null;
  return (
    <div
      role="note"
      className="pointer-events-auto fixed top-[58px] left-1/2 z-30 flex max-w-[min(820px,calc(100%-24px))] -translate-x-1/2 items-center gap-3 rounded-[2px] border border-line-control bg-surface-panel px-3 py-2 text-[12px] leading-4 shadow-lg"
    >
      <span className="shrink-0 font-semibold text-text-primary">{title}</span>
      <ol className="flex flex-wrap gap-x-3 gap-y-0.5 text-text-secondary">
        {steps.map((step, index) => (
          <li key={step}>
            <span className="font-mono text-text-primary">{index + 1}</span> {step}
          </li>
        ))}
      </ol>
      <button
        type="button"
        onClick={hideHints}
        title="Скрыть подсказки; вернуть — в окне «Помощь»"
        className="shrink-0 text-text-secondary underline hover:text-text-primary"
      >
        Понятно
      </button>
    </div>
  );
}
