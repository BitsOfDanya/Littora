import { create } from "zustand";
import type { WorkspaceModeId } from "@/config/modes";

export type SheetView = "layers" | "inspector";

export type SheetDetent = "closed" | "peek" | "half" | "full";

type ShellUiStore = {
  shortcutSheetOpen: boolean;
  queueOpenByMode: Readonly<Partial<Record<WorkspaceModeId, boolean>>>;
  sheetView: SheetView;
  sheetDetent: SheetDetent;
  setShortcutSheetOpen: (open: boolean) => void;
  setQueueOpen: (mode: WorkspaceModeId, open: boolean) => void;
  showSheet: (view: SheetView, detent?: SheetDetent) => void;
  setSheetDetent: (detent: SheetDetent) => void;
  updateSheetDetent: (update: (detent: SheetDetent) => SheetDetent) => void;
};

export const useShellUiStore = create<ShellUiStore>()((set) => ({
  shortcutSheetOpen: false,
  queueOpenByMode: {},
  sheetView: "layers",
  sheetDetent: "closed",
  setShortcutSheetOpen: (shortcutSheetOpen) => set({ shortcutSheetOpen }),
  setQueueOpen: (mode, open) =>
    set((state) => ({ queueOpenByMode: { ...state.queueOpenByMode, [mode]: open } })),
  showSheet: (sheetView, detent) =>
    set((state) => ({
      sheetView,
      sheetDetent: detent ?? (state.sheetDetent === "closed" ? "peek" : state.sheetDetent),
    })),
  setSheetDetent: (sheetDetent) => set({ sheetDetent }),
  updateSheetDetent: (update) => set((state) => ({ sheetDetent: update(state.sheetDetent) })),
}));
