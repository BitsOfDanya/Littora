"use client";

import { useSyncExternalStore } from "react";
import { useAnalysisStore } from "@/state/analysis-store";
import { useCurrentAnalysis } from "./use-analysis";

const KEY = "littora:start-hint";
const listeners = new Set<() => void>();

export function readHints(): boolean {
  try {
    return window.localStorage.getItem(KEY) !== "hidden";
  } catch {
    return true;
  }
}

export function showHints(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    return;
  } finally {
    listeners.forEach((listener) => listener());
  }
}

export function hideHints(): void {
  try {
    window.localStorage.setItem(KEY, "hidden");
  } catch {
    return;
  } finally {
    listeners.forEach((listener) => listener());
  }
}

export function subscribeHints(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const START = [
  "Выберите дату на ленте снимков внизу",
  "Нажмите «Запустить анализ» справа",
  "Щёлкните зону — карточка с флагами и сравнением с судном",
];

function useHint(): { title: string; steps: readonly string[] } {
  const analysis = useCurrentAnalysis().data ?? null;
  const zoneId = useAnalysisStore((state) => state.zoneId);
  if (!analysis) return { title: "С чего начать", steps: START };
  if (zoneId)
    return {
      title: "Карточка зоны",
      steps: [
        "Сверху — что делать с зоной",
        "Ниже — сравнение с измерениями с судна",
        "I — лупа по пикселю, R — линейка",
      ],
    };
  if (analysis.status.status === "insufficient_data")
    return {
      title: "Снимок не подошёл",
      steps: [
        "Выберите другую дату на ленте",
        "Или расширьте окно поиска до ±3–7 сут",
        "Облака и тени видны слоем «Маска»",
      ],
    };
  if (analysis.status.status === "not_detected")
    return {
      title: "Скоплений не найдено",
      steps: [
        "Посмотрите композиты FDI и «Ложные»",
        "Сравните с соседним пролётом в «Динамике»",
        "Зелёный пунктир — где доступна концентрация",
      ],
    };
  return {
    title: `Найдено зон: ${analysis.detection.zones.length}`,
    steps: [
      "Закрашенный маркер — проверить на месте",
      "Бледный — перепроверить, полый — похоже на судно",
      "Щёлкните зону, чтобы открыть карточку",
    ],
  };
}

export function StartHint() {
  const visible = useSyncExternalStore(subscribeHints, readHints, () => false);
  const hint = useHint();
  if (!visible) return null;
  return (
    <div
      role="note"
      aria-live="polite"
      className="pointer-events-auto fixed top-[58px] left-1/2 z-30 flex max-w-[min(820px,calc(100%-24px))] -translate-x-1/2 items-center gap-3 rounded-[2px] border border-line-control bg-surface-panel px-3 py-2 text-[12px] leading-4 shadow-lg"
    >
      <span className="shrink-0 font-semibold text-text-primary">{hint.title}</span>
      <ol className="flex flex-wrap gap-x-3 gap-y-0.5 text-text-secondary">
        {hint.steps.map((step, index) => (
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
