"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import { Map, type MapLayerMouseEvent, type ViewStateChangeEvent } from "react-map-gl/maplibre";
import { findBasemap } from "@/config/basemaps";
import type { LngLat } from "@/domain/geo";
import { useMapLayersStore } from "@/state/map-layers-store";
import { usePreferencesStore } from "@/state/preferences-store";
import { ChartLandBackground } from "./chart-land-background";
import { DeckOverlay } from "./deck/deck-overlay";
import { AoiBoundaryLayer } from "./furniture/aoi-boundary-layer";
import { GraticuleLayer } from "./furniture/graticule-layer";
import { PlaceLabelsVisibility } from "./furniture/place-labels-visibility";
import { MAIN_MAP_ID, MAPLIBRE_WORKER_URL } from "./map-constants";
import { useMapViewStore } from "./state/map-view-store";

const MAX_ZOOM = 16;

type MapViewProps = {
  mapStyle: StyleSpecification | string;
  initialCenter: LngLat;
  initialZoom: number;
};

function lockNorthUp(map: MapLibreMap): void {
  map.touchZoomRotate.disableRotation();
  map.keyboard.disableRotation();
}

function useLoadingBackground(): string {
  const basemapId = useMapLayersStore((state) => state.basemapId);
  const theme = usePreferencesStore((state) => state.theme);
  return findBasemap(basemapId).loadingBackground(theme);
}

export default function MapView({ mapStyle, initialCenter, initialZoom }: MapViewProps) {
  const setCursor = useMapViewStore((state) => state.setCursor);
  const setCamera = useMapViewStore((state) => state.setCamera);
  const setReady = useMapViewStore((state) => state.setReady);
  const loadingBackground = useLoadingBackground();

  const handleMove = (event: ViewStateChangeEvent) =>
    setCamera({
      center: [event.viewState.longitude, event.viewState.latitude],
      zoom: event.viewState.zoom,
      bearing: event.viewState.bearing,
    });
  const handleMouseMove = (event: MapLayerMouseEvent) =>
    setCursor([event.lngLat.lng, event.lngLat.lat]);

  return (
    <Map
      id={MAIN_MAP_ID}
      mapStyle={mapStyle}
      workerUrl={MAPLIBRE_WORKER_URL}
      initialViewState={{
        longitude: initialCenter[0],
        latitude: initialCenter[1],
        zoom: initialZoom,
      }}
      maxZoom={MAX_ZOOM}
      attributionControl={false}
      dragRotate={false}
      pitchWithRotate={false}
      touchPitch={false}
      onLoad={(event) => {
        lockNorthUp(event.target);
        setReady(true);
        const center = event.target.getCenter();
        setCamera({
          center: [center.lng, center.lat],
          zoom: event.target.getZoom(),
          bearing: event.target.getBearing(),
        });
      }}
      onMove={handleMove}
      onMouseMove={handleMouseMove}
      onMouseOut={() => setCursor(null)}
      style={{ position: "absolute", inset: 0, background: loadingBackground }}
    >
      <DeckOverlay />
      <ChartLandBackground />
      <GraticuleLayer />
      <AoiBoundaryLayer />
      <PlaceLabelsVisibility />
    </Map>
  );
}
