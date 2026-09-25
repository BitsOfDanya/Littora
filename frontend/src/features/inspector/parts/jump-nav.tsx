"use client";

import { useEffect, useState } from "react";
import { cn } from "@/ui/cn";

export type JumpTarget = { id: string; label: string };

export function JumpNav({
  targets,
  onNavigate,
  dense,
}: {
  targets: readonly JumpTarget[];
  onNavigate?: (id: string) => void;
  dense?: boolean;
}) {
  const [activeId, setActiveId] = useState(targets[0]?.id ?? null);

  useEffect(() => {
    const elements = targets
      .map((target) => document.getElementById(target.id))
      .filter((element): element is HTMLElement => Boolean(element));
    if (!elements.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveId(visible[0].target.id);
      },
      { rootMargin: "-96px 0px -60% 0px" },
    );
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [targets]);

  return (
    <nav
      aria-label="Разделы"
      className={cn(
        "flex h-8 [scrollbar-width:none] items-stretch overflow-x-auto border-b border-line-hairline px-4 text-[12px]",
        dense ? "gap-2.5" : "gap-3",
      )}
    >
      {targets.map((target) => (
        <a
          key={target.id}
          href={`#${target.id}`}
          onClick={(event) => {
            event.preventDefault();
            onNavigate?.(target.id);
            document
              .getElementById(target.id)
              ?.scrollIntoView({ block: "start", behavior: "smooth" });
            setActiveId(target.id);
          }}
          aria-current={activeId === target.id ? "true" : undefined}
          className={cn(
            "flex items-center border-b-2 border-transparent whitespace-nowrap text-text-secondary hover:text-text-primary",
            activeId === target.id && "border-text-primary text-text-primary",
          )}
        >
          {target.label}
        </a>
      ))}
    </nav>
  );
}
