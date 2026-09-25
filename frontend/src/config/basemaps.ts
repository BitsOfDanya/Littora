import type {
  ExpressionSpecification,
  FilterSpecification,
  LayerSpecification,
  SourceSpecification,
  StyleSpecification,
} from "maplibre-gl";
import type { BasemapId } from "@/state/map-layers-store";
import type { ThemeId } from "@/state/preferences-store";

export const GLYPHS_URL = "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf";
export const OFM_SOURCE_ID = "ofm";
export const ANCHOR_DATA_LAYER_ID = "anchor-data";
export const ANCHOR_LABELS_LAYER_ID = "anchor-labels";
export const BACKGROUND_LAYER_ID = "background";

export const TILE_URLS = {
  eox2025: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2025_3857/default/g/{z}/{y}/{x}.jpg",
  eox2024: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg",
  gibsRelief:
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
  openFreeMap: "https://tiles.openfreemap.org/planet",
} as const;

export const EOX_MAXZOOM = 14;
export const GIBS_MAXZOOM = 8;

export type AttributionId = "eox" | "openFreeMap" | "gibs";

export const ATTRIBUTIONS: Readonly<Record<AttributionId, string>> = {
  eox: "EOxCloudless 2025 (и 2024 в режиме «Динамика») — EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2025) · CC BY-NC-SA 4.0 · cloudless.eox.at",
  openFreeMap: "OpenFreeMap © OpenMapTiles · Данные © участники OpenStreetMap (ODbL)",
  gibs: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS). Blue Marble: NASA Earth Observatory",
};

export const ATTRIBUTION_COMPACT = "EOX S2 cloudless 2025 · © OpenStreetMap";

type RasterTint = {
  "raster-brightness-min"?: number;
  "raster-brightness-max"?: number;
  "raster-saturation"?: number;
  "raster-contrast"?: number;
};

export const RASTER_TINTS: Readonly<Record<"eox" | "gibs", Readonly<Record<ThemeId, RasterTint>>>> =
  {
    eox: {
      night: {
        "raster-brightness-min": 0.07,
        "raster-brightness-max": 0.86,
        "raster-saturation": -0.28,
        "raster-contrast": 0.15,
      },
      day: {
        "raster-brightness-min": 0.04,
        "raster-brightness-max": 1,
        "raster-saturation": -0.12,
        "raster-contrast": 0.06,
      },
    },
    gibs: {
      night: { "raster-brightness-max": 0.8, "raster-saturation": -0.35 },
      day: { "raster-brightness-max": 0.98, "raster-saturation": -0.2 },
    },
  };

type VectorInk = {
  coast: string;
  coastOpacity: number;
  river: string;
  boundary: string;
  boundaryOpacity: number;
  label: string;
  labelMinor: string;
  halo: string;
  road: string | null;
};

const DARK_GROUND_BACKGROUND = "#0B1620";
const LIGHT_GROUND_BACKGROUND = "#D4E6EC";

const IMAGERY_INK: VectorInk = {
  coast: "#E4F1F3",
  coastOpacity: 0.45,
  river: "#E4F1F3",
  boundary: "#E4F1F3",
  boundaryOpacity: 0.45,
  label: "#EEF6F7",
  labelMinor: "#C9D6DA",
  halo: "rgba(5,8,10,.78)",
  road: null,
};

const CHART_TINTS: Readonly<
  Record<ThemeId, { background: string; water: string; land: string; ink: VectorInk }>
