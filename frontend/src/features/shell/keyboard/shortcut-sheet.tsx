"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ApiStatusLabel } from "@/features/system/backend-status";
import { useApiStatus } from "@/features/system/use-api-status";
import { useShellUiStore } from "@/state/shell-ui-store";
import { IconButton } from "@/ui/button";
import { IconClose, IconSearch } from "@/ui/icons";
import { Kbd } from "@/ui/kbd";
import { PlannedTag } from "@/ui/planned";
import { Caps } from "@/ui/section";
import { useIsMacPlatform } from "../layout/use-environment";
import { DemoSwitch } from "../top-bar/demo-switch";
import { useEscapeLayer } from "./escape-stack";
import {
  MOD_KEY_PLACEHOLDER,
  type Shortcut,
  SHORTCUT_GROUP_LABELS,
  SHORTCUT_GROUP_ORDER,
  SHORTCUTS,
  shortcutMatches,
} from "./shortcuts";

function Combo({ keys, modLabel }: { keys: readonly string[]; modLabel: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      {keys.map((key) => (
        <Kbd key={key}>{key === MOD_KEY_PLACEHOLDER ? modLabel : key}</Kbd>
      ))}
    </span>
  );
}

function ShortcutRow({ shortcut, modLabel }: { shortcut: Shortcut; modLabel: string }) {
  return (
    <li className="flex min-h-8 items-center gap-3 border-b border-line-hairline py-1 last:border-b-0">
      <span className="min-w-0 flex-1 text-[13px] text-text-primary">{shortcut.action}</span>
      {shortcut.planned ? <PlannedTag capability={shortcut.planned} /> : null}
      <span className="flex shrink-0 items-center gap-1.5 text-[11px] text-text-tertiary">
        {shortcut.combos.map((combo, index) => (
          <span key={combo.join("+")} className="inline-flex items-center gap-1.5">
            {index > 0 ? <span aria-hidden>/</span> : null}
            <Combo keys={combo} modLabel={modLabel} />
          </span>
        ))}
      </span>
    </li>
  );
}

function ShortcutList({ query, modLabel }: { query: string; modLabel: string }) {
  const matches = SHORTCUTS.filter((shortcut) => shortcutMatches(shortcut, query));
  if (matches.length === 0)
    return (
      <p className="px-5 py-6 text-[13px] text-text-secondary">
        Ничего не найдено. Попробуйте название действия или букву клавиши.
      </p>
    );
  return (
    <div className="flex flex-col gap-4 px-5 py-4">
      {SHORTCUT_GROUP_ORDER.map((group) => {
        const rows = matches.filter((shortcut) => shortcut.group === group);
        if (rows.length === 0) return null;
        return (
          <section
            key={group}
            aria-label={SHORTCUT_GROUP_LABELS[group]}
            className="flex flex-col gap-1"
          >
            <Caps>{SHORTCUT_GROUP_LABELS[group]}</Caps>
            <ul className="flex flex-col">
              {rows.map((shortcut) => (
                <ShortcutRow
                  key={`${shortcut.group}-${shortcut.action}`}
                  shortcut={shortcut}
                  modLabel={modLabel}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function PhoneStatusRow() {
  const status = useApiStatus();
  return (
    <div className="flex items-center gap-3 border-b border-line-hairline px-5 py-2 text-[12px] text-text-secondary md:hidden">
      <ApiStatusLabel status={status} className="min-w-0 flex-1" />
      <DemoSwitch size="sheet" />
    </div>
  );
}

export function ShortcutSheet() {
  const open = useShellUiStore((state) => state.shortcutSheetOpen);
  const setOpen = useShellUiStore((state) => state.setShortcutSheetOpen);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const titleId = useId();
  const modLabel = useIsMacPlatform() ? "⌘" : "Ctrl";

  useEscapeLayer(open, () => setOpen(false));

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onClose={() => {
        setOpen(false);
        setQuery("");
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) setOpen(false);
      }}
      className="fixed inset-x-0 top-[88px] mx-auto max-h-[calc(100dvh-120px)] w-[min(640px,calc(100%-24px))] overflow-hidden rounded-[var(--radius-pop)] bg-surface-panel p-0 text-text-primary shadow-popover backdrop:bg-black/40 max-md:top-3"
    >
      <div className="flex max-h-[calc(100dvh-120px)] flex-col">
        <header className="flex items-center gap-3 border-b border-line-control px-5 pt-4 pb-3">
          <h2 id={titleId} className="font-serif text-[20px] leading-6 font-medium italic">
            Как пользоваться и клавиши
          </h2>
          <span className="text-[12px] text-text-tertiary">
            по физическим клавишам — работают и в русской раскладке
          </span>
          <IconButton
            label="Закрыть"
            shortcut="Esc"
            size="sm"
            className="ml-auto"
            onClick={() => setOpen(false)}
          >
            <IconClose />
          </IconButton>
        </header>
        <PhoneStatusRow />
        <ol className="flex list-decimal flex-col gap-1 border-b border-line-hairline py-3 pr-5 pl-9 text-[13px] leading-5 text-text-secondary">
          <li>Выберите район сверху и дату снимка на ленте внизу карты.</li>
          <li>
            Нажмите «Анализ района»: сервис проверит облака, найдёт места, похожие на скопления
            мусора, и оценит концентрацию по полевым данным.
          </li>
          <li>
            Щёлкните зону на карте: вероятность, площадь, доля покрытия, признаки ложной зоны и
            ближайшие измерения с судна.
          </li>
          <li>
            Слои и композиты (RGB, ложные цвета, FDI, NDVI) — в панели слоёв; I — лупа по пикселю, R
            — линейка.
          </li>
          <li>
            Выгрузка GeoJSON и CSV — внизу панели анализа; точность моделей — в режиме «Модели».
          </li>
        </ol>
        <label className="flex h-12 shrink-0 items-center gap-3 border-b border-line-hairline px-5 focus-within:shadow-[inset_0_-2px_0_var(--focus-ring)]">
          <IconSearch className="shrink-0 text-text-tertiary" />
          <span className="sr-only">Поиск по клавишам</span>
          <input
            type="search"
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Поиск по клавишам"
            className="h-full min-w-0 flex-1 bg-transparent text-[15px] text-text-primary outline-none placeholder:text-text-tertiary"
          />
        </label>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <ShortcutList query={query} modLabel={modLabel} />
        </div>
      </div>
    </dialog>
  );
}
