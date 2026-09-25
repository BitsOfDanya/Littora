import type {
  BeachingSeverity,
  BeachSegmentRisk,
  CurrentField,
  DriftForecastDetail,
  ForecastRun,
  ProbabilityEstimate,
  SourceEstimate,
  Velocity,
} from "@/data/forecast";
import type { DebrisCandidate } from "@/domain/detection";
import { type DriftForecast, FORECAST_HORIZONS_H } from "@/domain/forecast";
import type { LngLat } from "@/domain/geo";
import { offsetLngLat, toLocalMeters } from "@/lib/geo/local-metric";
import { DEMO_CANDIDATES } from "./candidates";
import { DEMO_LATEST_SCENE } from "./scenes";

const WATER_MASK_RLE = [
  "ll4*29|lby.b.8v|lbv.f.8u|lbs.o.8o|lbq.u.8k|lbo.y.8i|lbm.12.8g|lbk.15.8f|lbi.17.8f|l31.3.4.1.2.1.",
  "85.19.8e|l31.5.2.6.81.1b.8e|l2v.b.1.9.7x.1e.8d|l2v.n.7u.1f.8d|l2u.q.7r.1h.8c|l2t.t.7n.1k.8b|l2v.",
  "r.3.1.7i.1n.89|l2u.t.1.2.7g.1q.88|l2t.u.7i.1s.87|l2u.y.7b.1u.87|l2t.z.79.1r.1.4.87|l2u.z.77.1s.1",
  ".4.87|l2u.z.75.1u.2.3.87|l2u.y.74.1x.2.2.87|l2v.v.75.1y.3.1.87|l2w.t.74.20.8b|l2y.p.75.21.8b|l2z",
  ".1.2.m.72.23.8b|l31.m.71.26.8a|l30.n.6z.29.89|l30.n.6u.2f.88|l32.l.6s.2j.86|l33.k.6q.2l.86|l32.k",
  ".6o.2p.85|l32.k.6k.2u.84|l32.4.2.e.6j.2w.83|l38.d.6i.36.7v|l37.c.6i.39.7u|l35.h.6d.3c.7t|l35.j.6",
  "a.3e.7s|l34.k.69.3f.7s|l34.l.68.3g.7r|l33.4.2.i.2.5.5y.3h.7r|l33.4.2.q.5w.3j.7q|l33.4.2.r.5u.3k.",
  "7q|l39.s.1.2.5q.3k.7q|l38.u.5r.3m.7p|l38.v.5o.3s.7l|l38.v.5n.3u.7k|l37.x.5m.3v.7j|l36.y.5m.3v.7j",
  "|l31.14.5k.42.7d|l2x.14.2.2.5e.49.7c|l2v.15.3.3.5b.4d.7a|l2s.18.2.3.5b.4f.79|l2r.19.5f.4h.78|l2q",
  ".1b.5d.4j.77|l2o.1d.5c.4l.76|l2m.1g.5a.4m.76|l2l.1i.58.4o.75|l2k.1k.55.4q.75|l2j.1l.54.4r.75|l2i",
  ".1n.52.4r.76|l2g.1r.4z.4t.75|l2d.1u.4y.4u.75|l2c.1w.4v.4w.1.1.73|l2a.1z.4t.4w.76|l29.20.4s.4w.77",
  "|l29.21.4p.4y.77|l27.23.4n.51.2.2.72|l25.26.4l.56.72|l23.28.4k.5e.6v|l21.2b.4h.62.69|l20.2c.4g.6",
  "5.67|l1y.2f.4d.68.66|l1w.2i.4b.6c.63|l1v.2j.49.6g.61|l1t.2m.46.6k.5z|l1r.2o.45.6n.5x|l1q.2q.42.6",
  "q.5w|l1o.2s.40.6s.5w|l1n.2u.3y.6u.5v|l1l.2w.3w.6x.2.3.5p|l1k.2y.3u.78.5k|l1j.2z.3s.7d.5h|l1h.31.",
  "3r.7g.5f|l1g.33.3o.7k.5d|l11.1.d.34.3n.7m.5c|lz.7.8.36.3k.7p.5b|ly.a.6.36.3i.7t.59|lv.d.6.36.3h.",
  "7w.57|lt.h.3.37.3f.7z.56|lu.3q.3d.82.55|lw.3o.3b.85.54|lw.3k.2.1.3a.88.53|lw.3j.3.1.38.8a.53|ly.",
  "3g.3b.8c.53|ly.3g.39.8f.52|lz.3e.3.1.34.8h.52|lz.3e.3.1.31.8k.2.2.4y|lz.3e.2.1.30.8n.51|lx.3g.31",
  ".8o.52|lv.3j.2y.8p.53|lu.3k.2x.8r.52|ls.3l.17.1.1o.8t.52|lr.3m.8.1.s.1.4.3.1l.8u.53|lp.3o.8.1.o.",
  "e.1h.8w.53|ln.3q.9.1.k.h.1g.8t.2.1.54|lm.3r.a.2.b.p.1d.8u.58|lk.3u.9.2.9.r.1b.8u.5a|lj.3v.7.4.7.",
  "t.19.8k.1.1.5k|lh.3x.6.5.6.u.17.8l.5n|lf.3y.6.7.4.w.14.8n.5n|le.3z.4.19.12.8p.5n|lc.41.4.19.10.8",
  "s.5m|lb.42.3.19.10.8t.5m|la.43.2.19.z.8w.5l|l8.46.2.17.z.8x.5l|l7.47.1.z.1.4.11.90.5k|l6.57.16.9",
  "1.5k|l4.59.14.94.5j|l3.4c.1.w.14.96.5i|w5d.11.99.5h|w5d.10.9c.m.a.4j|w4r.1.l.y.9i.5.p.4h|w4q.3.l",
  ".w.af.4f|w4q.1.m.w.ah.4e|w4q.1.m.u.al.4c|w4q.2.i.w.an.4b|w4p.3.d.10.ap.4a|w4p.1.1.1.a.11.as.49|w",
  "50.12.au.48|w4o.2.2.4.1.13.ax.47|w4o.1.1.19.ay.47|w4p.18.b2.45|w4o.18.b4.44|w4o.17.b7.42|w4o.15.",
  "ba.41|w4o.14.bd.3z|w4o.12.bh.3x|w4o.11.bv.3k|w4o.10.c0.3g|w4o.y.c5.3d|w4n.y.c8.1a.6.1r.4|w4m.y.c",
  "a.14.g.1j.7|w4l.y.cc.z.l.1f.a|w4k.x.cf.s.s.1c.c|w4i.y.cq.d.y.19.e|w4h.y.cv.4.13.17.g|w4g.y.e4.14",
  ".i|w4f.y.e6.11.k|w4f.x.e8.y.m|w4e.x.ea.w.n|w4e.w.eb.u.p|w4e.v.ed.r.r|w4d.v.ef.o.t|w4c.v.eh.l.v|w",
  "49.2.1.u.ej.j.w|w48.x.el.h.x|w46.y.en.a.1.3.z|w46.x.ep.3.4.1.14|w45.x.g2|w3y.13.g3|w3x.13.g4|w3x",
  ".12.g5|w3w.12.g6|w3u.13.g7|w3t.13.g8|w3t.12.g9|w3s.12.ga|w3k.6.1.12.gb|w3h.1b.gc|w3h.1a.gd|w3h.1",
  "9.ge|w3g.18.gg|w3f.18.gh|w3f.17.gi|w3e.16.gk|w3e.15.gl|w3e.13.gn|w3d.12.gp|w3d.10.gr|w3d.y.gt|w3",
  "c.x.gv|w3c.v.gx|w3c.t.gz|w3c.s.h0|w3b.r.h2|w3b.p.h4|w3a.n.h7|w3a.i.hc|w3b.b.hi|wl4*2h|w9q.1.bd|w",
  "l4*4|l1.9s.2.b9|l1.l3*5|l2.9v.1.b6|l3.l1|l4.l0|l8.kw|lb.kt|lc.ks|ld.kr|lg.ko|li.km|ll.kj|ln.kh|l",
  "q.ke|lt.98.1.b2|lu.ka|lx.k7|lx.97.1.az|lx.k7|ly.k6|lw.k.1.jn*2|lv.f.1.jt|lu.g.1.jt|lu.ka*2|lv.k9",
  "|lw.k8|lz.k5*2|ly.k6|ly.d.1.js|ly.1g.1.ip|ly.g.1.jp|lz.f.2.jo|l11.f.2.7.2.jd|l13.f.1.7.1.jd|l14.",
  "f.1.2.1.jh|l15.i.1.jg|l18.f.1.v.1.1.1.ii|l16.g.3.w.1.ii|l15.j.1.v.2.1.1.ig|l14.k0|l13.r.2.t.1.5.",
  "5.i4|l13.k.1.4.1.1.2.s.1.2.1.1j.2.gr|l12.l.1.4.1.2.1.w.3.i9|l12.t.1.l.4.3.2.3.1.ia|l11.q.7.1.1.l",
  ".1.2.1.4.1.ia|l11.u.1.1.1.1.2.h.2.7.1.ic|l11.t.1.3.1.1.2.i.1.4.2.2.1.ia|l12.n.1.5.1.3.1.p.1.3.1.",
  "6.2.i2|l13.s.2.2.1.o.1.b.2.16.1.gv|l12.s.2.o.3.f.3.13.1.gv|l12.u.2.14.3.hz|l11.u.1.3.1.j4|l10.16",
  ".1.ix|l10.k.1.9.1.2.2.3.5.ix|lz.u.2.6.1.3.2.ix|lz.10.1.6.2.iw|lz.10.2.j3|ly.k6*2|ly.22.1.i3|ly.2",
  "2.2.2c.1.fp|lz.1d.1.n.2.i2|lz.1c.3.n.2.i1|ly.18.1.7.1.m.2.i1|ly.14.2.2.1.4.1.2.1.4.2.ij|ly.t.1.c",
  ".1.1.3.a.1.ik|ly.1e.1.2.2.2.2.ij|lz.t.1.k.1.3.1.im|l11.1h.2.e.2.i4|l16.1b.1.g.4.d.1.9.1.4.2.h8|l",
  "18.1a.2.e.5.s.2.h7|l19.16.1.3.1.h.4.hz|l1a.5.1.jo|l19.jv|l19.1e.2.s.1.hm|l1a.1a.1.1.1.ih|l1c.1z.",
  "1.hs|l1c.1t.3.hw|l1a.1x.1.hw|l1d.7.2.1.1.1.3.1.1.1.2.1b.1.3.1.hr|l1x.1d.2.l.2.h5|l1t.1f.3.n.1.h5",
  "|l1s.26.2.h4|l1v.5.1.1w.4.h3|l1v.22.4.h3|l25.1r.5.h3|l26.1p.6.h3|l28.1n.6.h3|l29.8.4.1b.6.h2|l2d",
  ".4.5.1b.5.5.1.gw|l2d.3.7.12.3.6.5.5.1.gv|l2o.12.3.6.4.h1|l2p.z.5.8.2.h1|l2p.s.2.4.6.8.2.h1|l2p.r",
  ".e.6.3.h1|l2q.q.f.3.6.h0|l2p.q.p.h0|l2p.q.q.gz|l2n.r.r.gz|l2m.r.t.gy|l2m.q.v.gx|l2m.p.11.gs|l2m.",
  "o.13.gr|l2m.n.1h.ge|l2n.l.1i.ge|l2n.k.1j.ge|l2n.j.1k.ge|l2o.h.1l.ge|l2p.f.1m.ge|l2q.c.1o.ge|l2t.",
  "7.1q.ge|l4q.ge*5|l4r.gd*5|l4s.gc*2|l4t.gb|l4u.ga|l4y.g6|l50.g4|l51.g3|l52.g2|l53.g1|l54.g0|l55.f",
  "z|l56.fy|l57.fx*3|l58.fw*2|l59.fv|l5a.fu|l5b.ft|l5c.fs|l5e.fq|l5f.fp|l5g.fo|l5h.fn|l5i.fm|l5k.fk",
].join("");

