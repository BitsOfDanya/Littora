import type { AoiGroup, AreaOfInterest } from "@/domain/aoi";

export const AOI_GROUP_LABELS: Record<AoiGroup, string> = {
  reference: "Эталонные участки",
  "russian-seas": "Моря России",
};

export const AREAS_OF_INTEREST = [
  {
    id: "gulf-of-honduras",
    name: "Гондурасский залив",
    seaName: "Карибское море",
    country: "Гондурас · Гватемала · Белиз",
    group: "reference",
    center: [-88.34, 15.92],
    zoom: 10.3,
    bbox: [-88.72, 15.72, -87.96, 16.12],
    sentinel2Tiles: ["16PCC", "16PDC", "16PEC", "16QED"],
    rationale:
      "Наиболее полно размеченный участок MARIDA: выносы мусора рекой Мотагуа после паводков",
    datasets: ["marida", "mados", "nasa-marine-debris"],
    waterLabels: [
      { name: "Гондурасский залив", position: [-88.3, 15.94], rank: "major" },
      { name: "бухта Омоа", position: [-88.12, 15.79], rank: "minor", minZoom: 9 },
      { name: "залив Аматике", position: [-88.64, 15.8], rank: "minor", minZoom: 9 },
    ],
  },
  {
    id: "gulf-of-gera",
    name: "Залив Гера, Лесбос",
    seaName: "Эгейское море",
    country: "Греция",
    group: "reference",
    center: [26.47, 39.06],
    zoom: 11.6,
    bbox: [26.36, 38.98, 26.58, 39.13],
    sentinel2Tiles: ["35SMD"],
    rationale:
      "Полигон Plastic Litter Project: контрольные мишени из HDPE и дерева известной площади",
    datasets: ["plp2021", "plp2022-2023"],
    waterLabels: [{ name: "залив Гера", position: [26.475, 39.085], rank: "major" }],
  },
  {
    id: "durban",
    name: "Дурбан",
    seaName: "Индийский океан",
    country: "ЮАР",
    group: "reference",
    center: [31.06, -29.88],
    zoom: 10.8,
    bbox: [30.85, -30.05, 31.25, -29.7],
    sentinel2Tiles: [],
    rationale: "Выносы мусора после паводков; отдельный тестовый набор в marinedebrisdetector",
    datasets: ["marida", "marinedebrisdetector"],
    waterLabels: [{ name: "Индийский океан", position: [31.16, -29.93], rank: "major" }],
  },
  {
    id: "novorossiysk",
    name: "Цемесская бухта",
    seaName: "Чёрное море",
    country: "Россия",
    group: "russian-seas",
    center: [37.8, 44.68],
    zoom: 11,
    bbox: [37.6, 44.55, 38.0, 44.8],
    sentinel2Tiles: [],
    rationale: "Крупный порт и судоходство; региональная модель течений BLKSEA 1/40°",
    datasets: [],
    waterLabels: [
      { name: "Цемесская бухта", position: [37.845, 44.672], rank: "major" },
      { name: "Чёрное море", position: [37.66, 44.62], rank: "minor" },
    ],
  },
  {
    id: "kerch-strait",
    name: "Керченский пролив",
    seaName: "Азовское и Чёрное моря",
    country: "Россия",
    group: "russian-seas",
    center: [36.55, 45.25],
    zoom: 9.6,
    bbox: [36.2, 44.9, 36.9, 45.5],
    sentinel2Tiles: [],
    rationale: "Водообмен Азовского и Чёрного морей, интенсивное судоходство",
    datasets: [],
    waterLabels: [
      { name: "Керченский пролив", position: [36.58, 45.3], rank: "major" },
      { name: "Чёрное море", position: [36.53, 45.08], rank: "minor" },
    ],
  },
  {
    id: "neva-bay",
    name: "Невская губа",
    seaName: "Финский залив, Балтийское море",
    country: "Россия",
    group: "russian-seas",
    center: [29.85, 59.95],
    zoom: 10,
    bbox: [29.4, 59.8, 30.3, 60.1],
    sentinel2Tiles: [],
    rationale: "Сток Невы и городская агломерация; модель течений BALTICSEA ~1,85 км",
    datasets: [],
    waterLabels: [
      { name: "Невская губа", position: [30.06, 59.94], rank: "major" },
      { name: "Финский залив", position: [29.52, 60.0], rank: "minor" },
    ],
  },
  {
    id: "peter-the-great-bay",
    name: "Амурский залив",
    seaName: "Японское море",
    country: "Россия",
    group: "russian-seas",
    center: [131.85, 43.12],
    zoom: 10,
    bbox: [131.5, 42.9, 132.2, 43.35],
    sentinel2Tiles: [],
    rationale: "Залив Петра Великого у Владивостока: сток рек и портовая активность",
    datasets: [],
    waterLabels: [
      { name: "Амурский залив", position: [131.8, 43.18], rank: "major" },
      { name: "Уссурийский залив", position: [132.12, 43.08], rank: "minor" },
    ],
  },
] as const satisfies readonly AreaOfInterest[];

export type AoiId = (typeof AREAS_OF_INTEREST)[number]["id"];

export const DEFAULT_AOI_ID: AoiId = "gulf-of-honduras";

export function findAoi(id: string): AreaOfInterest | undefined {
  return AREAS_OF_INTEREST.find((aoi) => aoi.id === id);
}
