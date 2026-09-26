"use client";

import type { CSSProperties } from "react";
import { useCandidates } from "@/data/candidates";
import { useCapability } from "@/features/system/use-capabilities";
import { cn } from "@/ui/cn";
import { DemoTag } from "@/ui/demo-mark";
import { IconSocket } from "@/ui/icons";

type StampVariant = "demo" | "planned";

const STAMP_COPY: Readonly<Record<StampVariant, { lead: string; tail: string }>> = {
  demo: { lead: "Демо-объекты на карте", tail: "не результат модели" },
  planned: { lead: "Детектор не подключён", tail: "реальные: снимок, маска качества, измерения" },
};

function useStampVariant(): StampVariant | null {
  const origin = useCandidates().origin;
  const detector = useCapability("debris_detection");
  if (origin === "api") return null;
  if (origin === "demo") return "demo";
  return detector === "available" ? null : "planned";
}

type MapStampProps = { align: "center" | "start"; style: CSSProperties };

export function MapStamp({ align, style }: MapStampProps) {
  const variant = useStampVariant();
  if (!variant) return null;
  const copy = STAMP_COPY[variant];
  return (
    <div
      className={cn(
        "@container absolute flex",
        align === "center" ? "justify-center" : "justify-start",
      )}
      style={style}
    >
      <p
        className={cn(
          "flex h-6 max-w-full items-center gap-1.5 border bg-surface-panel pr-2 text-[12px] leading-4 whitespace-nowrap",
          variant === "demo"
            ? "border-line-hairline pl-[3px] text-text-primary"
            : "border-dashed border-line-control pl-1.5 text-text-secondary",
        )}
      >
        {variant === "demo" ? <DemoTag /> : <IconSocket className="shrink-0 text-text-tertiary" />}
        <span>{copy.lead}</span>
        <span className="hidden text-text-secondary @[27rem]:inline">· {copy.tail}</span>
      </p>
    </div>
  );
}