const MASK = { west: -88.8, south: 15.56, stepDeg: 0.0015, cols: 760, rows: 520 } as const;

let waterCells: Uint8Array | null = null;

function decodeWaterMask(): Uint8Array {
  const cells = new Uint8Array(MASK.cols * MASK.rows);
  let row = 0;
  for (const entry of WATER_MASK_RLE.split("|")) {
    const [runs, repeat] = entry.split("*");
    const times = repeat ? Number.parseInt(repeat, 36) : 1;
    for (let copy = 0; copy < times; copy += 1) {
      let water = runs[0] === "w";
      let column = 0;
      for (const run of runs.slice(1).split(".")) {
        const length = Number.parseInt(run, 36);
        if (water) cells.fill(1, row * MASK.cols + column, row * MASK.cols + column + length);
        column += length;
        water = !water;
      }
      row += 1;
    }
  }
  return cells;
}

function isWater(lng: number, lat: number): boolean {
  const column = Math.floor((lng - MASK.west) / MASK.stepDeg);
  const row = Math.floor((lat - MASK.south) / MASK.stepDeg);
  if (column < 0 || row < 0 || column >= MASK.cols || row >= MASK.rows) return false;
  waterCells ??= decodeWaterMask();
  return waterCells[row * MASK.cols + column] === 1;
}

