"use client";

import type { MapModeId } from "@/config/layers";
import { useForecastPickHint } from "@/features/forecast/use-forecast-hint";
import { Button } from "@/ui/button";
import { IconChevronDown } from "@/ui/icons";
import { Tooltip } from "@/ui/tooltip";
import { MiniKey } from "./mini-key";

type CollapsedStripProps = {
  mode: MapModeId;
  objectsCount: number | null;
  onExpand: () => void;
  onOpenObjects: () => void;
};

function ForecastHint({ mode }: { mode: MapModeId }) {
  const pick = useForecastPickHint();
  if (mode !== "forecast" || !pick) return null;
  return (
    <p className="px-2.5 pb-2 text-[12px] leading-4 text-text-secondary">
      Выберите пятно, чтобы построить прогноз
    </p>
  );
}

export function CollapsedStrip({
  mode,
  objectsCount,
  onExpand,
  onOpenObjects,
}: CollapsedStripProps) {
  return (
    <div className="flex flex-col">
      <div className="flex h-[30px] items-center gap-1.5 pr-1 pl-0.5">
        <Tooltip content="Развернуть" shortcut="L" side="bottom">
          <button
            type="button"
            aria-expanded={false}
            aria-keyshortcuts="L"
            aria-label="Условные знаки — развернуть (L)"
            onClick={onExpand}
            className="flex h-7 items-center gap-1 rounded-[var(--radius-ctl)] px-1.5 whitespace-nowrap text-text-primary transition-colors duration-[var(--t-2)] hover:bg-surface-raised"
          >
            <IconChevronDown size={14} className="-rotate-90 text-text-tertiary" />
            <span className="font-serif text-[15px] leading-4 font-medium italic">
              Условные знаки
            </span>
          </button>
        </Tooltip>
        <span className="flex min-w-0 flex-1 justify-center">
          <MiniKey mode={mode} />
        </span>
        <Button size="sm" onClick={onOpenObjects} aria-keyshortcuts="O" title="Объекты · O">
          Объекты
          {objectsCount !== null ? (
            <span className="font-mono text-[11px] text-text-tertiary">{objectsCount}</span>
          ) : null}
        </Button>
      </div>
      <ForecastHint mode={mode} />
    </div>
  );
}
