import type { ReactNode } from "react";
import { cn } from "./cn";

type PanelSectionProps = {
  id?: string;
  title?: ReactNode;
  caps?: ReactNode;
  index?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function PanelSection({
  id,
  title,
  caps,
  index,
  aside,
  children,
  className,
}: PanelSectionProps) {
  return (
    <section
      id={id}
      className={cn(
        "flex scroll-mt-10 flex-col gap-2 border-b border-line-hairline px-4 py-3",
        className,
      )}
    >
      {title || caps || aside ? (
        <header className="flex items-baseline gap-2">
          {index ? <span className="font-mono text-[11px] text-text-tertiary">{index}</span> : null}
          {caps ? <Caps>{caps}</Caps> : null}
          {title ? (
            <h3 className="font-serif text-[16px] leading-[19px] font-medium italic">{title}</h3>
          ) : null}
          {aside ? <div className="ml-auto flex items-center gap-2">{aside}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function Caps({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "text-[11px] leading-[14px] font-semibold tracking-[0.07em] text-text-tertiary uppercase [font-stretch:88%]",
        className,
      )}
    >
      {children}
    </span>
  );
}

export const Eyebrow = Caps;