const GYRE = { center: [-88.2, 16.03] as LngLat, radiusM: 17_000, peakMs: 0.11 };
const NEARSHORE = { calmLat: 15.8, openLat: 15.88 };
const PLUME = { mouth: [-88.2372, 15.7225] as LngLat, peakMs: 0.22, decayM: 7_000, veerDeg: 15 };
const JET = {
  path: [
    [-88.25, 15.805],
    [-88.2, 15.8],
    [-88.14, 15.793],
    [-88.09, 15.787],
    [-88.062, 15.784],
    [-88.047, 15.781],
  ] as readonly LngLat[],
  peakMs: 0.09,
  widthM: 2_600,
  rampM: 3_000,
  focus: 0.15,
};
const INFLOW = { speedMs: 0.06, fromLat: 16.05, fullLat: 16.25 };

function smoothstep(edge0: number, edge1: number, value: number): number {
  const t = Math.min(Math.max((value - edge0) / (edge1 - edge0), 0), 1);
  return t * t * (3 - 2 * t);
}

function gyreAt(point: LngLat): Velocity {
  const [x, y] = toLocalMeters(GYRE.center, point);
  const r = Math.hypot(x, y);
  if (r < 1) return [0, 0];
  const q = r / GYRE.radiusM;
  const speed =
    GYRE.peakMs *
    q *
    Math.exp((1 - q * q) / 2) *
    smoothstep(NEARSHORE.calmLat, NEARSHORE.openLat, point[1]);
  return [(speed * -y) / r, (speed * x) / r];
}

