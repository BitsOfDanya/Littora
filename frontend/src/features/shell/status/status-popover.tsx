"use client";

import { type ReactNode, useId, useRef, useState } from "react";
import { cn } from "@/ui/cn";
import { useDismissable } from "../layout/use-dismiss";

type StatusPopoverProps = {
  trigger: ReactNode;
  title: string;
  triggerLabel?: string;
  align?: "left" | "right";
  width?: string;
  className?: string;
  children: ReactNode;
};

export function StatusPopover({
  trigger,
  title,
  triggerLabel,
  align = "left",
  width = "w-[340px]",
  className,
  children,
}: StatusPopoverProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useDismissable(containerRef, open, {
    onDismiss: () => setOpen(false),
    returnFocusTo: triggerRef,
  });

  return (
    <div ref={containerRef} className={cn("relative flex h-full", className)}>
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-haspopup="dialog"
        aria-label={triggerLabel}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "flex h-full min-w-0 items-center gap-1.5 px-1.5 whitespace-nowrap hover:bg-surface-raised hover:text-text-primary",
          open && "bg-surface-raised text-text-primary",
        )}
      >
        {trigger}
      </button>
      {open ? (
        <div
          id={panelId}
          role="dialog"
          aria-label={title}
          className={cn(
            "absolute bottom-[calc(100%+1px)] z-50 max-h-[min(560px,calc(100dvh-120px))] max-w-[calc(100vw-16px)] overflow-y-auto rounded-t-[var(--radius-pop)] bg-surface-panel text-[12px] whitespace-normal text-text-primary shadow-popover",
            align === "left" ? "left-0" : "right-0",
            width,
          )}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}
