import type { LngLat } from "@/domain/geo";
import type { SceneSummary } from "@/domain/scene";
import { offsetLngLat, toLocalMeters } from "@/lib/geo/local-metric";
import { centerlineOfWindrow, DEMO_CANDIDATE_SHAPES, unitHash } from "./candidates";
import { DEMO_SCENES, DEMO_TILE_FOOTPRINT } from "./scenes";
import { DEMO_CANDIDATE_HISTORIES } from "./timeline";

export type NoDataKind = "cloud" | "glint";

export type NoDataArea = {
  id: string;
  kind: NoDataKind;
  polygon: GeoJSON.Polygon;
};

export type UncertaintyArea = {
  id: string;
  uncertainty: number;
  reason: "candidate" | "cloud-edge";
  polygon: GeoJSON.Polygon;
};

export type SceneConditions = {
  sceneId: string;
  noData: readonly NoDataArea[];
  uncertainty: readonly UncertaintyArea[];
  footprint: GeoJSON.Polygon;
};

type Blob = { center: LngLat; radiusM: number; stretch: number; rotationDeg: number; seed: number };

const AREA_WEST = -88.95;
const AREA_EAST = -87.75;
const AREA_SOUTH = 15.55;
const AREA_NORTH = 16.3;
const BLOB_STEPS = 36;
const CLEARANCE_M = 700;
const EDGE_RING_SCALE = 1.35;
const EDGE_UNCERTAINTY = 0.5;

function ringOf(points: readonly LngLat[]): number[][] {
  return [...points, points[0]].map(([lng, lat]) => [lng, lat]);
}

function blobRing(blob: Blob, scale = 1): LngLat[] {
  const rotation = (blob.rotationDeg * Math.PI) / 180;
  const phaseA = unitHash(blob.seed, 1) * Math.PI * 2;
  const phaseB = unitHash(blob.seed, 2) * Math.PI * 2;
  return Array.from({ length: BLOB_STEPS }, (_, index) => {
    const angle = (index / BLOB_STEPS) * Math.PI * 2;
    const wobble = 1 + 0.16 * Math.sin(3 * angle + phaseA) + 0.09 * Math.sin(5 * angle + phaseB);
    const radius = blob.radiusM * wobble * scale;
    const x = Math.cos(angle) * radius * blob.stretch;
    const y = Math.sin(angle) * radius;
    return offsetLngLat(blob.center, [
      x * Math.cos(rotation) - y * Math.sin(rotation),
      x * Math.sin(rotation) + y * Math.cos(rotation),
    ]);
  });
}

function blobReach(blob: Blob): number {
  return blob.radiusM * 1.25 * Math.max(blob.stretch, 1);
}

function distanceM(a: LngLat, b: LngLat): number {
  const [x, y] = toLocalMeters(a, b);
  return Math.hypot(x, y);
}

function clearOf(blob: Blob, protectedLines: readonly (readonly LngLat[])[]): boolean {
  const reach = blobReach(blob) + CLEARANCE_M;
  return protectedLines.every((line) =>
    line.every((point) => distanceM(point, blob.center) > reach),
  );
}

function randomPoint(seed: number, attempt: number): LngLat {
  return [
    AREA_WEST + (AREA_EAST - AREA_WEST) * unitHash(seed, attempt, 7),
    AREA_SOUTH + (AREA_NORTH - AREA_SOUTH) * unitHash(seed, attempt, 11),
  ];
}

function sceneState(sceneId: string) {
  const cloudy: LngLat[][] = [];
  const clear: LngLat[][] = [];
  for (const history of DEMO_CANDIDATE_HISTORIES) {
    const shape = DEMO_CANDIDATE_SHAPES[history.candidateId];
    const pass = history.passes.find((entry) => entry.sceneId === sceneId);
    if (!shape || !pass) continue;
    const covered = pass.state === "cloudy" || pass.state === "no-data";
    const line = pass.geometry ? centerlineOfWindrow(pass.geometry) : [...shape.centerline];
    (covered ? cloudy : clear).push(line);
  }
  return { cloudy, clear };
}