function plumeAt(point: LngLat): Velocity {
  const [x, y] = toLocalMeters(PLUME.mouth, point);
  const r = Math.hypot(x, y);
  if (r < 1) return [0, 0];
  const speed = PLUME.peakMs * Math.exp(-r / PLUME.decayM) * (r / (r + 600));
  const veer = (PLUME.veerDeg * Math.PI) / 180;
  const dx = x / r;
  const dy = y / r;
  return [
    speed * (dx * Math.cos(veer) + dy * Math.sin(veer)),
    speed * (-dx * Math.sin(veer) + dy * Math.cos(veer)),
  ];
}

function jetAt(point: LngLat): Velocity {
  let best = {
    distance: Infinity,
    along: 0,
    tangent: [1, 0] as Velocity,
    offset: [0, 0] as Velocity,
  };
  let travelled = 0;
  for (let index = 0; index < JET.path.length - 1; index += 1) {
    const [ax, ay] = toLocalMeters(point, JET.path[index]);
    const [bx, by] = toLocalMeters(point, JET.path[index + 1]);
    const dx = bx - ax;
    const dy = by - ay;
    const length = Math.hypot(dx, dy);
    const t = Math.min(Math.max(-(ax * dx + ay * dy) / (length * length), 0), 1);
    const cx = ax + dx * t;
    const cy = ay + dy * t;
    const distance = Math.hypot(cx, cy);
    if (distance < best.distance)
      best = {
        distance,
        along: travelled + length * t,
        tangent: [dx / length, dy / length],
        offset: [cx, cy],
      };
    travelled += length;
  }
  const speed =
    JET.peakMs *
    Math.exp(-(best.distance * best.distance) / (2 * JET.widthM * JET.widthM)) *
    smoothstep(0, JET.rampM, best.along);
  const pull = best.distance > 1 ? (JET.focus * speed) / best.distance : 0;
  return [
    speed * best.tangent[0] + pull * best.offset[0],
    speed * best.tangent[1] + pull * best.offset[1],
  ];
}

function currentAt(lng: number, lat: number): Velocity {
  const point: LngLat = [lng, lat];
  const [ge, gn] = gyreAt(point);
  const [pe, pn] = plumeAt(point);
  const [je, jn] = jetAt(point);
  return [
    ge + pe + je - INFLOW.speedMs * smoothstep(INFLOW.fromLat, INFLOW.fullLat, lat),
    gn + pn + jn,
  ];
}

export const DEMO_CURRENT_FIELD: CurrentField = {
  label: "Синтетическое поле течений для макета",
  bounds: [
    MASK.west,
    MASK.south,
    MASK.west + MASK.cols * MASK.stepDeg,
    MASK.south + MASK.rows * MASK.stepDeg,
  ],
  typicalSpeedMs: 0.15,
  velocityAt: (lng, lat) => (isWater(lng, lat) ? currentAt(lng, lat) : null),
  isWater,
};

const T0 = DEMO_LATEST_SCENE.acquiredAt;

export const DEMO_FORECAST_RUN: ForecastRun = {
  t0: T0,
  runAt: "2026-09-18T18:00:00Z",
  issuedAt: "2026-09-18T18:40:00Z",
  ensembleSize: 50,
  windageRatio: 0.01,
  windFromDeg: 290,
  windSpeedMs: 4,
  hindcastHours: 48,
  currents: "CMEMS GLO-PHY 1/12°",
  wind: "GFS 0,25°",
  model: "OpenDrift",
};

const STEPS_PER_HOUR = 4;
const STEP_S = 3600 / STEPS_PER_HOUR;
const DIFFUSIVITY_M2S = 1;
const FORECAST_HOURS = FORECAST_HORIZONS_H[FORECAST_HORIZONS_H.length - 1];
const ENVELOPE_SHARE = 0.9;
const ENVELOPE_MARGIN_M = 150;
const Z90 = 1.6449;

type Rng = () => number;

function seededRng(seed: number): Rng {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussian(rng: Rng): number {
  const u = Math.max(rng(), 1e-12);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rng());
}

type Member = {
  position: LngLat;
  stranded: { hour: number; position: LngLat } | null;
  currentScale: number;
  bias: Velocity;
  wind: Velocity;
};

function windDrift(rng: Rng): Velocity {
  const ratio = DEMO_FORECAST_RUN.windageRatio * (0.6 + 0.8 * rng());
  const toward = ((DEMO_FORECAST_RUN.windFromDeg + 180 + 15 * gaussian(rng)) * Math.PI) / 180;
  const speed = DEMO_FORECAST_RUN.windSpeedMs * ratio;
  return [speed * Math.sin(toward), speed * Math.cos(toward)];
}

function startPosition(candidate: DebrisCandidate, rng: Rng): LngLat {
  const ring = candidate.geometry.coordinates[0];
  const index = Math.floor(rng() * (ring.length - 1));
  const [lng, lat] = ring[index];
  const pull = rng();
  return [lng + (candidate.centroid[0] - lng) * pull, lat + (candidate.centroid[1] - lat) * pull];
}

