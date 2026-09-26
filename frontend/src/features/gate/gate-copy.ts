export const GATE_COPY = {
  region: "Littora — вход в рабочее пространство",
  button: "Открыть рабочее пространство",
  buttonOpening: "Открываем…",
  announcement: (mode: string, aoi: string) => `Рабочее пространство открыто: «${mode}», ${aoi}`,
} as const;

export const GATE_FACTS: readonly { value: string; label: string }[] = [
  { value: "F1 0,91", label: "детектор мусора на отложенном test MARIDA, режим сервиса" },
  { value: "шт./км²", label: "концентрация по полевым данным с интервалом и статусом" },
  { value: "7 пар", label: "судно и спутник в один день: сравнение по каждой" },
  { value: "15 функций", label: "маски, композиты, дрейф, обследование, отчёт моделей" },
];

export const GATE_STEPS: readonly string[] = [
  "район и дата",
  "анализ снимка",
  "зона и сравнение с судном",
  "выгрузка GeoJSON и CSV",
];
