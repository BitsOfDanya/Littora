"use client";

import { type ThemeId, usePreferencesStore } from "@/state/preferences-store";
import { cn } from "@/ui/cn";
import { IconMoon, IconSun } from "@/ui/icons";
import { Tooltip } from "@/ui/tooltip";
import { useHydrated } from "../layout/use-environment";

const THEMES: readonly { id: ThemeId; label: string; Icon: typeof IconSun }[] = [
  { id: "day", label: "День", Icon: IconSun },
  { id: "night", label: "Ночь", Icon: IconMoon },
];

export function ThemeSeg() {
  const storedTheme = usePreferencesStore((state) => state.theme);
  const setTheme = usePreferencesStore((state) => state.setTheme);
  const theme = useHydrated() ? storedTheme : null;

  return (
    <Tooltip content="Тема: День или Ночь" shortcut="T">
      <div
        role="radiogroup"
        aria-label="Тема"
        aria-keyshortcuts="T"
        className="inline-flex h-7 gap-px rounded-[var(--radius-ctl)] border border-line-control bg-surface-sunken p-px"
      >
        {THEMES.map(({ id, label, Icon }) => {
          const selected = theme === id;
          return (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={label}
              onClick={() => setTheme(id)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[1px] px-1.5 text-[12px] text-text-secondary transition-colors duration-[var(--t-2)] hover:bg-surface-raised hover:text-text-primary",
                selected &&
                  "bg-surface-raised font-semibold text-text-primary shadow-[inset_0_0_0_1px_var(--text-primary)] xl:px-2",
              )}
            >
              <Icon size={14} />
              {selected ? <span className="hidden xl:inline">{label}</span> : null}
            </button>
          );
        })}
      </div>
    </Tooltip>
  );
}

export function ThemeToggleButton() {
  const storedTheme = usePreferencesStore((state) => state.theme);
  const theme = useHydrated() ? storedTheme : "night";
  const toggle = usePreferencesStore((state) => state.toggleTheme);
  const next = theme === "night" ? "День" : "Ночь";
  return (
    <button
      type="button"
      aria-label={`Тема: ${theme === "night" ? "Ночь" : "День"}. Переключить на «${next}»`}
      onClick={toggle}
      className="grid size-10 shrink-0 place-items-center text-text-primary hover:bg-surface-raised"
    >
      {theme === "night" ? <IconMoon size={20} /> : <IconSun size={20} />}
    </button>
  );
}
