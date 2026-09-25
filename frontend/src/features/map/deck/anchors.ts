import { ANCHOR_DATA_LAYER_ID, ANCHOR_LABELS_LAYER_ID } from "@/config/basemaps";

export type Anchored = { beforeId?: string };

export const UNDER_COASTLINE: Anchored = { beforeId: ANCHOR_DATA_LAYER_ID };

export const UNDER_LABELS: Anchored = { beforeId: ANCHOR_LABELS_LAYER_ID };
