"use client";

import { useEffect, useState } from "react";
import { create } from "zustand";
import { useActiveMode } from "./orientation/modes";

type Step = { key: string; selector: string; title: string; text: string };

const STEPS: Readonly<Record<string, readonly Step[]>> = {
  monitor: [
    {
      key: "aoi",
      selector: '[aria-label="Район работы"]',
      title: "Район",
      text: "Выберите акваторию: карта перейдёт к ней, лента внизу покажет пролёты Sentinel-2.",
    },
    {
      key: "rail",
      selector: '[aria-label^="Пролёты Sentinel-2"]',
      title: "Дата снимка",
      text: "Каждая метка — пролёт спутника. Цвет показывает пригодность: облака, пропуски, блики.",
    },
    {
      key: "run",
      selector: '[data-tour="run-analysis"]',
      title: "Анализ",
      text: "Запускает детектор на снимке: маска качества, зоны мусора, концентрация и статус. Ниже — «Свой снимок».",
    },
    {
      key: "layers",
      selector: '[aria-label="Условные знаки и объекты"], [aria-label="Слои и объекты"]',
      title: "Слои и объекты",
      text: "Легенда и включение слоёв: композиты, вероятность, маска, где доступна концентрация, разметка команды.",
    },
    {
      key: "tools",
      selector: '[aria-label="Инструменты карты"]',
      title: "Инструменты",
      text: "Масштаб, сетка, лупа по пикселю (I) и линейка (R).",
    },
    {
      key: "modes",
      selector: '[aria-label="Режимы"]',
      title: "Режимы",
      text: "Динамика — сравнение пролётов, Прогноз — дрейф, Обследование — маршрут из порта, Модели — точность.",
    },
  ],
  timeline: [
    {
      key: "rail",
      selector: '[aria-label^="Пролёты Sentinel-2"]',
      title: "Пролёты",
      text: "Выберите два пролёта: зоны сравнятся — новые, сохранившиеся, исчезнувшие.",
    },
  ],
  forecast: [
    {
      key: "tools",
      selector: '[aria-label="Инструменты карты"]',
      title: "Сценарий дрейфа",
      text: "Облако — где зоны могут оказаться через 6–72 ч, пунктир назад — откуда пришли. Это сценарий, не прогноз.",
    },
  ],
  survey: [
    {
      key: "tools",
      selector: '[aria-label="Инструменты карты"]',
      title: "Маршрут",
      text: "Маршрут судна из ближайшего порта и вылеты БПЛА к зонам с поправкой на дрейф; GPX — для навигатора.",
    },
  ],
  models: [
    {
      key: "guide",
      selector: "#models-guide",
      title: "Как читать",
      text: "Три вывода: чему доверять, что перепроверять и чего не выводить по снимку.",
    },
    {
      key: "gallery",
      selector: "#models-gallery",
      title: "Примеры",
      text: "Мусор вблизи и издалека: удачные и ложные обнаружения, мишени известного размера.",
    },
  ],
};

type TourState = {
  hidden: boolean;
  skipped: ReadonlySet<string>;
  skip: (key: string) => void;
  hideAll: () => void;
};

export const useTourStore = create<TourState>((set) => ({
  hidden: false,
  skipped: new Set(),
  skip: (key) => set((state) => ({ skipped: new Set([...state.skipped, key]) })),
  hideAll: () => set({ hidden: true }),
}));

type Placed = { step: Step; index: number; total: number; rect: DOMRect };

function place(steps: readonly Step[], skipped: ReadonlySet<string>, prefix: string) {
  const open = steps.filter((step) => !skipped.has(`${prefix}:${step.key}`));
  for (const [index, step] of open.entries()) {
    const target = document.querySelector(step.selector);
    const rect = target?.getBoundingClientRect();
    if (rect && rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < innerHeight)
      return { step, index, total: open.length, rect };
  }
  return null;
}

const BUBBLE_W = 280;
const GAP = 14;

export function useTourActive(): boolean {
  const hidden = useTourStore((state) => state.hidden);
  const mode = useActiveMode();
  return !hidden && Boolean(mode && STEPS[mode.id]?.length);
}

export function GuideTour() {
  const mode = useActiveMode();
  const hidden = useTourStore((state) => state.hidden);
  const skipped = useTourStore((state) => state.skipped);
  const skip = useTourStore((state) => state.skip);
  const hideAll = useTourStore((state) => state.hideAll);
  const [placed, setPlaced] = useState<Placed | null>(null);
  const modeId = mode?.id ?? "";

  useEffect(() => {
    if (hidden || !STEPS[modeId]) return;
    const update = () => setPlaced(place(STEPS[modeId], skipped, modeId));
    const first = window.setTimeout(update, 60);
    const timer = window.setInterval(update, 600);
    window.addEventListener("resize", update);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
      window.removeEventListener("resize", update);
    };
  }, [hidden, modeId, skipped]);

  if (hidden || !STEPS[modeId] || !placed) return null;
  const { step, rect } = placed;
  const right = rect.left + rect.width / 2 < innerWidth / 2;
  const left = right
    ? Math.min(rect.right + GAP, innerWidth - BUBBLE_W - 8)
    : Math.max(rect.left - GAP - BUBBLE_W, 8);
  const top = Math.min(Math.max(rect.top + rect.height / 2 - 48, 60), innerHeight - 170);
  const arrowTop = Math.min(Math.max(rect.top + rect.height / 2 - top - 6, 12), 140);

  return (
    <div
      role="dialog"
      aria-label={`Подсказка: ${step.title}`}
      className="pointer-events-auto fixed z-50 rounded-[2px] border border-line-control bg-surface-panel p-3 text-[12px] leading-4 shadow-lg"
      style={{ left, top, width: BUBBLE_W }}
    >
      <span
        aria-hidden
        className="absolute size-3 rotate-45 border-line-control bg-surface-panel"
        style={{
          top: arrowTop,
          ...(right
            ? { left: -7, borderLeftWidth: 1, borderBottomWidth: 1 }
            : { right: -7, borderRightWidth: 1, borderTopWidth: 1 }),
        }}
      />
      <p className="mb-1 flex items-baseline justify-between gap-2">
        <span className="font-semibold text-text-primary">{step.title}</span>
        <span className="font-mono text-[11px] text-text-tertiary">
          {placed.index + 1}/{placed.total}
        </span>
      </p>
      <p className="text-text-secondary">{step.text}</p>
      <div className="mt-2 flex items-center gap-3">
        <button
          type="button"
          onClick={() => skip(`${modeId}:${step.key}`)}
          className="rounded-[2px] border border-line-control px-2 py-0.5 text-text-primary hover:bg-surface-raised"
        >
          {placed.index + 1 < placed.total ? "Дальше" : "Понятно"}
        </button>
        <button
          type="button"
          onClick={hideAll}
          className="text-text-tertiary underline hover:text-text-primary"
        >
          Скрыть все подсказки
        </button>
      </div>
    </div>
  );
}
