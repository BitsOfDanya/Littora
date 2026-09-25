"use client";

import Link from "next/link";
import { WORKSPACE_MODES } from "@/config/modes";
import { cn } from "@/ui/cn";
import { ModeIcons } from "@/ui/icons";
import { Kbd } from "@/ui/kbd";
import { Tooltip } from "@/ui/tooltip";
import { MODE_PURPOSE, modeHref, useActiveMode, useViewQuery } from "../orientation/modes";

type ModeTabsVariant = "bar" | "row";

export function ModeTabs({ variant }: { variant: ModeTabsVariant }) {
  const activeMode = useActiveMode();
  const query = useViewQuery();

  return (
    <nav
      aria-label="Режимы"
      className={cn(
        "h-full",
        variant === "row" && "border-b border-line-hairline bg-surface-panel",
      )}
    >
      <ul className={cn("h-full", variant === "row" ? "grid grid-cols-5" : "ml-1 flex")}>
        {WORKSPACE_MODES.map((mode) => {
          const isActive = activeMode?.id === mode.id;
          return (
            <li key={mode.id} className="h-full">
              <Tooltip content={MODE_PURPOSE[mode.id]} shortcut={mode.hotkey} className="h-full">
                <Link
                  href={modeHref(mode, query)}
                  aria-current={isActive ? "page" : undefined}
                  aria-keyshortcuts={mode.hotkey}
                  className={cn(
                    "relative flex h-full items-center justify-center gap-1.5 px-2 text-[13px] font-medium whitespace-nowrap text-text-secondary [font-stretch:85%] hover:bg-surface-raised hover:text-text-primary xl:px-[9px] xl:text-[14px] xl:[font-stretch:100%]",
                    isActive && "font-semibold text-text-primary",
                  )}
                >
                  <Kbd
                    inverted={isActive}
                    className={cn("hidden xl:inline-grid", !isActive && "text-text-tertiary")}
                  >
                    {mode.hotkey}
                  </Kbd>
                  <span>{mode.label}</span>
                  {isActive ? (
                    <span
                      aria-hidden
                      className="absolute inset-x-2 -bottom-px h-[3px] bg-text-primary"
                    />
                  ) : null}
                </Link>
              </Tooltip>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function ModeTabBar() {
  const activeMode = useActiveMode();
  const query = useViewQuery();

  return (
    <nav
      aria-label="Режимы"
      className="border-t border-line-control bg-surface-panel pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="grid h-[58px] grid-cols-5">
        {WORKSPACE_MODES.map((mode) => {
          const isActive = activeMode?.id === mode.id;
          const Icon = ModeIcons[mode.id];
          return (
            <li key={mode.id}>
              <Link
                href={modeHref(mode, query)}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "relative flex h-full flex-col items-center justify-center gap-1 text-[11px] font-medium text-text-secondary [font-stretch:85%]",
                  isActive && "bg-surface-raised font-semibold text-text-primary",
                )}
              >
                {isActive ? (
                  <span
                    aria-hidden
                    className="absolute inset-x-3 -top-px h-[3px] bg-text-primary"
                  />
                ) : null}
                <Icon size={20} />
                <span>{mode.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