> = {
  night: {
    background: DARK_GROUND_BACKGROUND,
    water: "#0D151A",
    land: "#1C1F1D",
    ink: {
      coast: "#8FA0A6",
      coastOpacity: 1,
      river: "#2E4250",
      boundary: "#8FA0A6",
      boundaryOpacity: 0.55,
      label: "#D3DADD",
      labelMinor: "#A9B4B8",
      halo: "rgba(5,8,10,.85)",
      road: null,
    },
  },
  day: {
    background: LIGHT_GROUND_BACKGROUND,
    water: "#D4E6EC",
    land: "#DCD3B0",
    ink: {
      coast: "#5E6A6E",
      coastOpacity: 1,
      river: "#9DB4BD",
      boundary: "#5E6A6E",
      boundaryOpacity: 0.6,
      label: "#2E3538",
      labelMinor: "#4A5256",
      halo: "rgba(255,255,255,.9)",
      road: "#8B661F",
    },
  },
};

const LOCALIZED_NAME: ExpressionSpecification = ["coalesce", ["get", "name:ru"], ["get", "name"]];
const POLYGON: ExpressionSpecification = [
  "match",
  ["geometry-type"],
  ["Polygon", "MultiPolygon"],
  true,
  false,
];
const LINE: ExpressionSpecification = [
  "match",
  ["geometry-type"],
  ["LineString", "MultiLineString"],
  true,
  false,
];

function allOf(...conditions: ExpressionSpecification[]): FilterSpecification {
  return ["all", ...conditions];
}

const SOURCES = {
  eox2025: {
    type: "raster",
    tiles: [TILE_URLS.eox2025],
    tileSize: 256,
    maxzoom: EOX_MAXZOOM,
    attribution: ATTRIBUTIONS.eox,
  },
  gibs: {
    type: "raster",
    tiles: [TILE_URLS.gibsRelief],
    tileSize: 256,
    maxzoom: GIBS_MAXZOOM,
    attribution: ATTRIBUTIONS.gibs,
  },
  ofm: { type: "vector", url: TILE_URLS.openFreeMap, attribution: ATTRIBUTIONS.openFreeMap },
} as const satisfies Record<string, SourceSpecification>;

function backgroundLayer(color: string): LayerSpecification {
  return { id: BACKGROUND_LAYER_ID, type: "background", paint: { "background-color": color } };
}

function anchorLayer(id: string): LayerSpecification {
  return {
    id,
    type: "background",
    layout: { visibility: "none" },
    paint: { "background-opacity": 0 },
  };
}

function coastlineLayer(ink: VectorInk, maxWidth: number): LayerSpecification {
  return {
    id: "coastline",
    type: "line",
    source: OFM_SOURCE_ID,
    "source-layer": "water",
    filter: allOf(
      POLYGON,
      ["!=", ["get", "brunnel"], "tunnel"],
      ["!=", ["get", "class"], "swimming_pool"],
    ),
    layout: { "line-join": "round" },
    paint: {
      "line-color": ink.coast,
      "line-opacity": ink.coastOpacity,
      "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.5, 12, maxWidth],
    },
  };
}

function boundaryLayer(ink: VectorInk): LayerSpecification {
  return {
    id: "admin-boundary",
    type: "line",
    source: OFM_SOURCE_ID,
    "source-layer": "boundary",
    filter: ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]],
    layout: { "line-join": "round" },
    paint: {
      "line-color": ink.boundary,
      "line-opacity": ink.boundaryOpacity,
      "line-width": 0.8,
      "line-dasharray": [5, 2, 1, 2],
    },
  };
}

