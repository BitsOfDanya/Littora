"use client";

import { useWorkspaceStore } from "@/state/workspace-store";
import { cn } from "@/ui/cn";
import { Kbd } from "@/ui/kbd";
import { Tooltip } from "@/ui/tooltip";

const DEMO_SWITCH_HINT =
  "Показывать демонстрационные данные интерфейса (фикстуры, не результат модели)";

type DemoSwitchProps = { size?: "bar" | "sheet"; className?: string };

export function DemoSwitch({ size = "bar", className }: DemoSwitchProps) {
  const enabled = useWorkspaceStore((state) => state.demoFixtures);
  const toggle = useWorkspaceStore((state) => state.toggleDemoFixtures);
  const isSheet = size === "sheet";

  return (
    <Tooltip content={DEMO_SWITCH_HINT} shortcut={isSheet ? undefined : "D"} className={className}>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label="Демо-данные"
        aria-keyshortcuts="D"
        onClick={toggle}
        className={cn(
          "inline-flex shrink-0 items-center gap-2 rounded-[var(--radius-ctl)] border border-line-control pr-1.5 pl-2 text-[12px] font-medium whitespace-nowrap transition-colors duration-[var(--t-2)] hover:border-line-strong",
          isSheet ? "h-10 px-3 text-[13px]" : "h-7",
          enabled
            ? "demo-hatch bg-surface-raised text-text-primary"
            : "bg-transparent text-text-secondary",
        )}
      >
        <span className="font-mono text-[11px] tracking-[0.06em]">ДЕМО</span>
        <span className={cn(!isSheet && "hidden 2xl:inline")}>{enabled ? "вкл" : "выкл"}</span>
        {isSheet ? null : <Kbd className="hidden bg-surface-panel lg:inline-grid">D</Kbd>}
      </button>
    </Tooltip>
  );
}
