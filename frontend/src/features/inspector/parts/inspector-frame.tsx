"use client";

import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";
import { IconButton } from "@/ui/button";
import { cn } from "@/ui/cn";
import { DemoRibbon } from "@/ui/demo-mark";
import { IconClose } from "@/ui/icons";
import { Caps } from "@/ui/section";
import { Breadcrumbs, type Crumb } from "./breadcrumbs";

type InspectorFrameProps = {
  label: string;
  eyebrow: string;
  crumbs: readonly Crumb[];
  demoSource?: string | null;
  onClose?: () => void;
  header?: ReactNode;
  nav?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  selectionRule?: boolean;
  pin?: "all" | "nav";
};

const NAV_HEIGHT_PX = 32;

function usePinnedHeight() {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(32);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setHeight(element.offsetHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, height };
}

function TopBand({
  crumbs,
  demoSource,
  onClose,
}: Pick<InspectorFrameProps, "crumbs" | "demoSource" | "onClose">) {
  return (
    <>
      <div className="flex h-8 items-center gap-2 border-b border-line-hairline pr-2 pl-4">
        <Breadcrumbs crumbs={crumbs} className="flex-1" />
        {onClose ? (
          <IconButton label="Закрыть" shortcut="Esc" size="sm" onClick={onClose}>
            <IconClose />
          </IconButton>
        ) : null}
      </div>
      {demoSource !== undefined && demoSource !== null ? <DemoRibbon source={demoSource} /> : null}
    </>
  );
}

function HeaderBlock({
  eyebrow,
  header,
  selectionRule,
}: Pick<InspectorFrameProps, "eyebrow" | "header" | "selectionRule">) {
  return (
    <header
      className={cn(
        "flex flex-col gap-1.5 border-b border-line-hairline px-4 pt-3 pb-3",
        selectionRule && "border-l-[3px] border-l-accent-selection pl-[13px]",
      )}
    >
      <Caps>{eyebrow}</Caps>
      {header}
    </header>
  );
}

function Footer({ footer }: { footer: ReactNode }) {
  return (
    <footer className="sticky bottom-0 z-10 flex flex-wrap gap-2 border-t border-line-hairline bg-surface-panel p-3">
      {footer}
    </footer>
  );
}

export function InspectorFrame({
  label,
  eyebrow,
  crumbs,
  demoSource,
  onClose,
  header,
  nav,
  footer,
  children,
  selectionRule,
  pin = "all",
}: InspectorFrameProps) {
  const { ref: pinnedRef, height: pinnedHeight } = usePinnedHeight();

  if (pin === "all")
    return (
      <article aria-label={label} className="flex min-h-full flex-col bg-surface-panel">
        <div className="sticky top-0 z-10 bg-surface-panel">
          <TopBand crumbs={crumbs} demoSource={demoSource} onClose={onClose} />
          <HeaderBlock eyebrow={eyebrow} header={header} selectionRule={selectionRule} />
          {nav}
        </div>
        <div className="flex-1">{children}</div>
        {footer ? <Footer footer={footer} /> : null}
      </article>
    );

  const style = { "--inspector-pin": `${pinnedHeight + NAV_HEIGHT_PX}px` } as CSSProperties;
  return (
    <article aria-label={label} className="flex min-h-full flex-col bg-surface-panel" style={style}>
      <div ref={pinnedRef} className="sticky top-0 z-20 bg-surface-panel">
        <TopBand crumbs={crumbs} demoSource={demoSource} onClose={onClose} />
      </div>
      <HeaderBlock eyebrow={eyebrow} header={header} selectionRule={selectionRule} />
      {nav ? (
        <div className="sticky z-10 bg-surface-panel" style={{ top: pinnedHeight }}>
          {nav}
        </div>
      ) : null}
      <div className="flex-1">{children}</div>
      {footer ? <Footer footer={footer} /> : null}
    </article>
  );
}