function placeLabelLayers(ink: VectorInk): LayerSpecification[] {
  const paint = {
    "text-color": ink.label,
    "text-halo-color": ink.halo,
    "text-halo-width": 1.4,
  } as const;
  return [
    {
      id: "label-country",
      type: "symbol",
      source: OFM_SOURCE_ID,
      "source-layer": "place",
      maxzoom: 7,
      filter: ["==", ["get", "class"], "country"],
      layout: {
        "text-field": LOCALIZED_NAME,
        "text-font": ["Noto Sans Bold"],
        "text-size": 12,
        "text-letter-spacing": 0.08,
        "text-max-width": 7,
      },
      paint,
    },
    {
      id: "label-village",
      type: "symbol",
      source: OFM_SOURCE_ID,
      "source-layer": "place",
      minzoom: 10,
      filter: ["==", ["get", "class"], "village"],
      layout: {
        "text-field": LOCALIZED_NAME,
        "text-font": ["Noto Sans Regular"],
        "text-size": 11,
        "text-max-width": 8,
      },
      paint: { ...paint, "text-color": ink.labelMinor },
    },
    {
      id: "label-town",
      type: "symbol",
      source: OFM_SOURCE_ID,
      "source-layer": "place",
      minzoom: 7,
      filter: ["==", ["get", "class"], "town"],
      layout: {
        "text-field": LOCALIZED_NAME,
        "text-font": ["Noto Sans Regular"],
        "text-size": 12,
        "text-max-width": 8,
      },
      paint,
    },
    {
      id: "label-city",
      type: "symbol",
      source: OFM_SOURCE_ID,
      "source-layer": "place",
      minzoom: 4,
      filter: ["==", ["get", "class"], "city"],
      layout: {
        "text-field": LOCALIZED_NAME,
        "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 5, 11, 10, 13],
        "text-max-width": 8,
      },
      paint,
    },
  ];
}

export const PLACE_LABEL_LAYER_IDS: readonly string[] = placeLabelLayers(IMAGERY_INK).map(
  (layer) => layer.id,
);

function riverLayer(ink: VectorInk): LayerSpecification {
  return {
    id: "rivers",
    type: "line",
    source: OFM_SOURCE_ID,
    "source-layer": "waterway",
    minzoom: 8,
    filter: allOf(LINE, ["match", ["get", "class"], ["river", "canal"], true, false]),
    paint: {
      "line-color": ink.river,
      "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.5, 13, 1.4],
    },
  };
}

function roadLayer(color: string): LayerSpecification {
  return {
    id: "roads",
    type: "line",
    source: OFM_SOURCE_ID,
    "source-layer": "transportation",
    minzoom: 9,
    filter: allOf(LINE, [
      "match",
      ["get", "class"],
      ["motorway", "trunk", "primary", "secondary"],
      true,
      false,
    ]),
    layout: { "line-join": "round", "line-cap": "round" },
    paint: {
      "line-color": color,
      "line-opacity": 0.45,
      "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.6, 14, 1.6],
    },
  };
}

function waterFillLayer(color: string): LayerSpecification {
  return {
    id: "water",
    type: "fill",
    source: OFM_SOURCE_ID,
    "source-layer": "water",
    filter: allOf(POLYGON, ["!=", ["get", "brunnel"], "tunnel"]),
    paint: { "fill-color": color, "fill-antialias": false },
  };
}

function composeStyle(
  name: string,
  sources: Record<string, SourceSpecification>,
  layers: LayerSpecification[],
): StyleSpecification {
  return { version: 8, name, glyphs: GLYPHS_URL, sources, layers };
}

function mosaicStyle(theme: ThemeId): StyleSpecification {
  return composeStyle(
    "littora-mosaic",
    { gibs: SOURCES.gibs, eox2025: SOURCES.eox2025, [OFM_SOURCE_ID]: SOURCES.ofm },
    [
      backgroundLayer(DARK_GROUND_BACKGROUND),
      {
        id: "gibs-relief",
        type: "raster",
        source: "gibs",
        maxzoom: 8.5,
        paint: {
          ...RASTER_TINTS.gibs[theme],
          "raster-opacity": ["interpolate", ["linear"], ["zoom"], 6.5, 1, 8.5, 0],
        },
      },
      {
        id: "eox-mosaic",
        type: "raster",
        source: "eox2025",
        minzoom: 6.5,
        paint: {
          ...RASTER_TINTS.eox[theme],
          "raster-opacity": ["interpolate", ["linear"], ["zoom"], 6.5, 0, 8.5, 1],
        },
      },
      anchorLayer(ANCHOR_DATA_LAYER_ID),
      coastlineLayer(IMAGERY_INK, 1),
      boundaryLayer(IMAGERY_INK),
      anchorLayer(ANCHOR_LABELS_LAYER_ID),
      ...placeLabelLayers(IMAGERY_INK),
    ],
  );
}

