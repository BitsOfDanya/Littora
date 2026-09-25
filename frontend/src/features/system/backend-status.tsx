"use client";

import { ApiError, ApiUnreachableError } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format/numbers";
import { formatUtcDateTime, formatUtcTime } from "@/lib/format/time";
import { cn } from "@/ui/cn";
import { IconAlarm, IconCaution, IconRing } from "@/ui/icons";
import { KeyValue, KeyValueList } from "@/ui/key-value";
import { PlannedTag } from "@/ui/planned";
import { Caps } from "@/ui/section";
import { CAPABILITY_LABELS, useCapabilitySummary } from "./use-capabilities";
import type { ApiState, ApiStatus } from "./use-api-status";

const STATE_WORD: Record<ApiState, string> = {
  checking: "проверка",
  online: "в сети",
  slow: "медленно отвечает",
  offline: "недоступен",
};

function describeError(error: unknown): string {
  if (error instanceof ApiUnreachableError) return "нет связи";
  if (error instanceof ApiError) return `ошибка ${error.status}`;
  return "ошибка ответа";
}

function utcClock(timestamp: number): string {
  return formatUtcTime(new Date(timestamp).toISOString());
}

export function ApiStatusGlyph({ state, size = 12 }: { state: ApiState; size?: number }) {
  if (state === "offline")
    return (
      <IconAlarm
        size={size}
        fill="currentColor"
        fillOpacity={0.28}
        className="shrink-0 text-state-alarm"
      />
    );
  if (state === "slow")
    return (
      <IconCaution
        size={size}
        fill="currentColor"
        fillOpacity={0.28}
        className="shrink-0 text-state-caution"
      />
    );
  return (
    <IconRing
      size={size}
      className={cn(
        "shrink-0",
        state === "checking" ? "text-text-disabled" : "text-text-secondary",
      )}
    />
  );
}

function retryText(retryInSeconds: number | null): string | null {
  if (retryInSeconds === null) return null;
  return retryInSeconds > 0 ? `повтор через ${retryInSeconds} с` : "повтор…";
}

type ApiStatusParts = { main: string; contact: string | null; retry: string | null };

function apiStatusParts({
  state,
  health,
  lastContactAt,
  retryInSeconds,
}: ApiStatus): ApiStatusParts {
  if (state === "checking") return { main: "Проверяем сервер…", contact: null, retry: null };
  if (state === "offline") {
    return {
      main: "API недоступен",
      contact: lastContactAt ? `последняя связь ${utcClock(lastContactAt)}` : null,
      retry: retryText(retryInSeconds),
    };
  }
  const latency = `${formatNumber(health?.latencyMs ?? 0)} мс`;
  return {
    main: state === "slow" ? `API медленно отвечает · ${latency}` : `API в сети · ${latency}`,
    contact: null,
    retry: null,
  };
}

type ApiStatusLabelProps = {
  status: ApiStatus;
  versionClassName?: string;
  detailClassName?: string;
  className?: string;
};

export function ApiStatusLabel({
  status,
  versionClassName,
  detailClassName,
  className,
}: ApiStatusLabelProps) {
  const reachable = status.state === "online" || status.state === "slow";
  const { main, contact, retry } = apiStatusParts(status);
  return (
    <span
      className={cn(
        "inline-flex min-w-0 items-center gap-1.5 whitespace-nowrap",
        status.state === "offline" && "text-state-alarm",
        status.state === "slow" && "text-state-caution",
        className,
      )}
    >
      <ApiStatusGlyph state={status.state} />
      <span>{main}</span>
      {contact ? <span className={detailClassName}>· {contact}</span> : null}
      {retry ? <span>· {retry}</span> : null}
      {reachable && status.health && versionClassName !== undefined ? (
        <span className={versionClassName}>· v{status.health.version}</span>
      ) : null}
    </span>
  );
}

function HealthDetails({ status }: { status: ApiStatus }) {
  const { health, state, lastCheckAt, lastContactAt, error } = status;
  return (
    <section className="flex flex-col gap-1 px-3 py-2.5">
      <header className="flex items-baseline gap-2">
        <Caps>Сервер</Caps>
        <span className="font-mono text-[11px] text-text-tertiary">GET /api/v1/health</span>
      </header>
      <KeyValueList>
        <KeyValue label="Состояние">
          <span
            className={cn(
              state === "offline" && "text-state-alarm",
              state === "slow" && "text-state-caution",
            )}
          >
            {state === "offline"
              ? `${STATE_WORD[state]} · ${describeError(error)}`
              : STATE_WORD[state]}
          </span>
        </KeyValue>
        {health ? (
          <>
            <KeyValue label="Сервис">{health.service}</KeyValue>
            <KeyValue label="Версия">{health.version}</KeyValue>
            <KeyValue label="Окружение">{health.environment}</KeyValue>
            <KeyValue label="Время сервера">{formatUtcDateTime(health.timestamp)}</KeyValue>
            <KeyValue label="Задержка" unit="мс">
              {formatNumber(health.latencyMs)}
            </KeyValue>
          </>
        ) : null}
        <KeyValue label="Последняя проверка">{lastCheckAt ? utcClock(lastCheckAt) : "—"}</KeyValue>
        {state === "offline" ? (
          <KeyValue label="Последняя связь">
            {lastContactAt ? utcClock(lastContactAt) : "—"}
          </KeyValue>
        ) : null}
      </KeyValueList>
    </section>
  );
}

function CapabilityDetails() {
  const summary = useCapabilitySummary();
  return (
    <section className="flex flex-col gap-1 border-t border-line-hairline px-3 py-2.5">
      <header className="flex items-baseline gap-2">
        <Caps>Модули анализа</Caps>
        <span className="font-mono text-[11px] text-text-tertiary">GET /api/v1/meta</span>
        <span className="ml-auto font-mono text-[11px] text-text-secondary">
          {summary.availableCount} / {summary.total}
        </span>
      </header>
      {summary.status === "error" ? (
        <p className="flex items-center gap-1.5 text-[12px] text-state-alarm">
          <IconAlarm size={12} />
          Не удалось получить /api/v1/meta
        </p>
      ) : null}
      {summary.status === "loading" ? (
        <p className="text-[12px] text-text-tertiary">Проверяем возможности сервера…</p>
      ) : null}
      <ul className="flex flex-col">
        {summary.entries.map(({ key, availability }) => (
          <li
            key={key}
            className="flex min-h-7 items-center gap-2 border-b border-line-hairline last:border-b-0"
          >
            <span className="flex min-w-0 flex-1 flex-col py-1">
              <span className="text-[12px] text-text-primary">{CAPABILITY_LABELS[key]}</span>
              <span className="font-mono text-[11px] text-text-tertiary">{key}</span>
            </span>
            {availability === "available" ? (
              <span className="font-mono text-[11px] text-text-primary">готово</span>
            ) : availability === "planned" ? (
              <PlannedTag capability={key} />
            ) : (
              <span className="font-mono text-[11px] text-text-tertiary">—</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function SystemDetails({ status }: { status: ApiStatus }) {
  return (
    <div className="flex flex-col">
      <HealthDetails status={status} />
      <CapabilityDetails />
    </div>
  );
}
