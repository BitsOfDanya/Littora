export type ShortcutGroupId = "global" | "map" | "rail" | "selection" | "timeline" | "forecast";

export type Shortcut = {
  combos: readonly (readonly string[])[];
  action: string;
  group: ShortcutGroupId;
  planned?: string;
};

export const SHORTCUT_GROUP_LABELS: Record<ShortcutGroupId, string> = {
  global: "Везде",
  map: "Карта",
  rail: "Шкала времени",
  selection: "Выделенный объект",
  timeline: "Динамика",
  forecast: "Прогноз",
};

export const SHORTCUT_GROUP_ORDER: readonly ShortcutGroupId[] = [
  "global",
  "map",
  "rail",
  "selection",
  "timeline",
  "forecast",
];

export const MOD_KEY_PLACEHOLDER = "Mod";

export const SHORTCUTS: readonly Shortcut[] = [
  {
    group: "global",
    combos: [["1–5"]],
    action: "Режим: Мониторинг, Динамика, Прогноз, Обследование, Модели",
  },
  {
    group: "global",
    combos: [[MOD_KEY_PLACEHOLDER, "K"]],
    action: "Поиск и команды — пока открывает эту таблицу",
  },
  { group: "global", combos: [["?"]], action: "Таблица клавиш" },
  {
    group: "global",
    combos: [["Esc"]],
    action: "Закрыть верхний слой: меню → окно → панель → выделение",
  },
  { group: "global", combos: [["T"]], action: "Тема: Ночь ↔ День" },
  { group: "global", combos: [["D"]], action: "Демо-данные: показать / скрыть" },
  { group: "map", combos: [["L"]], action: "Условные знаки: развернуть / свернуть" },
  { group: "map", combos: [["O"]], action: "Вкладка «Объекты», фокус на таблицу" },
  { group: "map", combos: [["F"]], action: "Показать район целиком" },
  { group: "map", combos: [["N"]], action: "Север вверх" },
  { group: "map", combos: [["+"], ["−"]], action: "Приблизить / отдалить" },
  { group: "map", combos: [["G"]], action: "Сетка и рамка: вкл / выкл" },
  { group: "map", combos: [["J"], ["K"]], action: "Следующий / предыдущий объект по приоритету" },
  { group: "map", combos: [["Shift", "J"]], action: "Следующий объект с неквитированным событием" },
  { group: "map", combos: [["I"]], action: "Лупа: значения пикселя" },
  { group: "map", combos: [["R"]], action: "Линейка" },
  { group: "rail", combos: [["Q"]], action: "Очередь событий: развернуть / свернуть" },
  { group: "rail", combos: [["["], ["]"]], action: "Предыдущий / следующий пролёт" },
  {
    group: "rail",
    combos: [
      ["Shift", "["],
      ["Shift", "]"],
    ],
    action: "Предыдущий / следующий пригодный пролёт",
  },
  { group: "rail", combos: [["Space"]], action: "Воспроизведение: пуск / пауза" },
  { group: "selection", combos: [["Enter"]], action: "Открыть строку списка или досье" },
  { group: "selection", combos: [["A"]], action: "Квитировать события объекта" },
  { group: "selection", combos: [["S"]], action: "Добавить в план обследования" },
  { group: "selection", combos: [["P"]], action: "Закрепить спектр в досье" },
  { group: "timeline", combos: [["C"]], action: "Способ сравнения: Шторка → Прозрачность → Линза" },
  {
    group: "timeline",
    combos: [[","], ["."]],
    action: "Сдвинуть шторку на 5 %, с Shift — на 20 %",
  },
  { group: "timeline", combos: [["X"]], action: "Поменять A и B" },
  { group: "forecast", combos: [["["], ["]"]], action: "Шаг горизонта прогноза" },
  {
    group: "forecast",
    combos: [["Shift", "1–5"]],
    action: "Горизонт +6 / +12 / +24 / +48 / +72 ч",
  },
  { group: "forecast", combos: [["M"]], action: "Частицы течений: пауза / пуск" },
];

export function shortcutMatches(shortcut: Shortcut, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase("ru");
  if (!needle) return true;
  const haystack = [
    shortcut.action,
    SHORTCUT_GROUP_LABELS[shortcut.group],
    ...shortcut.combos.flat(),
  ]
    .join(" ")
    .toLocaleLowerCase("ru");
  return haystack.includes(needle);
}
