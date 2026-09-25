import { create } from "zustand";

type StatusHintStore = {
  hint: string | null;
  setHint: (hint: string | null) => void;
};

export const useStatusHintStore = create<StatusHintStore>()((set) => ({
  hint: null,
  setHint: (hint) => set({ hint }),
}));
