"use client";

import Link from "next/link";
import { SITE } from "@/config/site";
import { useReturnToGate } from "@/features/gate/use-return-to-gate";
import { BrandMark } from "@/ui/brand-mark";
import { Tooltip } from "@/ui/tooltip";

const SHORT_VERSION = SITE.version.split(".").slice(0, 2).join(".");

export function Brand() {
  const returnToGate = useReturnToGate();
  return (
    <Tooltip content="К экрану входа" className="h-full shrink-0">
      <Link
        href="/"
        aria-label={`${SITE.product} ${SITE.version} — к экрану входа`}
        onClick={(event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
          event.preventDefault();
          returnToGate();
        }}
        className="flex h-full items-center gap-2 border-r border-line-hairline px-3 text-text-primary hover:bg-surface-raised"
      >
        <BrandMark height={16} />
        <span className="hidden font-serif text-[19px] leading-none font-semibold italic [font-variation-settings:'opsz'_40] sm:inline md:text-[21px]">
          {SITE.product}
        </span>
        <span className="hidden pt-1 font-mono text-[11px] leading-none text-text-tertiary 2xl:inline">
          {SHORT_VERSION}
        </span>
      </Link>
    </Tooltip>
  );
}