function spawnMembers(candidate: DebrisCandidate, rng: Rng): Member[] {
  return Array.from({ length: DEMO_FORECAST_RUN.ensembleSize }, () => ({
    position: startPosition(candidate, rng),
    stranded: null,
    currentScale: 1 + 0.08 * gaussian(rng),
    bias: [0.018 * gaussian(rng), 0.018 * gaussian(rng)],
    wind: windDrift(rng),
  }));
}

function memberVelocity(member: Member, position: LngLat, direction: 1 | -1): Velocity {
  const [east, north] = currentAt(position[0], position[1]);
  return [
    direction * (east * member.currentScale + member.bias[0] + member.wind[0]),
    direction * (north * member.currentScale + member.bias[1] + member.wind[1]),
  ];
}

function advanceMember(member: Member, hour: number, direction: 1 | -1, rng: Rng): void {
  if (member.stranded) return;
  const start = member.position;
  const [k1e, k1n] = memberVelocity(member, start, direction);
  const middle = offsetLngLat(start, [(k1e * STEP_S) / 2, (k1n * STEP_S) / 2]);
  const [k2e, k2n] = memberVelocity(member, middle, direction);
  const spread = Math.sqrt(2 * DIFFUSIVITY_M2S * STEP_S);
  const next = offsetLngLat(start, [
    k2e * STEP_S + spread * gaussian(rng),
    k2n * STEP_S + spread * gaussian(rng),
  ]);
  if (isWater(next[0], next[1])) member.position = next;
  else member.stranded = { hour, position: start };
}

function runEnsemble(
  candidate: DebrisCandidate,
  hours: number,
  direction: 1 | -1,
  seed: number,
): { members: Member[]; hourly: LngLat[][] } {
  const rng = seededRng(seed);
  const members = spawnMembers(candidate, rng);
  const hourly: LngLat[][] = [members.map((member) => member.position)];
  for (let hour = 1; hour <= hours; hour += 1) {
    for (let step = 0; step < STEPS_PER_HOUR; step += 1) {
      const time = hour - 1 + (step + 1) / STEPS_PER_HOUR;
      for (const member of members) advanceMember(member, time, direction, rng);
    }
    hourly.push(members.map((member) => member.position));
  }
  return { members, hourly };
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = sorted.length / 2;
  return sorted.length % 2 ? sorted[Math.floor(middle)] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function medianPosition(positions: readonly LngLat[]): LngLat {
  return [median(positions.map((p) => p[0])), median(positions.map((p) => p[1]))];
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function roundPosition([lng, lat]: LngLat): LngLat {
  return [round(lng, 5), round(lat, 5)];
}

type Point = readonly [number, number];

function cross(o: Point, a: Point, b: Point): number {
  return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
}

function convexHull(points: readonly Point[]): Point[] {
  const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const lower: Point[] = [];
  for (const point of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0)
      lower.pop();
    lower.push(point);
  }
  const upper: Point[] = [];
  for (const point of [...sorted].reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0)
      upper.pop();
    upper.push(point);
  }
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}

function chaikin(ring: readonly Point[], iterations: number): Point[] {
  let current = [...ring];
  for (let pass = 0; pass < iterations; pass += 1) {
    const next: Point[] = [];
    current.forEach((point, index) => {
      const following = current[(index + 1) % current.length];
      next.push([0.75 * point[0] + 0.25 * following[0], 0.75 * point[1] + 0.25 * following[1]]);
      next.push([0.25 * point[0] + 0.75 * following[0], 0.25 * point[1] + 0.75 * following[1]]);
    });
    current = next;
  }
  return current;
}

function coreMembers(local: readonly Point[]): Point[] {
  const n = local.length;
  const mx = local.reduce((sum, p) => sum + p[0], 0) / n;
  const my = local.reduce((sum, p) => sum + p[1], 0) / n;
  let sxx = 0;
  let syy = 0;
  let sxy = 0;
  for (const [x, y] of local) {
    sxx += (x - mx) ** 2;
    syy += (y - my) ** 2;
    sxy += (x - mx) * (y - my);
  }
  const [a, c, b] = [sxx / (n - 1) + 1, syy / (n - 1) + 1, sxy / (n - 1)];
  const determinant = a * c - b * b;
  const distance = ([x, y]: Point) => {
    const dx = x - mx;
    const dy = y - my;
    return (c * dx * dx - 2 * b * dx * dy + a * dy * dy) / determinant;
  };
  return [...local]
    .sort((p, q) => distance(p) - distance(q))
    .slice(0, Math.ceil(n * ENVELOPE_SHARE));
}

