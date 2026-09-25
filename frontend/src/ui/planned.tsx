import type { ReactNode } from "react";
import { cn } from "./cn";
import { IconSocket } from "./icons";

export function PlannedTag({ capability, className }: { capability: string; className?: string }) {
  return (
    <span
      title={`Возможность ${capability} ещё не подключена (planned)`}
      className={cn(
        "inline-flex h-[18px] shrink-0 items-center rounded-[var(--radius-ctl)] border border-dashed border-line-control px-1 font-mono text-[11px] leading-none text-text-tertiary",
        className,
      )}
    >
      план
    </span>
  );
}

type PlannedStateProps = {
  title: string;
  capability: string;
  status?: "planned" | "error" | "loading";
  children?: ReactNode;
  requirement?: ReactNode;
  action?: ReactNode;
  className?: string;
};

export function PlannedState({
  title,
  capability,
  status = "planned",
  children,
  requirement,
  action,
  className,
}: PlannedStateProps) {
  return (
    <section
      className={cn(
        "flex flex-col gap-2 rounded-[var(--radius-ctl)] border border-dashed border-line-control bg-surface-panel p-4",
        className,
      )}
    >
      <header className="flex items-start gap-2">
        <IconSocket className="mt-0.5 shrink-0 text-text-tertiary" />
        <h3 className="flex-1 text-[13px] font-semibold text-text-primary">{title}</h3>
        <PlannedTag capability={capability} />
      </header>
      {status === "loading" ? (
        <p className="text-[13px] text-text-secondary">Проверяем возможности сервера…</p>
      ) : null}
      {status === "error" ? (
        <p className="text-[13px] text-state-alarm">Не удалось получить /api/v1/meta</p>
      ) : null}
      {children ? <p className="text-[13px] text-text-secondary">{children}</p> : null}
      {requirement ? <p className="text-[12px] text-text-tertiary">Нужно: {requirement}</p> : null}
      <p className="font-mono text-[11px] text-text-tertiary">
        {capability} · GET /api/v1/meta → {status === "error" ? "ошибка" : "planned"}
      </p>
      {action ? <div className="pt-1">{action}</div> : null}
    </section>
  );
}
