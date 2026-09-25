"use client";

import { useWorkspaceStore } from "@/state/workspace-store";
import { cn } from "@/ui/cn";

export function SheetDemoSwitch() {
  const demoOn = useWorkspaceStore((state) => state.demoFixtures);
  const setDemoFixtures = useWorkspaceStore((state) => state.setDemoFixtures);
  return (
    <button
      type="button"
      role="switch"
      aria-checked={demoOn}
      title="Показывать демонстрационные данные интерфейса (фикстуры, не результат модели)"
      onClick={() => setDemoFixtures(!demoOn)}
      className={cn(
        "inline-flex h-10 shrink-0 items-center rounded-[var(--radius-ctl)] border border-line-control px-3 font-mono text-[11px] font-medium tracking-[0.06em] text-text-secondary",
        demoOn && "demo-hatch border-demo-ink text-demo-ink",
      )}
    >
      ДЕМО {demoOn ? "вкл" : "выкл"}
    </button>
  );
}