function coveringBlob(
  line: readonly LngLat[],
  seed: number,
  protectedLines: readonly (readonly LngLat[])[],
): Blob {
  const middle = line[Math.floor(line.length / 2)];
  const halfLength = Math.max(distanceM(line[0], middle), distanceM(line.at(-1) ?? middle, middle));
  const generous: Blob = {
    center: offsetLngLat(middle, [
      (unitHash(seed, 3) - 0.5) * 900,
      (unitHash(seed, 4) - 0.5) * 900,
    ]),
    radiusM: halfLength + 1600 + unitHash(seed, 5) * 1800,
    stretch: 1.1 + unitHash(seed, 6) * 0.4,
    rotationDeg: unitHash(seed, 8) * 180,
    seed,
  };
  if (clearOf(generous, protectedLines)) return generous;
  return { center: middle, radiusM: halfLength + 700, stretch: 1, rotationDeg: 0, seed };
}

function extraBlobs(
  scene: SceneSummary,
  seed: number,
  protectedLines: readonly (readonly LngLat[])[],
): Blob[] {
  const count = Math.max(1, Math.round(scene.cloudCover * 12));
  const blobs: Blob[] = [];
  for (let index = 0; index < count; index += 1) {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const blobSeed = seed * 97 + index * 13 + attempt;
      const blob: Blob = {
        center: randomPoint(blobSeed, attempt),
        radiusM: (1200 + unitHash(blobSeed, 9) * 3800) * (0.7 + scene.cloudCover),
        stretch: 1 + unitHash(blobSeed, 10) * 0.8,
        rotationDeg: unitHash(blobSeed, 12) * 180,
        seed: blobSeed,
      };
      if (clearOf(blob, protectedLines)) {
        blobs.push(blob);
        break;
      }
    }
  }
  return blobs;
}

function glintBlob(
  scene: SceneSummary,
  seed: number,
  protectedLines: readonly (readonly LngLat[])[],
): Blob | null {
  if (scene.sunGlintRisk === "low") return null;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const blob: Blob = {
      center: randomPoint(seed * 31 + 5, attempt),
      radiusM: scene.sunGlintRisk === "high" ? 2600 : 1700,
      stretch: 3.2,
      rotationDeg: -24,
      seed: seed * 31 + attempt,
    };
    if (clearOf(blob, protectedLines)) return blob;
  }
  return null;
}

function corridorAround(geometry: GeoJSON.Polygon, zone: GeoJSON.Polygon): GeoJSON.Polygon {
  const ring = geometry.coordinates[0] ?? [];
  const zoneRing = zone.coordinates[0] ?? [];
  const center = (points: number[][]) => [
    points.reduce((sum, point) => sum + point[0], 0) / Math.max(points.length, 1),
    points.reduce((sum, point) => sum + point[1], 0) / Math.max(points.length, 1),
  ];
  const [fromLng, fromLat] = center(zoneRing);
  const [toLng, toLat] = center(ring);
  return {
    type: "Polygon",
    coordinates: [zoneRing.map(([lng, lat]) => [lng + toLng - fromLng, lat + toLat - fromLat])],
  };
}

function polygon(rings: readonly (readonly LngLat[])[]): GeoJSON.Polygon {
  return { type: "Polygon", coordinates: rings.map(ringOf) };
}

function overcast(scene: SceneSummary, seed: number): NoDataArea[] {
  const outer: LngLat[] = [
    [AREA_WEST - 0.25, AREA_SOUTH - 0.2],
    [AREA_EAST + 0.25, AREA_SOUTH - 0.2],
    [AREA_EAST + 0.25, AREA_NORTH + 0.2],
    [AREA_WEST - 0.25, AREA_NORTH + 0.2],
  ];
  const gaps: Blob[] = [
    { center: [-87.9, 16.22], radiusM: 3800, stretch: 1.4, rotationDeg: 20, seed: seed + 1 },
    { center: [-88.8, 15.62], radiusM: 3000, stretch: 1.2, rotationDeg: 70, seed: seed + 2 },
  ];
  return [
    {
      id: `${scene.id}:overcast`,
      kind: "cloud",
      polygon: polygon([outer, ...gaps.map((gap) => blobRing(gap).reverse())]),
    },
  ];
}