function envelopeOf(positions: readonly LngLat[]): GeoJSON.Polygon {
  const origin = positions[0];
  const local = positions.map((position) => toLocalMeters(origin, position) as Point);
  const hull = convexHull(coreMembers(local));
  const cx = hull.reduce((sum, p) => sum + p[0], 0) / Math.max(hull.length, 1);
  const cy = hull.reduce((sum, p) => sum + p[1], 0) / Math.max(hull.length, 1);
  const ring =
    hull.length >= 3
      ? chaikin(
          hull.map(([x, y]) => {
            const r = Math.hypot(x - cx, y - cy) || 1;
            return [
              x + ((x - cx) / r) * ENVELOPE_MARGIN_M,
              y + ((y - cy) / r) * ENVELOPE_MARGIN_M,
            ] as Point;
          }),
          3,
        )
      : Array.from({ length: 24 }, (_, index) => {
          const angle = (index / 24) * Math.PI * 2;
          return [
            cx + Math.cos(angle) * ENVELOPE_MARGIN_M,
            cy + Math.sin(angle) * ENVELOPE_MARGIN_M,
          ] as Point;
        });
  const coordinates = ring.map(([x, y]) => {
    const [lng, lat] = offsetLngLat(origin, [x, y]);
    return [round(lng, 5), round(lat, 5)];
  });
  return { type: "Polygon", coordinates: [[...coordinates, coordinates[0]]] };
}

function wilson(successes: number, total: number): ProbabilityEstimate {
  const p = successes / total;
  const z2 = Z90 * Z90;
  const denominator = 1 + z2 / total;
  const center = (p + z2 / (2 * total)) / denominator;
  const half = (Z90 * Math.sqrt((p * (1 - p)) / total + z2 / (4 * total * total))) / denominator;
  return {
    value: round(p, 2),
    low: round(Math.max(0, center - half), 2),
    high: round(Math.min(1, center + half), 2),
  };
}

type CoastStretch = { id: string; name: string; path: readonly LngLat[] };

const COAST_STRETCHES: readonly CoastStretch[] = [
  {
    id: "omoa",
    name: "Омоа, пляж",
    path: [
      [-88.0454, 15.7752],
      [-88.0454, 15.7768],
      [-88.0468, 15.7786],
      [-88.049, 15.78],
      [-88.049, 15.7808],
      [-88.0472, 15.7826],
      [-88.0448, 15.7834],
      [-88.044, 15.7818],
      [-88.042, 15.7818],
      [-88.0402, 15.7828],
      [-88.0406, 15.7832],
      [-88.04, 15.7842],
      [-88.0384, 15.785],
      [-88.0256, 15.7858],
      [-88.0232, 15.7866],
    ],
  },
  {
    id: "chachaguala",
    name: "Чачагуала",
    path: [
      [-88.0964, 15.7318],
      [-88.0868, 15.7322],
      [-88.082, 15.735],
      [-88.0806, 15.7364],
      [-88.081, 15.738],
      [-88.0778, 15.7416],
      [-88.0774, 15.746],
      [-88.076, 15.7486],
      [-88.0704, 15.7494],
      [-88.067, 15.752],
      [-88.067, 15.7532],
      [-88.0656, 15.7546],
      [-88.0584, 15.7554],
      [-88.056, 15.7578],
      [-88.0512, 15.7602],
      [-88.0478, 15.7636],
      [-88.0462, 15.7664],
      [-88.0462, 15.7712],
      [-88.0454, 15.7752],
    ],
  },
  {
    id: "chivana",
    name: "Чивана",
    path: [
      [-88.0232, 15.7866],
      [-88.0016, 15.7866],
      [-87.9988, 15.7866],
      [-87.9944, 15.7882],
      [-87.9934, 15.7892],
      [-87.9936, 15.7906],
      [-87.9888, 15.7914],
      [-87.978, 15.797],
      [-87.977, 15.8004],
      [-87.9748, 15.8026],
      [-87.9692, 15.8018],
      [-87.9628, 15.8026],
    ],
  },
  {
    id: "cortes",
    name: "Пуэрто-Кортес",
    path: [
      [-87.9628, 15.8026],
      [-87.9516, 15.807],
      [-87.946, 15.8114],
      [-87.9444, 15.8114],
      [-87.9396, 15.8146],
      [-87.9366, 15.8176],
      [-87.9342, 15.822],
      [-87.933, 15.8252],
    ],
  },
  {
    id: "masca",
    name: "Маска",
    path: [
      [-88.1092, 15.7014],
      [-88.1114, 15.6988],
      [-88.113, 15.696],
      [-88.1138, 15.6936],
      [-88.1146, 15.692],
      [-88.116, 15.6898],
      [-88.1208, 15.687],
      [-88.1284, 15.685],
      [-88.1328, 15.6838],
      [-88.1368, 15.6838],
      [-88.1428, 15.6814],
      [-88.152, 15.6814],
      [-88.1608, 15.6838],
    ],
  },
  {
    id: "cuyamel",
    name: "Куямель",
    path: [
      [-88.1608, 15.6838],
      [-88.1672, 15.6866],
      [-88.182, 15.6946],
      [-88.1944, 15.7038],
      [-88.2024, 15.7078],
      [-88.2184, 15.7182],
    ],
  },
  {
    id: "motagua",
    name: "Дельта Мотагуа",
    path: [
      [-88.2184, 15.7182],
      [-88.2288, 15.7234],
      [-88.234, 15.7242],
      [-88.242, 15.7278],
      [-88.2516, 15.7306],
      [-88.2588, 15.7346],
      [-88.265, 15.7408],
    ],
  },
  {
    id: "quetzalito",
    name: "Эль-Кетсалито",
    path: [
      [-88.265, 15.7408],
      [-88.2706, 15.748],
      [-88.2742, 15.75],
      [-88.275, 15.754],
      [-88.2768, 15.7562],
      [-88.286, 15.757],
      [-88.3, 15.7694],
      [-88.31, 15.7778],
      [-88.3184, 15.783],
      [-88.324, 15.7874],
      [-88.3312, 15.7922],
    ],
  },
  {
    id: "jaloa",
    name: "Халоа",
    path: [
      [-88.3312, 15.7922],
      [-88.3428, 15.7986],
      [-88.3632, 15.8118],
      [-88.3832, 15.823],
      [-88.3904, 15.8266],
      [-88.3956, 15.8282],
    ],
  },
  {
    id: "san-francisco",
    name: "Сан-Франсиско-дель-Мар",
    path: [
      [-88.3956, 15.8282],
      [-88.3988, 15.8298],
      [-88.4028, 15.8318],
      [-88.412, 15.8374],
      [-88.4376, 15.8506],
      [-88.4692, 15.8726],
    ],
  },
  {
    id: "manabique",
    name: "Пунта-де-Манабике",
    path: [
      [-88.4692, 15.8726],
      [-88.4904, 15.8874],
      [-88.5032, 15.8974],
      [-88.538, 15.9322],
    ],
  },
  {
    id: "tres-puntas",
    name: "Кабо-Трес-Пунтас",
    path: [
      [-88.538, 15.9322],
      [-88.554, 15.9454],
      [-88.574, 15.9554],
      [-88.578, 15.9582],
      [-88.5852, 15.9618],
      [-88.594, 15.9642],
      [-88.6104, 15.9666],
      [-88.6212, 15.9662],
      [-88.623, 15.9648],
      [-88.6226, 15.962],
    ],
  },
  {
    id: "amatique",
    name: "Манабике, берег залива",
    path: [
      [-88.5626, 15.8584],
      [-88.5642, 15.852],
      [-88.5642, 15.8468],
      [-88.5642, 15.8376],
      [-88.5634, 15.8324],
      [-88.5624, 15.8298],
      [-88.5604, 15.8302],
      [-88.5578, 15.8264],
      [-88.5562, 15.8216],
      [-88.5538, 15.8184],
      [-88.5534, 15.8152],
      [-88.5558, 15.8092],
      [-88.5566, 15.8052],
      [-88.5626, 15.7936],
      [-88.5654, 15.7892],
      [-88.5682, 15.7832],
    ],
  },
];

