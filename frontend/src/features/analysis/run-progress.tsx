"use client";

import { useEffect, useState } from "react";

const TICK_MS = 1_000;
const QUIET_MS = 10_000;

function clock(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function RunProgress({ startedAt }: { startedAt: number | null }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (startedAt === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  if (startedAt === null || now - startedAt < QUIET_MS) return null;
  return (
    <p className="text-[12px] leading-4 text-text-secondary">
      Идёт расчёт · <span className="font-mono tabular-nums">{clock(now - startedAt)}</span>. Каналы
      снимка читаются из облачного архива Sentinel-2 — первый анализ сцены занимает несколько минут.
      Результат сохранится на сервере, даже если уйти из режима.
    </p>
  );
}
