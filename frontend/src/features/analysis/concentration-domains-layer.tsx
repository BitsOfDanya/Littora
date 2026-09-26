"use client";

import type { Layer, PickingInfo } from "@deck.gl/core";
import { PathStyleExtension } from "@deck.gl/extensions";
import { GeoJsonLayer } from "@deck.gl/layers";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useDemoActive } from "@/features/cartouche/use-layer-truth";
import { type Rgba, withAlpha } from "@/features/map/color";
import { type Anchored, UNDER_LABELS } from "@/features/map/deck/anchors";
import { useDeckLayers } from "@/features/map/deck/use-deck-layers";
import { useStatusHintStore } from "@/features/shell/status-hint-store";
import { useCapability } from "@/features/system/use-capabilities";
import { type ConcentrationDomain, getConcentrationDomains } from "@/lib/api/analyses";
import { formatNumber } from "@/lib/format/numbers";
import { useLayerVisible } from "@/state/map-layers-store";
import { profileLabel } from "./analysis-copy";

const DOMAIN_COLOR: Rgba = [72, 168, 116, 255];

function hint(domain: ConcentrationDomain): string {
  const { properties } = domain;
  return `Концентрация доступна · ${profileLabel(properties.profile)} · медиана ${formatNumber(properties.value, 0)} шт./км² (${formatNumber(properties.lower, 0)}–${formatNumber(properties.upper, 0)}) · сезон ${properties.season} · до ${properties.max_distance_km} км от ${properties.points} точек`;
}

export function ConcentrationDomainsLayer() {
  const visible = useLayerVisible("concentration-domains");
  const available = useCapability("concentration_model") === "available";
  const demoActive = useDemoActive();
  const setHint = useStatusHintStore((state) => state.setHint);
  const domains = useQuery({
    queryKey: ["concentration", "domains"],
    queryFn: ({ signal }) => getConcentrationDomains(signal),
    staleTime: Infinity,
    enabled: visible && available,
  });

  const layers = useMemo(() => {
    const list: Layer[] = [];
    const features = domains.data?.features ?? [];
    if (!visible || demoActive || !features.length) return list;
    list.push(
      new GeoJsonLayer<ConcentrationDomain["properties"], Anchored>({
        id: "concentration-domains",
        ...UNDER_LABELS,
        data: domains.data as never,
        stroked: true,
        filled: true,
        getFillColor: withAlpha(DOMAIN_COLOR, 0.08),
        getLineColor: withAlpha(DOMAIN_COLOR, 0.9),
        getLineWidth: 1.2,
        lineWidthUnits: "pixels",
        pickable: true,
        onHover: ((info: PickingInfo<ConcentrationDomain>) =>
          setHint(info.object ? hint(info.object) : null)) as never,
        extensions: [new PathStyleExtension({ dash: true })],
        getDashArray: [1, 2],
        dashJustified: true,
      } as never),
    );
    return list;
  }, [domains.data, visible, demoActive, setHint]);

  useDeckLayers("concentration-domains", layers);
  return null;
}
