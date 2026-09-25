export const GATE_COPY = {
  region: "Littora — вход в рабочее пространство",
  button: "Открыть рабочее пространство",
  buttonOpening: "Открываем…",
  announcement: (mode: string, aoi: string) => `Рабочее пространство открыто: «${mode}», ${aoi}`,
} as const;