function conditionsFor(scene: SceneSummary, index: number): SceneConditions {
  const footprint = polygon([DEMO_TILE_FOOTPRINT]);
  const seed = index * 17 + 3;
  if (scene.usability === "unusable")
    return { sceneId: scene.id, noData: overcast(scene, seed), uncertainty: [], footprint };
  const { cloudy, clear } = sceneState(scene.id);
  const covering = cloudy.map((line, lineIndex) => coveringBlob(line, seed + lineIndex * 5, clear));
  const extras = extraBlobs(scene, seed, clear);
  const clouds = [...covering, ...extras];
  const glint = glintBlob(scene, seed, clear);
  const noData: NoDataArea[] = [
    ...clouds.map((blob, blobIndex) => ({
      id: `${scene.id}:cloud-${blobIndex}`,
      kind: "cloud" as const,
      polygon: polygon([blobRing(blob)]),
    })),
    ...(glint
      ? [{ id: `${scene.id}:glint`, kind: "glint" as const, polygon: polygon([blobRing(glint)]) }]
      : []),
  ];
  const edges: UncertaintyArea[] = clouds.map((blob, blobIndex) => ({
    id: `${scene.id}:edge-${blobIndex}`,
    uncertainty: EDGE_UNCERTAINTY,
    reason: "cloud-edge",
    polygon: polygon([blobRing(blob, EDGE_RING_SCALE), blobRing(blob).reverse()]),
  }));
  const candidates: UncertaintyArea[] = DEMO_CANDIDATE_HISTORIES.flatMap((history) => {
    const shape = DEMO_CANDIDATE_SHAPES[history.candidateId];
    const pass = history.passes.find((entry) => entry.sceneId === scene.id);
    if (!shape?.uncertaintyZone || pass?.state !== "found" || !pass.geometry) return [];
    const latest = history.passes.at(-1)?.geometry;
    return [
      {
        id: `${scene.id}:${history.candidateId}`,
        uncertainty: shape.uncertainty,
        reason: "candidate" as const,
        polygon:
          pass.geometry === latest
            ? shape.uncertaintyZone
            : corridorAround(pass.geometry, shape.uncertaintyZone),
      },
    ];
  });
  return { sceneId: scene.id, noData, uncertainty: [...edges, ...candidates], footprint };
}

export const DEMO_SCENE_CONDITIONS: Readonly<Record<string, SceneConditions>> = Object.fromEntries(
  DEMO_SCENES.map((scene, index) => [scene.id, conditionsFor(scene, index)]),
);

function insideRing(point: LngLat, ring: readonly number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (
      yi > point[1] !== yj > point[1] &&
      point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi
    )
      inside = !inside;
  }
  return inside;
}

function insidePolygon(point: LngLat, shape: GeoJSON.Polygon): boolean {
  const [outer, ...holes] = shape.coordinates;
  return insideRing(point, outer) && !holes.some((hole) => insideRing(point, hole));
}

export function nearestNoDataM(sceneId: string, point: LngLat): number | null {
  const conditions = DEMO_SCENE_CONDITIONS[sceneId];
  if (!conditions) return null;
  let best = Infinity;
  for (const area of conditions.noData) {
    if (insidePolygon(point, area.polygon)) return 0;
    for (const ring of area.polygon.coordinates)
      for (const [lng, lat] of ring) best = Math.min(best, distanceM(point, [lng, lat]));
  }
  return Number.isFinite(best) ? Math.round(best) : null;
}
