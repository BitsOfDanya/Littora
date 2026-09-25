"use client";

import { useEffect, useState } from "react";
import { IconButton } from "@/ui/button";
import { IconCheck, IconCopy } from "@/ui/icons";

const CONFIRM_MS = 1200;

export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), CONFIRM_MS);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <span className="inline-flex items-center gap-1.5">
      <IconButton label={label} size="sm" onClick={copy}>
        {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
      </IconButton>
      <span aria-live="polite" className="text-[12px] text-text-secondary">
        {copied ? "Скопировано" : ""}
      </span>
    </span>
  );
}
