"use client";

import type { Layer, PickingInfo } from "@deck.gl/core";
import { ClipExtension, type ClipExtensionProps } from "@deck.gl/extensions";
import { BitmapLayer, GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { useTimelineCompare } from "@/data/timeline";
import { type RealZone, toRealZones, zoneColor } from "@/features/analysis/zones";
import { withAlpha } from "@/features/map/color";
import { type Anchored, UNDER_COASTLINE, UNDER_LABELS } from "@/features/map/deck/anchors";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { type Analysis, analysisFileUrl, getAnalysis } from "@/lib/api/analyses";
import { formatNumber } from "@/lib/format/numbers";
import { queryKeys } from "@/lib/query/query-keys";
import { useLayerVisible } from "@/state/map-layers-store";
import type { ComparePair, CompareSide } from "./compare-model";
import { useCompareViewStore } from "./compare-view-store";
import { analysisOf, type LivePasses } from "./live-model";

type Bounds = [number, number, number, number];
type Corner = [number, number];
type ZoneKind = "new" | "persisting" | "disappeared" | "not_observed";
type ZoneProps = { zone: RealZone; side: CompareSide; kind: ZoneKind | null };
type ZoneFeature = GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon, ZoneProps>;
type ZoneMark = ZoneProps & { position: Corner };

const OWNER = "timeline:live";
const MAX_LAT = 85.05;
const ZONE_FILL_ALPHA = 0.3;
const ZONE_MARKER_PX = 5;
const ZONE_MARKERS_MAX_ZOOM = 14;
const clip = new ClipExtension();

const KIND_WORD: Record<ZoneKind, string> = {
  new: "новая",
  persisting: "на том же месте",
  disappeared: "исчезла",
  not_observed: "на другой дате не наблюдалась",
};

export type LiveCompareView = { aImage: boolean; bImage: boolean };

function sideBounds(dividerLng: number, side: CompareSide): Bounds {
  return side === "a"
    ? [-180, -MAX_LAT, dividerLng, MAX_LAT]
    : [dividerLng, -MAX_LAT, 180, MAX_LAT];
}

function cornersForDeck(corners: readonly (readonly number[])[]): [Corner, Corner, Corner, Corner] {
  const [topLeft, topRight, bottomRight, bottomLeft] = corners.map(
    ([lng, lat]) => [lng, lat] as Corner,
  );
  return [bottomLeft, topLeft, topRight, bottomRight];
}

function useSideAnalysis(sceneId: string | null, passes: LivePasses): Analysis | null {
  const analysisId = sceneId ? (analysisOf(passes, sceneId)?.id ?? null) : null;
  const query = useQuery({
    queryKey: queryKeys.analyses.detail(analysisId ?? ""),
    queryFn: ({ signal }) => getAnalysis(analysisId ?? "", signal),
    enabled: analysisId !== null,
    staleTime: Infinity,
  });
  return analysisId && query.data?.id === analysisId ? query.data : null;
}

export function liveCompareView(pair: ComparePair | null, passes: LivePasses): LiveCompareView {
  const has = (sceneId: string | undefined) =>
    Boolean(sceneId && analysisOf(passes, sceneId)?.layers.includes("image"));
  return { aImage: has(pair?.a.id), bImage: has(pair?.b.id) };
}

function zoneKinds(
  pair: ComparePair | null,
  compare: ReturnType<typeof useTimelineCompare>["data"],
): { a: Record<string, ZoneKind>; b: Record<string, ZoneKind> } {
  if (!pair || !compare?.comparable) return { a: {}, b: {} };
  const before = compare.before_zones ?? {};
  const after = compare.after_zones ?? {};
  const forward = Date.parse(pair.a.acquiredAt) <= Date.parse(pair.b.acquiredAt);
  return forward ? { a: before, b: after } : { a: after, b: before };
}

function imageLayer(analysis: Analysis, side: CompareSide, bounds: Bounds | null) {
  const image = analysis.layers.image;
  if (!image) return null;
  return new BitmapLayer<ClipExtensionProps & Anchored>({
    id: `${OWNER}:image-${side}:${analysis.id}`,
    ...UNDER_COASTLINE,
    image: analysisFileUrl(analysis.id, "image.png"),
    bounds: cornersForDeck(image.corners),
    extensions: bounds ? [clip] : [],
    clipBounds: bounds ?? undefined,
    clipByInstance: false,
  });
}

function zoneFeatures(
  analysis: Analysis,
  side: CompareSide,
  kinds: Record<string, ZoneKind>,
): { features: ZoneFeature[]; marks: ZoneMark[] } {
  const zones = toRealZones(analysis.detection.zones);
  const features: ZoneFeature[] = [];
  const marks: ZoneMark[] = [];
  for (const zone of zones) {
    const kind = kinds[zone.id] ?? null;
    if (zone.geometry)
      features.push({ type: "Feature", geometry: zone.geometry, properties: { zone, side, kind } });
    if (zone.centroid)
      marks.push({ zone, side, kind, position: [zone.centroid[0], zone.centroid[1]] });
  }
  return { features, marks };
}

type Hover = (info: PickingInfo<ZoneFeature | ZoneMark>) => void;

function zoneLayers(
  analysis: Analysis,
  side: CompareSide,
  kinds: Record<string, ZoneKind>,
  bounds: Bounds | null,
  showMarkers: boolean,
  onHover: Hover,
): Layer[] {
  const { features, marks } = zoneFeatures(analysis, side, kinds);
  const threshold = analysis.detection.threshold ?? null;
  const colorOf = (zone: RealZone) => zoneColor(zone.probabilityMax, threshold);
  const clipping = {
    extensions: bounds ? [clip] : [],
    clipBounds: bounds ?? undefined,
    clipByInstance: false,
  };
  const layers: Layer[] = [
    new GeoJsonLayer<ZoneProps, ClipExtensionProps & Anchored>({
      id: `${OWNER}:zones-${side}:${analysis.id}`,
      ...UNDER_LABELS,
      data: features,
      pickable: true,
      filled: true,
      stroked: true,
      getFillColor: (feature) => withAlpha(colorOf(feature.properties.zone), ZONE_FILL_ALPHA),
      getLineColor: (feature) => colorOf(feature.properties.zone),
      getLineWidth: 1.4,
      lineWidthUnits: "pixels",
      lineWidthMinPixels: 1,
      onHover,
      ...clipping,
    }),
  ];
  if (showMarkers)
    layers.push(
      new ScatterplotLayer<ZoneMark, ClipExtensionProps & Anchored>({
        id: `${OWNER}:zone-marks-${side}:${analysis.id}`,
        ...UNDER_LABELS,
        data: marks,
        pickable: true,
        getPosition: (mark) => mark.position,
        getRadius: ZONE_MARKER_PX,
        radiusUnits: "pixels",
        stroked: true,
        filled: true,
        getFillColor: (mark) =>
          mark.kind === "persisting" ? [0, 0, 0, 0] : withAlpha(colorOf(mark.zone), 0.35),
        getLineColor: (mark) => colorOf(mark.zone),
        getLineWidth: 1.6,
        lineWidthUnits: "pixels",
        onHover,
        ...clipping,
      }),
    );
  return layers;
}

function zoneHint(props: ZoneProps): string {
  const letter = props.side === "a" ? "A" : "B";
  const kind = props.kind ? ` · ${KIND_WORD[props.kind]}` : "";
  const peak =
    props.zone.probabilityMax === null ? "" : ` · p ${formatNumber(props.zone.probabilityMax, 2)}`;
  const area = props.zone.areaM2 === null ? "" : ` · ${formatNumber(props.zone.areaM2)} м²`;
  return `${letter}: ${props.zone.id}${kind}${peak}${area}`;
}

function useZoneHover(): Hover {
  const setHint = useStatusHintStore((state) => state.setHint);
  useEffect(() => () => setHint(null), [setHint]);
  return useCallback(
    (info) => {
      const object = info.object;
      if (!object) {
        setHint(null);
        return;
      }
      setHint(zoneHint("properties" in object ? object.properties : object));
    },
    [setHint],
  );
}

export function useLiveCompareLayers(pair: ComparePair | null, passes: LivePasses): Layer[] {
  const a = useSideAnalysis(pair?.a.id ?? null, passes);
  const b = useSideAnalysis(pair?.b.id ?? null, passes);
  const forward = pair ? Date.parse(pair.a.acquiredAt) <= Date.parse(pair.b.acquiredAt) : true;
  const compare = useTimelineCompare((forward ? a : b)?.id ?? null, (forward ? b : a)?.id ?? null);
  const dividerLng = useCompareViewStore((state) => state.dividerLng);
  const zoom = useCompareViewStore((state) => state.zoom);
  const zonesVisible = useLayerVisible("detector-zones");
  const onHover = useZoneHover();
  const showMarkers = zoom < ZONE_MARKERS_MAX_ZOOM;
  const kinds = useMemo(() => zoneKinds(pair, compare.data), [pair, compare.data]);

  return useMemo(() => {
    const aBounds = dividerLng === null ? null : sideBounds(dividerLng, "a");
    const bBounds = dividerLng === null ? null : sideBounds(dividerLng, "b");
    const images: Layer[] = [];
    const zones: Layer[] = [];
    if (a && aBounds) {
      const layer = imageLayer(a, "a", aBounds);
      if (layer) images.push(layer);
      if (zonesVisible) zones.push(...zoneLayers(a, "a", kinds.a, aBounds, showMarkers, onHover));
    }
    if (b) {
      const layer = imageLayer(b, "b", bBounds);
      if (layer) images.push(layer);
      if (zonesVisible) zones.push(...zoneLayers(b, "b", kinds.b, bBounds, showMarkers, onHover));
    }
    return [...images, ...zones];
  }, [a, b, dividerLng, kinds, zonesVisible, showMarkers, onHover]);
}
