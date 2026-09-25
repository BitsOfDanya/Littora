import type { DatasetReference, DatasetRole } from "@/domain/dataset";

export type DatasetEntry = DatasetReference & {
  roles: readonly DatasetRole[];
  source: string;
  contents: string;
  paperDoi: string;
  citation: string;
};

export const DATASET_ROLE_LABEL: Record<DatasetRole, string> = {
  training: "обучение",
  validation: "проверка",
  calibration: "калибровка",
  reference: "эталон",
};

export const doiUrl = (doi: string) => `https://doi.org/${doi}`;

export const DATASETS: readonly DatasetEntry[] = [
  {
    id: "marida",
    name: "MARIDA",
    fullName: "Marine Debris Archive",
    role: "training",
    roles: ["training", "validation"],
    source: "Kikaki et al., 2022 · PLOS ONE",
    contents:
      "1\u202F381 патч 256 × 256\u202Fпикс. из 63 сцен; маска классов и маска уверенности разметчика; сплиты 694 / 328 / 359.",
    labels: "15 классов: мусор, саргассум, пена, суда, следы, облака, типы воды",
    sensor: "Sentinel-2, 11 каналов (без B09 и B10), ACOLITE rhorc, сетка 10 м",
    period: "11.2015–01.2021",
    coverage: "11 стран; ≈ 90\u202F% размеченных пикселей — Гондурасский залив",
    volume: "1,16 ГБ (4,38 ГБ распак.)",
    license: "CC BY 4.0",
    doi: "10.5281/zenodo.5151941",
    paperDoi: "10.1371/journal.pone.0262247",
    useInLittora: "Тестовый сплит для проверки; спектральный классификатор; классы-двойники",
    citation:
      "Kikaki K., Kakogeorgiou I., Mikeli P., Raitsos D. E., Karantzalos K. MARIDA: A benchmark for Marine Debris detection from Sentinel-2 remote sensing data. PLOS ONE. 2022;17(1):e0262247. https://doi.org/10.1371/journal.pone.0262247. Dataset: Zenodo, https://doi.org/10.5281/zenodo.5151941",
  },
  {
    id: "mados",
    name: "MADOS",
    fullName: "Marine Debris and Oil Spill",
    role: "training",
    roles: ["training"],
    source: "Kikaki et al., 2024 · ISPRS J. Photogramm.",
    contents:
      "2\u202F803 фрагмента 240 × 240\u202Fпикс. из 174 сцен, 47 тайлов; ≈ 1,5 млн размеченных пикселей.",
    labels: "15 классов, включая мусор, нефть, пену и саргассум",
    sensor: "Sentinel-2, 11 каналов, ACOLITE rhorc, родные 10 / 20 / 60 м",
    period: "2015–2022",
    coverage: "весь мир",
    volume: "4,04 ГБ (5,35 ГБ распак.)",
    license: "CC BY 4.0",
    doi: "10.5281/zenodo.10664073",
    paperDoi: "10.1016/j.isprsjprs.2024.02.017",
    useInLittora: "Основной обучающий набор сегментации; базовая модель MariNeXt",
    citation:
      "Kikaki K., Kakogeorgiou I., Hoteit I., Karantzalos K. Detecting Marine Pollutants and Sea Surface Features with Deep Learning in Sentinel-2 Imagery. ISPRS Journal of Photogrammetry and Remote Sensing. 2024. https://doi.org/10.1016/j.isprsjprs.2024.02.017. Dataset: MADOS — Marine Debris and Oil Spill, Zenodo, https://doi.org/10.5281/zenodo.10664073",
  },
  {
    id: "plp2019",
    name: "PLP 2019",
    fullName: "Plastic Litter Project 2019",
    role: "calibration",
    roles: ["calibration"],
    source: "Topouzelis et al., 2020 · Remote Sensing",
    contents:
      "Плавучие мишени из бутылок, пакетов и тростника (шесть 5 × 5 м и две 1 × 5 м) под пролётами Sentinel-2.",
    labels: "Доля пластика в каждом пикселе Sentinel-2",
    sensor: "Sentinel-2 после ACOLITE + снимки БПЛА",
    period: "04–06.2019",
    coverage: "пляж Цамакия, Лесбос",
    volume: "68,9 МБ",
    license: "CC BY 4.0",
    doi: "10.5281/zenodo.3752719",
    paperDoi: "10.3390/rs12122013",
    useInLittora: "Калибровка доли покрытия пикселя по известному проценту пластика",
    citation:
      "Topouzelis K., Papageorgiou D., Karagaitanakis A., Papakonstantinou A., Arias Ballesteros M. Remote Sensing of Sea Surface Artificial Floating Plastic Targets with Sentinel-2 and Unmanned Aerial Systems (Plastic Litter Project 2019). Remote Sensing. 2020;12(12):2013. https://doi.org/10.3390/rs12122013. Dataset: PLP2019 dataset, Zenodo, 2020, https://doi.org/10.5281/zenodo.3752719",
  },
  {
    id: "plp2021",
    name: "PLP 2021",
    fullName: "Plastic Litter Project 2021",
    role: "validation",
    roles: ["validation", "reference"],
    source: "Papageorgiou et al., 2022 · Remote Sensing",
    contents:
      "Мишени из сетки HDPE и деревянных досок, по ≈ 600\u202Fм² каждая, на постоянной швартовке; 22 пролёта с шагом 5 дней.",
    labels: "Положение и материал мишеней по ортофото; пиксельных масок нет",
    sensor: "Sentinel-2 L1C (13 каналов) + ACOLITE L2W + ортофото",
    period: "06–10.2021",
    coverage: "залив Гера, Лесбос",
    volume: "≈ 159,5 ГБ, 22 архива по датам",
    license: "CC BY 4.0",
    doi: "10.5281/zenodo.7085112",
    paperDoi: "10.3390/rs14235997",
    useInLittora: "Спектры чистого пластика и дерева; устойчивость признаков во времени",
    citation:
      "Papageorgiou D., Topouzelis K. Plastic Litter Project 2021 dataset. Zenodo. 2022. https://doi.org/10.5281/zenodo.7085112. Article: Papageorgiou D., Topouzelis K., Suaria G., Aliani S., Corradi P. Sentinel-2 Detection of Floating Marine Litter Targets with Partial Spectral Unmixing and Spectral Comparison with Other Floating Materials (Plastic Litter Project 2021). Remote Sensing. 2022;14(23):5997. https://doi.org/10.3390/rs14235997",
  },
  {
    id: "plp2022-2023",
    name: "PLP 2022–23",
    fullName: "Plastic Litter Project 2022–2023 · Minimum Detection Fraction",
    role: "calibration",
    roles: ["calibration"],
    source: "Papageorgiou, Topouzelis, 2024 · IJAEOG",
    contents:
      "Листы HDPE площадью 1, 2 и 3\u202Fм²; для Sentinel-2 порог обнаружения — выше 3\u202Fм² на пиксель 10 × 10 м.",
    labels: "Известные размеры и положения мишеней по снимкам БПЛА",
    sensor: "Sentinel-2 L1C + ACOLITE L2W; PlanetScope SuperDove",
    period: "2022–2023, 5 дат Sentinel-2",
    coverage: "залив Гера, Лесбос",
    volume: "3,83 ГБ",
    license: "CC BY 4.0",
    doi: "10.5281/zenodo.10046182",
    paperDoi: "10.1016/j.jag.2024.104245",
    useInLittora: "Граница «не обнаружимо»: ниже неё пиксель — не «чистая вода»",
    citation:
      "Papageorgiou D., Topouzelis K. Plastic Litter Project 2022-2023 - Minimum Detection Fraction Dataset. Zenodo. 2023. https://doi.org/10.5281/zenodo.10046182. Article: Experimental observations of marginally detectable floating plastic targets in Sentinel-2 and Planet Super Dove imagery. International Journal of Applied Earth Observation and Geoinformation. 2024. https://doi.org/10.1016/j.jag.2024.104245",
  },
  {
    id: "windrows-med",
    name: "Windrows MED",
    fullName: "Mediterranean Sentinel-2 Litter Windrows Catalogue v1.0",
    role: "reference",
    roles: ["reference"],
    source: "Cózar et al., 2024 · Nature Communications",
    contents:
      "14\u202F374 полосы плавающего мусора длиннее 70 м, найденные детектором и проверенные человеком в ≈ 300\u202F000 снимков.",
    labels: "Пиксели каждой полосы с 13-канальным спектром; только положительные примеры",
    sensor: "Sentinel-2 L1C, отражение без атмосферной коррекции, все каналы на сетке 10 м",
    period: "07.2015–09.2021",
    coverage: "всё Средиземное море",
    volume: "2,06 ГБ",
    license: "CC BY 4.0",
    doi: "10.5281/zenodo.11045944",
    paperDoi: "10.1038/s41467-024-48674-7",
    useInLittora: "Эталон горячих точек и сезонности",
    citation:
      "Cózar A., Arias M., Suaria G., et al. Proof of concept for a new sensor to monitor marine litter from space. Nature Communications. 2024;15:4637. https://doi.org/10.1038/s41467-024-48674-7. Dataset: Mediterranean Sentinel-2 Litter Windrows Catalogue v1.0, Zenodo, 2024, https://doi.org/10.5281/zenodo.11045944",
  },
];
