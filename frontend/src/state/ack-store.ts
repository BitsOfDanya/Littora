import { create } from "zustand";

export const OPERATOR_ACTOR = "оператор";

export type Acknowledgement = { at: string; actor: string };

type AckStore = {
  acknowledgements: Readonly<Record<string, Acknowledgement>>;
  acknowledge: (eventIds: readonly string[], at?: Date) => void;
};

export const useAckStore = create<AckStore>()((set) => ({
  acknowledgements: {},
  acknowledge: (eventIds, at = new Date()) =>
    set((state) => {
      const pending = eventIds.filter((id) => !state.acknowledgements[id]);
      if (pending.length === 0) return state;
      const stamp: Acknowledgement = { at: at.toISOString(), actor: OPERATOR_ACTOR };
      return {
        acknowledgements: {
          ...state.acknowledgements,
          ...Object.fromEntries(pending.map((id) => [id, stamp])),
        },
      };
    }),
}));

export function useAcknowledgement(eventId: string): Acknowledgement | undefined {
  return useAckStore((state) => state.acknowledgements[eventId]);
}
