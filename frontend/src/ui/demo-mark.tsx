import { cn } from "./cn";

const DEFAULT_TITLE = "Демонстрационные данные интерфейса — фикстура, не результат модели";

export function DemoTag({
  title = DEFAULT_TITLE,
  label = "ДЕМО",
  className,
}: {
  title?: string;
  label?: string;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "demo-hatch inline-flex h-[18px] shrink-0 items-center rounded-[var(--radius-ctl)] border border-demo-ink px-1 font-mono text-[11px] leading-none font-medium tracking-[0.06em] text-demo-ink",
        className,
      )}
    >
      {label}
    </span>
  );
}

export function DemoRibbon({ source, className }: { source?: string; className?: string }) {
  return (
    <div
      className={cn(
        "demo-hatch flex min-h-6 flex-wrap items-center gap-x-2 border-y border-line-hairline px-4 py-1 text-[11px] text-text-secondary",
        className,
      )}
    >
      <span className="font-mono font-medium tracking-[0.06em] text-demo-ink">ДЕМО</span>
      <span>Фикстура интерфейса — не результат модели</span>
      {source ? <span className="font-mono text-text-tertiary">{source}</span> : null}
    </div>
  );
}
