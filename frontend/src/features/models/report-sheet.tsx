"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import styles from "./report.module.css";

const EASE_STD = [0.2, 0, 0.38, 0.9] as const;

export function ReportScrim() {
  const reduced = useReducedMotion();
  return (
    <motion.div
      aria-hidden
      initial={reduced ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.15, ease: EASE_STD }}
      className="pointer-events-auto absolute inset-0 z-20 bg-[var(--map-scrim)]"
    />
  );
}

export function ReportSheet({ titleId, children }: { titleId: string; children: ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <motion.section
      aria-labelledby={titleId}
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, ease: EASE_STD }}
      className="pointer-events-auto absolute inset-0 z-20 flex bg-surface-panel text-text-primary md:inset-5 md:mx-auto md:max-w-[1040px] md:border md:border-text-primary md:p-[3px]"
    >
      <div
        tabIndex={0}
        className={`@container min-h-0 flex-1 overflow-y-auto overscroll-contain md:border md:border-line-hairline ${styles.scroller}`}
      >
        {children}
      </div>
    </motion.section>
  );
}
