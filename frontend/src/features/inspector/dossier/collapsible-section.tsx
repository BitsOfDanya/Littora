"use client";

import type { ReactNode } from "react";
import { cn } from "@/ui/cn";
import { IconChevronDown } from "@/ui/icons";

export function CollapsibleSection({
  id,
  index,
  title,
  open,
  onToggle,
  aside,
  children,
}: {
  id: string;
  index: string;
  title: string;
  open: boolean;
  onToggle: (open: boolean) => void;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-[var(--inspector-pin,40px)] border-b border-line-hairline"
    >
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`${id}-body`}
          onClick={() => onToggle(!open)}
          className="flex min-h-10 w-full items-baseline gap-2 px-4 py-3 text-left hover:bg-surface-raised"
        >
          <span className="font-mono text-[11px] text-text-tertiary">{index}</span>
          <span className="font-serif text-[16px] leading-[19px] font-medium italic">{title}</span>
          <span className="ml-auto flex items-center gap-2 self-center">
            {aside}
            <IconChevronDown
              size={14}
              className={cn(
                "text-text-secondary transition-transform duration-[var(--t-2)]",
                open && "rotate-180",
              )}
            />
          </span>
        </button>
      </h3>
      <div id={`${id}-body`} hidden={!open} className="px-4 pb-3">
        {children}
      </div>
    </section>
  );
}
