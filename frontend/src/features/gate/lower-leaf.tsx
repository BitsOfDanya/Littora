"use client";

import { motion } from "motion/react";
import type { Ref } from "react";
import { SITE } from "@/config/site";
import { Kbd } from "@/ui/kbd";
import { GATE_COPY } from "./gate-copy";
import { useGateValue } from "./use-gate-value";

function LockIcon() {
  return (
    <svg
      width={20}
      height={20}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="square"
      aria-hidden
      focusable={false}
    >
      <path d="M1.5 8h13M5 4.5L8 1.5l3 3M5 11.5l3 3 3-3" />
    </svg>
  );
}

type EnterButtonProps = {
  opening: boolean;
  onOpen: () => void;
  buttonRef: Ref<HTMLButtonElement>;
};

function EnterButton({ opening, onOpen, buttonRef }: EnterButtonProps) {
  const shift = useGateValue((frame) => frame.buttonShiftPx);
  return (
    <motion.button
      ref={buttonRef}
      type="button"
      onClick={onOpen}
      aria-busy={opening || undefined}
      aria-keyshortcuts="Enter"
      style={{ y: shift }}
      className="inline-flex h-[52px] w-full shrink-0 items-center justify-center gap-3.5 rounded-[var(--radius-ctl)] bg-primary-fill px-5 text-[16px] font-semibold text-primary-text transition-colors duration-(--t-2) ease-(--e-std) hover:bg-[#2B3134] md:h-14 md:w-auto md:justify-start md:pr-4 md:pl-[22px] md:text-[17px]"
    >
      <LockIcon />
      <span>{opening ? GATE_COPY.buttonOpening : GATE_COPY.button}</span>
      <Kbd className="hidden h-5 min-w-[38px] border-[rgba(245,244,239,.45)] bg-transparent text-primary-text md:inline-grid">
        Enter
      </Kbd>
    </motion.button>
  );
}

export function LowerLeafContent(button: EnterButtonProps) {
  return (
    <div className="absolute inset-0 flex flex-col pt-5 pr-[calc(var(--gauge-col)+16px)] pb-4 pl-4 md:pt-8 md:pr-[calc(var(--gauge-col)+var(--gate-frame)+24px)] md:pb-[calc(var(--gate-frame)+12px)] md:pl-[calc(var(--gate-frame)+var(--gate-pad))]">
      <p className="max-w-[820px] text-[19px] leading-[25px] font-medium text-balance text-(--gate-ink) md:text-[clamp(19px,1.85vw,27px)] md:leading-[1.3]">
        {SITE.claim}
      </p>
      <p className="mt-2 max-w-[620px] text-[13px] leading-5 text-(--gate-ink) md:mt-3 md:text-[15px] md:leading-6">
        {SITE.description}
      </p>
      <div className="mt-5 md:mt-7">
        <EnterButton {...button} />
      </div>
    </div>
  );
}
