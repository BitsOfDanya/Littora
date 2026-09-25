"use client";

import { useCallback, useRef } from "react";
import type { WorkspaceModeId } from "@/config/modes";
import { QueueColumn } from "../queue/queue-column";
import { queueHasRail } from "../queue/use-queue";
import { useRegionTarget } from "../shell-slots";
import styles from "../workspace-shell.module.css";
import { useModeCrossfade } from "./motion";
import type { ShellLayout } from "./use-environment";

export function RailFrame({
  mode,
  layout,
}: {
  mode: WorkspaceModeId | undefined;
  layout: ShellLayout;
}) {
  const registerTarget = useRegionTarget("rail");
  const contentRef = useRef<HTMLDivElement | null>(null);
  const setContent = useCallback(
    (element: HTMLDivElement | null) => {
      contentRef.current = element;
      registerTarget(element);
    },
    [registerTarget],
  );

  useModeCrossfade(contentRef, mode);

  return (
    <section aria-label="Шкала времени" className={styles.rail}>
      {mode && queueHasRail(mode) ? <QueueColumn mode={mode} layout={layout} /> : null}
      <div ref={setContent} className="min-w-0 flex-1 overflow-hidden" />
    </section>
  );
}
