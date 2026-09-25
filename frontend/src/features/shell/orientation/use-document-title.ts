"use client";

import { useEffect } from "react";
import { findAoi } from "@/config/aois";
import { SITE } from "@/config/site";
import { useWorkspaceStore } from "@/state/workspace-store";
import { useActiveMode } from "./modes";

export function useDocumentTitle(): void {
  const mode = useActiveMode();
  const aoiName = findAoi(useWorkspaceStore((state) => state.aoiId))?.name;

  useEffect(() => {
    const title = [mode?.label, aoiName, SITE.product].filter(Boolean).join(" · ");
    const enforce = () => {
      if (document.title !== title) document.title = title;
    };
    enforce();
    const observer = new MutationObserver(enforce);
    observer.observe(document.head, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [mode?.label, aoiName]);
}