const STRETCH_CAPTURE_M = 1_500;
const ALARM_FROM = 0.4;
const CAUTION_FROM = 0.1;

function distanceToPathM(point: LngLat, path: readonly LngLat[]): number {
  let best = Infinity;
  for (let index = 0; index < path.length - 1; index += 1) {
    const [ax, ay] = toLocalMeters(point, path[index]);
    const [bx, by] = toLocalMeters(point, path[index + 1]);
    const dx = bx - ax;
    const dy = by - ay;
    const lengthSq = dx * dx + dy * dy || 1;
    const t = Math.min(Math.max(-(ax * dx + ay * dy) / lengthSq, 0), 1);
    best = Math.min(best, Math.hypot(ax + dx * t, ay + dy * t));
  }
  return best;
}

function nearestStretch(point: LngLat): CoastStretch | null {
  let best: { stretch: CoastStretch; distance: number } | null = null;
  for (const stretch of COAST_STRETCHES) {
    const distance = distanceToPathM(point, stretch.path);
    if (distance <= STRETCH_CAPTURE_M && (!best || distance < best.distance))
      best = { stretch, distance };
  }
  return best?.stretch ?? null;
}

function quantile(sorted: readonly number[], q: number): number {
  const position = (sorted.length - 1) * q;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

function severityOf(probability: number): BeachingSeverity {
  if (probability >= ALARM_FROM) return "alarm";
  if (probability >= CAUTION_FROM) return "caution";
  return "info";
}

function labelAnchor(path: readonly LngLat[]): LngLat {
  return path[Math.floor(path.length / 2)];
}

const OTHER_COAST_ID = "other";

function riskFor(
  id: string,
  name: string,
  hours: readonly number[],
  total: number,
  path: readonly LngLat[],
): BeachSegmentRisk {
  const sorted = [...hours].sort((a, b) => a - b);
  const probability = wilson(sorted.length, total);
  return {
    id,
    name,
    severity: severityOf(probability.value),
    probability,
    members: sorted.length,
    windowH: [Math.floor(quantile(sorted, 0.1)), Math.ceil(quantile(sorted, 0.9))],
    path,
    labelAt: path.length ? labelAnchor(path) : null,
  };
}

function beachingRisks(members: readonly Member[]): BeachSegmentRisk[] {
  const hits = new Map<string, number[]>();
  for (const member of members) {
    if (!member.stranded) continue;
    const id = nearestStretch(member.stranded.position)?.id ?? OTHER_COAST_ID;
    hits.set(id, [...(hits.get(id) ?? []), member.stranded.hour]);
  }
  const named = COAST_STRETCHES.filter((stretch) => hits.has(stretch.id)).map((stretch) =>
    riskFor(stretch.id, stretch.name, hits.get(stretch.id) ?? [], members.length, stretch.path),
  );
  const other = hits.get(OTHER_COAST_ID);
  return [
    ...named.sort((a, b) => b.members - a.members),
    ...(other ? [riskFor(OTHER_COAST_ID, "Прочий берег", other, members.length, [])] : []),
  ];
}

type RiverMouth = { id: string; name: string; position: LngLat };

const RIVER_MOUTHS: readonly RiverMouth[] = [
  { id: "motagua", name: "Устье р. Мотагуа", position: [-88.2372, 15.7225] },
  { id: "cuyamel", name: "Устье р. Куямель", position: [-88.2018, 15.7063] },
  { id: "chachaguala", name: "Устье р. Чачагуала", position: [-88.0957, 15.7301] },
  { id: "san-francisco", name: "Устье р. Сан-Франсиско", position: [-88.3959, 15.8243] },
  { id: "chamelecon", name: "Устье р. Чамелекон", position: [-87.7913, 15.8946] },
];

const MOUTH_CAPTURE_M = 5_000;
const OPEN_SEA_ID = "open-sea";

function sourceOf(member: Member): string {
  const end = member.stranded?.position ?? member.position;
  let best: { id: string; distance: number } | null = null;
  for (const mouth of RIVER_MOUTHS) {
    const [dx, dy] = toLocalMeters(mouth.position, end);
    const distance = Math.hypot(dx, dy);
    if (distance <= MOUTH_CAPTURE_M && (!best || distance < best.distance))
      best = { id: mouth.id, distance };
  }
  return best?.id ?? OPEN_SEA_ID;
}

function sourceEstimates(members: readonly Member[]): SourceEstimate[] {
  const counts = new Map<string, number>();
  for (const member of members) {
    const id = sourceOf(member);
    counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  const rivers = RIVER_MOUTHS.filter((mouth) => counts.has(mouth.id)).map((mouth) => ({
    id: mouth.id,
    name: mouth.name,
    position: mouth.position,
    probability: wilson(counts.get(mouth.id) ?? 0, members.length),
    members: counts.get(mouth.id) ?? 0,
  }));
  const openSea = counts.get(OPEN_SEA_ID) ?? 0;
  return [
    ...rivers.sort((a, b) => b.members - a.members),
    ...(openSea
      ? [
          {
            id: OPEN_SEA_ID,
            name: "Не определено — открытое море",
            position: null,
            probability: wilson(openSea, members.length),
            members: openSea,
          },
        ]
      : []),
  ];
}

function buildForecast(candidate: DebrisCandidate, index: number): DriftForecastDetail {
  const forward = runEnsemble(candidate, FORECAST_HOURS, 1, 1_009 + index * 7_919);
  const backward = runEnsemble(
    candidate,
    DEMO_FORECAST_RUN.hindcastHours,
    -1,
    5_003 + index * 7_919,
  );
  const medianPath = forward.hourly.map((positions) => roundPosition(medianPosition(positions)));
  const hindcastPath = backward.hourly
    .map((positions) => roundPosition(medianPosition(positions)))
    .reverse();
  const beaching = beachingRisks(forward.members);
  const stranded = forward.members.filter((member) => member.stranded).length;
  const top = beaching[0];
  return {
    candidateId: candidate.id,
    issuedAt: DEMO_FORECAST_RUN.issuedAt,
    forcing: {
      currents: DEMO_FORECAST_RUN.currents,
      wind: DEMO_FORECAST_RUN.wind,
      waves: null,
      runAt: DEMO_FORECAST_RUN.runAt,
    },
    windageRatio: DEMO_FORECAST_RUN.windageRatio,
    origin: roundPosition(candidate.centroid),
    medianPath,
    envelopes: FORECAST_HORIZONS_H.map((horizonH) => ({
      horizonH,
      median: medianPath[horizonH],
      polygon: envelopeOf(forward.hourly[horizonH]),
      probability: 0.9,
    })),
    beachingRisk:
      top && top.severity !== "info"
        ? { segment: top.name, probability: top.probability.value }
        : null,
    hindcastPath,
    beachedByHour: forward.hourly.map((_, hour) =>
      round(
        forward.members.filter((member) => member.stranded && member.stranded.hour <= hour).length /
          forward.members.length,
        2,
      ),
    ),
    beaching,
    beachingAny: wilson(stranded, forward.members.length),
    sources: sourceEstimates(backward.members),
  };
}

export const DEMO_FORECAST_DETAILS: readonly DriftForecastDetail[] =
  DEMO_CANDIDATES.map(buildForecast);

export const DEMO_FORECASTS: readonly DriftForecast[] = DEMO_FORECAST_DETAILS;
