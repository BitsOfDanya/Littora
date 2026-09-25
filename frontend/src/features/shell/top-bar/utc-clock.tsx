"use client";

import { useState, useSyncExternalStore } from "react";
import { Tooltip } from "@/ui/tooltip";

const MINUTE_MS = 60_000;

const pad = (value: number) => String(value).padStart(2, "0");

function subscribeToMinutes(onTick: () => void): () => void {
  let interval = 0;
  const timeout = window.setTimeout(
    () => {
      onTick();
      interval = window.setInterval(onTick, MINUTE_MS);
    },
    MINUTE_MS - (Date.now() % MINUTE_MS),
  );
  return () => {
    window.clearTimeout(timeout);
    window.clearInterval(interval);
  };
}

function currentMinute(): number {
  return Math.floor(Date.now() / MINUTE_MS);
}

function utcMinuteLabel(minute: number): string {
  const date = new Date(minute * MINUTE_MS);
  return `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}Z`;
}

function detailLabel(date: Date): string {
  const utc = `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())} UTC`;
  return `${utc} · местное ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function UtcClock() {
  const minute = useSyncExternalStore(subscribeToMinutes, currentMinute, () => null);
  const [detail, setDetail] = useState("Всемирное время UTC");
  const refreshDetail = () => setDetail(detailLabel(new Date()));

  return (
    <Tooltip content={detail}>
      <time
        tabIndex={0}
        aria-label={minute === null ? "Время UTC" : `Время ${utcMinuteLabel(minute)} UTC`}
        dateTime={minute === null ? undefined : new Date(minute * MINUTE_MS).toISOString()}
        onPointerEnter={refreshDetail}
        onFocus={refreshDetail}
        className="inline-flex h-7 items-center px-1 font-mono text-[13px] font-medium text-text-primary"
      >
        {minute === null ? "--:--Z" : utcMinuteLabel(minute)}
      </time>
    </Tooltip>
  );
}
