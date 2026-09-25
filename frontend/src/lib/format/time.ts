const MONTHS_GENITIVE = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
] as const;

const MONTHS_SHORT = [
  "янв",
  "фев",
  "мар",
  "апр",
  "май",
  "июн",
  "июл",
  "авг",
  "сен",
  "окт",
  "ноя",
  "дек",
] as const;

const pad = (value: number) => String(value).padStart(2, "0");

export function formatUtcDateTime(iso: string): string {
  const date = new Date(iso);
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}Z`;
}

export function formatUtcDate(iso: string): string {
  return iso.slice(0, 10);
}

export function formatUtcTime(iso: string): string {
  const date = new Date(iso);
  return `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}Z`;
}

export function formatLongDate(iso: string): string {
  const date = new Date(iso);
  return `${date.getUTCDate()} ${MONTHS_GENITIVE[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

export function formatShortDate(iso: string): string {
  const date = new Date(iso);
  return `${date.getUTCDate()} ${MONTHS_SHORT[date.getUTCMonth()]}`;
}

export function monthShortName(monthIndex: number): string {
  return MONTHS_SHORT[monthIndex];
}

export function formatAge(fromIso: string, now: Date): string {
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(fromIso).getTime()) / 60_000));
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч`;
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days} д ${restHours} ч` : `${days} д`;
}
