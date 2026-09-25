"use client";

import { type ReactNode, useId } from "react";
import type { MapModeId } from "@/config/layers";
import { type CartoucheGroupId, useCartoucheStore } from "@/state/cartouche-store";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { IconChevronDown } from "@/ui/icons";
import { Caps } from "@/ui/section";
import type { RowDensity } from "./layer-row";

type GroupSectionProps = {
  mode: MapModeId;
  id: CartoucheGroupId;
  title: ReactNode;
  demo?: boolean;
  defaultOpen?: boolean;
  summary?: ReactNode;
  density?: RowDensity;
  children: ReactNode;
};

export function GroupSection({
  mode,
  id,
  title,
  demo,
  defaultOpen = true,
  summary,
  density = "compact",
  children,
}: GroupSectionProps) {
  const contentId = useId();
  const open = useCartoucheStore((state) => state.groupOpenByMode[mode]?.[id] ?? defaultOpen);
  const setGroupOpen = useCartoucheStore((state) => state.setGroupOpen);

  return (
    <section className="border-t border-line-hairline px-3 pt-1 pb-1 first:border-t-0">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setGroupOpen(mode, id, !open)}
        className={cn(
          "-mx-1.5 flex w-[calc(100%+12px)] items-center gap-1.5 rounded-[var(--radius-ctl)] px-1.5 text-left hover:bg-surface-raised",
          density === "touch" ? "min-h-10" : "min-h-7",
          demo && "demo-hatch",
        )}
      >
        <IconChevronDown
          size={12}
          className={cn("shrink-0 text-text-tertiary", !open && "-rotate-90")}
        />
        <Caps className="min-w-0 text-text-secondary">{title}</Caps>
        {demo ? <DemoTag /> : null}
        {!open && summary ? (
          <span className="ml-auto shrink-0 font-mono text-[11px] text-text-tertiary">
            {summary}
          </span>
        ) : null}
      </button>
      <div id={contentId} hidden={!open} className="flex flex-col pt-0.5 pb-1.5">
        {children}
      </div>
    </section>
  );
}
