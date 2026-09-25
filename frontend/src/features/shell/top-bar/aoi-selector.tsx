"use client";

import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { AOI_GROUP_LABELS, AREAS_OF_INTEREST, type AoiId, findAoi } from "@/config/aois";
import type { AreaOfInterest } from "@/domain/aoi";
import { fitAoi } from "@/features/map/camera";
import { useMainMap } from "@/features/map/use-main-map";
import { useWorkspaceStore } from "@/state/workspace-store";
import { cn } from "@/ui/cn";
import { IconChevronDown } from "@/ui/icons";
import { useDismissable } from "../layout/use-dismiss";

const GROUPS = ["case", "reference", "russian-seas"] as const;

function subline(aoi: AreaOfInterest): string {
  return [aoi.seaName, aoi.sentinel2Tiles[0]].filter(Boolean).join(" · ");
}

function AoiOption({
  aoi,
  selected,
  onChoose,
}: {
  aoi: AreaOfInterest;
  selected: boolean;
  onChoose: () => void;
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      data-aoi-option
      onClick={onChoose}
      className={cn(
        "grid w-full grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-0.5 border-b border-line-hairline px-3.5 py-2 text-left last:border-b-0 hover:bg-surface-raised",
        selected && "bg-surface-sunken shadow-[inset_3px_0_0_var(--text-primary)]",
      )}
    >
      <span className="font-serif text-[16px] leading-5 font-medium text-text-primary italic">
        {aoi.name}
      </span>
      <span className="row-span-2 max-w-[88px] self-start pt-0.5 text-right font-mono text-[11px] leading-4 text-text-tertiary">
        {aoi.sentinel2Tiles.length ? aoi.sentinel2Tiles.join(" ") : "тайлы —"}
      </span>
      <span className="text-[11px] leading-4 text-text-secondary">
        {aoi.seaName} · {aoi.country}
      </span>
      <span className="col-span-2 text-[12px] leading-4 text-text-tertiary">{aoi.rationale}</span>
    </button>
  );
}

function moveFocus(list: HTMLElement | null, event: KeyboardEvent<HTMLElement>): void {
  if (!list || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const options = [...list.querySelectorAll<HTMLButtonElement>("[data-aoi-option]")];
  const index = options.indexOf(document.activeElement as HTMLButtonElement);
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? options.length - 1
        : event.key === "ArrowDown"
          ? Math.min(options.length - 1, index + 1)
          : Math.max(0, index - 1);
  event.preventDefault();
  options[next]?.focus();
}

export function AoiSelector() {
  const aoiId = useWorkspaceStore((state) => state.aoiId);
  const setAoi = useWorkspaceStore((state) => state.setAoi);
  const map = useMainMap();
  const [isOpen, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const aoi = findAoi(aoiId);

  useDismissable(containerRef, isOpen, {
    onDismiss: () => setOpen(false),
    returnFocusTo: triggerRef,
  });

  useEffect(() => {
    if (!isOpen) return;
    const selected = listRef.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]');
    selected?.focus();
  }, [isOpen]);

  const choose = (id: AoiId) => {
    setOpen(false);
    triggerRef.current?.focus();
    if (id === aoiId) return;
    setAoi(id);
    const next = findAoi(id);
    if (map && next) fitAoi(map, next);
  };

  return (
    <div ref={containerRef} className="relative h-full min-w-0 max-md:flex-1 md:shrink-0">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={listId}
        title={aoi ? `${aoi.name} · ${subline(aoi)}` : undefined}
        onClick={() => setOpen((open) => !open)}
        className="flex h-full w-full items-center gap-2.5 border-r border-line-hairline px-3 text-left hover:bg-surface-raised md:min-w-[196px] md:px-3.5"
      >
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-serif text-[16px] leading-[19px] font-medium italic">
            {aoi?.name}
          </span>
          {aoi ? (
            <span className="hidden truncate pt-0.5 font-mono text-[11px] leading-3 text-text-tertiary xl:block">
              {subline(aoi)}
            </span>
          ) : null}
        </span>
        <IconChevronDown className="shrink-0 text-text-secondary" />
      </button>
      {isOpen ? (
        <div
          ref={listRef}
          id={listId}
          role="listbox"
          aria-label="Район работы"
          onKeyDown={(event) => moveFocus(listRef.current, event)}
          className="absolute top-full left-0 z-50 mt-px flex max-h-[min(640px,calc(100dvh-120px))] w-[360px] max-w-[100vw] flex-col overflow-y-auto rounded-b-[var(--radius-pop)] bg-surface-panel shadow-popover max-md:fixed max-md:inset-x-0 max-md:top-12 max-md:w-auto"
        >
          {GROUPS.map((group) => (
            <div key={group} role="group" aria-label={AOI_GROUP_LABELS[group]}>
              <div className="border-b border-line-hairline px-3.5 pt-2.5 pb-1.5 text-[11px] leading-[14px] font-semibold tracking-[0.07em] text-text-tertiary uppercase [font-stretch:88%]">
                {AOI_GROUP_LABELS[group]}
              </div>
              {AREAS_OF_INTEREST.filter((entry) => entry.group === group).map((entry) => (
                <AoiOption
                  key={entry.id}
                  aoi={entry}
                  selected={entry.id === aoiId}
                  onChoose={() => choose(entry.id)}
                />
              ))}
            </div>
          ))}
          <p className="border-t border-line-hairline px-3.5 py-2 text-[11px] leading-4 text-text-tertiary">
            Районы — конфигурация сервера, не результат модели
          </p>
        </div>
      ) : null}
    </div>
  );
}
