"use client";

import { type RefObject, useId, useRef } from "react";
import type { WorkspaceModeId } from "@/config/modes";
import { useShellUiStore } from "@/state/shell-ui-store";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { IconChevronLeft, IconDiamond } from "@/ui/icons";
import { SeverityGlyph } from "@/ui/indicators";
import { Kbd } from "@/ui/kbd";
import { Caps } from "@/ui/section";
import { Tooltip } from "@/ui/tooltip";
import { allowsInlineQueue, type ShellLayout } from "../layout/use-environment";
import { useDismissable } from "../layout/use-dismiss";
import { newEventsPhrase } from "./queue-copy";
import { QueueEmpty, QueueList } from "./queue-list";
import { type QueueModel, useQueue, useQueueOpen } from "./use-queue";

function QueueGlyph({ queue, size = 16 }: { queue: QueueModel; size?: number }) {
  if (queue.worstNew) return <SeverityGlyph severity={queue.worstNew} size={size} />;
  return <IconDiamond size={size} className="text-text-tertiary" />;
}

function QueueHeader({ queue, onCollapse }: { queue: QueueModel; onCollapse: () => void }) {
  return (
    <header className="flex h-7 shrink-0 items-center gap-2 border-b border-line-hairline pr-1 pl-3 whitespace-nowrap">
      <Caps className="text-text-secondary">Очередь</Caps>
      <span className="font-mono text-[11px] text-text-primary">{queue.newCount} нов.</span>
      {queue.demoOrigin === "demo" ? <DemoTag /> : null}
      <span className="ml-auto hidden items-center gap-1 text-[11px] text-text-tertiary 2xl:flex">
        <Kbd>Shift J</Kbd>
        <span aria-hidden>·</span>
        <Kbd>A</Kbd>
      </span>
      <button
        type="button"
        aria-label="Свернуть очередь (Q)"
        title="Свернуть очередь · Q"
        onClick={onCollapse}
        className="ml-auto grid size-6 shrink-0 place-items-center rounded-[var(--radius-ctl)] text-text-secondary hover:bg-surface-raised hover:text-text-primary 2xl:ml-0"
      >
        <IconChevronLeft />
      </button>
    </header>
  );
}

type QueuePanelProps = {
  queue: QueueModel;
  onCollapse: () => void;
  onSelected?: () => void;
  id: string;
  className?: string;
};

function QueuePanel({ queue, onCollapse, onSelected, id, className }: QueuePanelProps) {
  return (
    <section
      id={id}
      aria-label="Очередь событий"
      className={cn("flex min-h-0 flex-col bg-surface-panel", className)}
    >
      <QueueHeader queue={queue} onCollapse={onCollapse} />
      {queue.rows.length > 0 ? (
        <QueueList rows={queue.rows} onSelected={onSelected} />
      ) : (
        <QueueEmpty />
      )}
    </section>
  );
}

type QueueStripProps = {
  queue: QueueModel;
  expanded: boolean;
  controls: string;
  onToggle: () => void;
  triggerRef?: RefObject<HTMLButtonElement | null>;
};

function QueueStrip({ queue, expanded, controls, onToggle, triggerRef }: QueueStripProps) {
  const label = `Очередь: ${newEventsPhrase(queue.newCount)}`;
  return (
    <Tooltip content={label} shortcut="Q" side="right" className="h-full">
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={expanded}
        aria-controls={controls}
        aria-label={`${label}${queue.demoOrigin === "demo" ? " · ДЕМО" : ""}. Развернуть (Q)`}
        onClick={onToggle}
        className={cn(
          "flex h-full w-11 flex-col items-center justify-center gap-1 border-r border-line-hairline text-text-primary hover:bg-surface-raised",
          expanded && "bg-surface-raised",
        )}
      >
        <QueueGlyph queue={queue} />
        <span className="font-mono text-[15px] leading-4 font-semibold">{queue.newCount}</span>
        <span className="text-[11px] leading-3 text-text-secondary">нов.</span>
        {queue.demoOrigin === "demo" ? <DemoTag className="mt-0.5" /> : null}
      </button>
    </Tooltip>
  );
}

function QueuePopover({
  queue,
  open,
  id,
  onToggle,
  onClose,
}: {
  queue: QueueModel;
  open: boolean;
  id: string;
  onToggle: () => void;
  onClose: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useDismissable(containerRef, open, { onDismiss: onClose, returnFocusTo: triggerRef });
  return (
    <div ref={containerRef} className="relative h-full shrink-0">
      <QueueStrip
        queue={queue}
        expanded={open}
        controls={id}
        onToggle={onToggle}
        triggerRef={triggerRef}
      />
      {open ? (
        <QueuePanel
          queue={queue}
          id={id}
          onCollapse={onClose}
          onSelected={onClose}
          className="absolute bottom-[calc(100%+1px)] left-0 z-40 max-h-[240px] w-[320px] rounded-t-[var(--radius-pop)] shadow-popover"
        />
      ) : null}
    </div>
  );
}

export function QueueColumn({ mode, layout }: { mode: WorkspaceModeId; layout: ShellLayout }) {
  const queue = useQueue();
  const open = useQueueOpen(mode, layout, queue.newCount);
  const setQueueOpen = useShellUiStore((state) => state.setQueueOpen);
  const panelId = useId();
  const toggle = () => setQueueOpen(mode, !open);
  const close = () => setQueueOpen(mode, false);

  if (!allowsInlineQueue(layout))
    return (
      <QueuePopover queue={queue} open={open} id={panelId} onToggle={toggle} onClose={close} />
    );
  if (!open)
    return <QueueStrip queue={queue} expanded={false} controls={panelId} onToggle={toggle} />;
  return (
    <QueuePanel
      queue={queue}
      id={panelId}
      onCollapse={close}
      className="h-full w-[var(--queue-w)] shrink-0 border-r border-line-hairline"
    />
  );
}
