"use client";

import { type KeyboardEvent, type ReactNode, useRef } from "react";
import type { CartoucheTab } from "@/state/cartouche-store";
import { cn } from "@/ui/cn";
import { IconChevronUp } from "@/ui/icons";
import { Tooltip } from "@/ui/tooltip";
import type { RowDensity } from "./layer-row";

export type TabIds = { legend: string; objects: string; panel: string };

const TAB_ORDER: readonly CartoucheTab[] = ["legend", "objects"];

type TabButtonProps = {
  id: string;
  panelId: string;
  selected: boolean;
  density: RowDensity;
  onSelect: () => void;
  buttonRef: (element: HTMLButtonElement | null) => void;
  children: ReactNode;
};

function TabButton({
  id,
  panelId,
  selected,
  density,
  onSelect,
  buttonRef,
  children,
}: TabButtonProps) {
  return (
    <button
      ref={buttonRef}
      id={id}
      type="button"
      role="tab"
      aria-selected={selected}
      aria-controls={panelId}
      tabIndex={selected ? 0 : -1}
      onClick={onSelect}
      className={cn(
        "inline-flex min-w-0 flex-auto items-center justify-center gap-1.5 rounded-[1px] px-2 whitespace-nowrap text-text-secondary transition-colors duration-[var(--t-2)] hover:bg-surface-raised hover:text-text-primary",
        density === "touch" ? "h-10" : "h-6",
        selected &&
          "bg-surface-raised font-semibold text-text-primary shadow-[inset_0_0_0_1px_var(--text-primary)]",
      )}
    >
      {children}
    </button>
  );
}

type CartoucheHeaderProps = {
  tab: CartoucheTab;
  onTab: (tab: CartoucheTab) => void;
  objectsCount: number | null;
  ids: TabIds;
  density: RowDensity;
  onCollapse?: () => void;
};

export function CartoucheHeader({
  tab,
  onTab,
  objectsCount,
  ids,
  density,
  onCollapse,
}: CartoucheHeaderProps) {
  const buttons = useRef<Partial<Record<CartoucheTab, HTMLButtonElement | null>>>({});

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = TAB_ORDER.indexOf(tab);
    const next =
      event.key === "ArrowRight"
        ? TAB_ORDER[(index + 1) % TAB_ORDER.length]
        : event.key === "ArrowLeft"
          ? TAB_ORDER[(index + TAB_ORDER.length - 1) % TAB_ORDER.length]
          : event.key === "Home"
            ? TAB_ORDER[0]
            : event.key === "End"
              ? TAB_ORDER[TAB_ORDER.length - 1]
              : null;
    if (!next) return;
    event.preventDefault();
    onTab(next);
    buttons.current[next]?.focus();
  };

  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-line-hairline px-2 py-1">
      <div
        role="tablist"
        aria-label="Картуш карты"
        onKeyDown={handleKeyDown}
        className="flex min-w-0 flex-1 gap-px rounded-[var(--radius-ctl)] border border-line-control bg-surface-sunken p-px"
      >
        <TabButton
          id={ids.legend}
          panelId={ids.panel}
          selected={tab === "legend"}
          density={density}
          onSelect={() => onTab("legend")}
          buttonRef={(element) => {
            buttons.current.legend = element;
          }}
        >
          <span className="font-serif text-[15px] leading-4 font-medium italic">
            Условные знаки
          </span>
        </TabButton>
        <TabButton
          id={ids.objects}
          panelId={ids.panel}
          selected={tab === "objects"}
          density={density}
          onSelect={() => onTab("objects")}
          buttonRef={(element) => {
            buttons.current.objects = element;
          }}
        >
          <span className="text-[13px]">Объекты</span>
          {objectsCount !== null ? (
            <span className="font-mono text-[11px] text-text-tertiary">{objectsCount}</span>
          ) : null}
        </TabButton>
      </div>
      {onCollapse ? (
        <Tooltip content="Свернуть" shortcut="L" side="bottom">
          <button
            type="button"
            aria-label="Свернуть условные знаки (L)"
            aria-keyshortcuts="L"
            aria-expanded
            onClick={onCollapse}
            className="grid size-7 shrink-0 place-items-center rounded-[var(--radius-ctl)] border border-line-control bg-surface-raised text-text-secondary transition-colors duration-[var(--t-2)] hover:border-line-strong hover:text-text-primary"
          >
            <IconChevronUp />
          </button>
        </Tooltip>
      ) : null}
    </div>
  );
}
