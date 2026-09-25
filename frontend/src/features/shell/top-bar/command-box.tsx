"use client";

import { useShellUiStore } from "@/state/shell-ui-store";
import { cn } from "@/ui/cn";
import { IconSearch } from "@/ui/icons";
import { Kbd } from "@/ui/kbd";
import { Tooltip } from "@/ui/tooltip";
import { useIsMacPlatform } from "../layout/use-environment";

export function CommandBox({ variant = "bar" }: { variant?: "bar" | "phone" }) {
  const open = useShellUiStore((state) => state.setShortcutSheetOpen);
  const isMac = useIsMacPlatform();
  const shortcut = isMac ? "⌘K" : "Ctrl K";

  if (variant === "phone") {
    return (
      <button
        type="button"
        aria-label="Поиск и команды"
        onClick={() => open(true)}
        className="grid size-10 shrink-0 place-items-center text-text-primary hover:bg-surface-raised"
      >
        <IconSearch size={20} />
      </button>
    );
  }

  return (
    <Tooltip content="Поиск и команды" shortcut={shortcut}>
      <button
        type="button"
        aria-label="Поиск и команды"
        aria-keyshortcuts={isMac ? "Meta+K" : "Control+K"}
        onClick={() => open(true)}
        className={cn(
          "inline-flex h-7 shrink-0 items-center gap-2 rounded-[var(--radius-ctl)] border border-line-control bg-surface-sunken pr-1 pl-2 text-[12px] whitespace-nowrap text-text-tertiary transition-colors duration-[var(--t-2)] hover:border-line-strong hover:text-text-primary 2xl:w-[196px]",
        )}
      >
        <IconSearch size={14} className="shrink-0" />
        <span className="hidden 2xl:inline">Поиск и команды</span>
        <Kbd className="ml-auto bg-surface-panel">{shortcut}</Kbd>
      </button>
    </Tooltip>
  );
}