function chartStyle(theme: ThemeId): StyleSpecification {
  const tint = CHART_TINTS[theme];
  return composeStyle("littora-chart", { [OFM_SOURCE_ID]: SOURCES.ofm }, [
    backgroundLayer(tint.background),
    waterFillLayer(tint.water),
    riverLayer(tint.ink),
    anchorLayer(ANCHOR_DATA_LAYER_ID),
    coastlineLayer(tint.ink, 1.1),
    ...(tint.ink.road ? [roadLayer(tint.ink.road)] : []),
    boundaryLayer(tint.ink),
    anchorLayer(ANCHOR_LABELS_LAYER_ID),
    ...placeLabelLayers(tint.ink),
  ]);
}

function reliefStyle(theme: ThemeId): StyleSpecification {
  return composeStyle("littora-relief", { gibs: SOURCES.gibs, [OFM_SOURCE_ID]: SOURCES.ofm }, [
    backgroundLayer(DARK_GROUND_BACKGROUND),
    { id: "gibs-relief", type: "raster", source: "gibs", paint: { ...RASTER_TINTS.gibs[theme] } },
    anchorLayer(ANCHOR_DATA_LAYER_ID),
    coastlineLayer(IMAGERY_INK, 1),
    boundaryLayer(IMAGERY_INK),
    anchorLayer(ANCHOR_LABELS_LAYER_ID),
    ...placeLabelLayers(IMAGERY_INK),
  ]);
}

export type OverzoomNote = { fromZoom: number; text: string };

export type BasemapDefinition = {
  id: BasemapId;
  label: string;
  description: string;
  attribution: string;
  attributions: readonly AttributionId[];
  overzoomNote: OverzoomNote | null;
  style: (theme: ThemeId) => StyleSpecification;
  loadingBackground: (theme: ThemeId) => string;
  landAfterLoad: (theme: ThemeId) => string | null;
};

export const BASEMAPS: readonly BasemapDefinition[] = [
  {
    id: "s2-mosaic",
    label: "Мозаика S2",
    description: "Безоблачная мозаика Sentinel-2 за 2025 год · 10 м · не снимок конкретной даты",
    attribution: ATTRIBUTION_COMPACT,
    attributions: ["eox", "gibs", "openFreeMap"],
    overzoomNote: null,
    style: mosaicStyle,
    loadingBackground: () => DARK_GROUND_BACKGROUND,
    landAfterLoad: () => null,
  },
  {
    id: "chart",
    label: "Карта",
    description: "Векторная карта OpenStreetMap",
    attribution: "OpenFreeMap · © OpenStreetMap",
    attributions: ["openFreeMap"],
    overzoomNote: null,
    style: chartStyle,
    loadingBackground: (theme) => CHART_TINTS[theme].background,
    landAfterLoad: (theme) => CHART_TINTS[theme].land,
  },
  {
    id: "bathymetry",
    label: "Рельеф дна",
    description: "Рельеф суши и дна, до масштаба z8",
    attribution: "NASA GIBS Blue Marble · © OpenStreetMap",
    attributions: ["gibs", "openFreeMap"],
    overzoomNote: { fromZoom: 9, text: "Рельеф до масштаба z8; дальше — растянут" },
    style: reliefStyle,
    loadingBackground: () => DARK_GROUND_BACKGROUND,
    landAfterLoad: () => null,
  },
];

export function findBasemap(id: BasemapId): BasemapDefinition {
  return BASEMAPS.find((basemap) => basemap.id === id) ?? BASEMAPS[0];
}

export function attributionsFor(id: BasemapId): string[] {
  return findBasemap(id).attributions.map((source) => ATTRIBUTIONS[source]);
}
