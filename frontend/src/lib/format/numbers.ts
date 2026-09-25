const LOCALE = "ru-RU";

const formatters = new Map<string, Intl.NumberFormat>();

function formatterFor(
  minimumFractionDigits: number,
  maximumFractionDigits: number,
): Intl.NumberFormat {
  const key = `${minimumFractionDigits}:${maximumFractionDigits}`;
  let formatter = formatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat(LOCALE, { minimumFractionDigits, maximumFractionDigits });
    formatters.set(key, formatter);
  }
  return formatter;
}

export function formatNumber(value: number, fractionDigits = 0): string {
  return formatterFor(fractionDigits, fractionDigits).format(value);
}

export function formatSigned(value: number, fractionDigits = 0): string {
  const formatted = formatNumber(Math.abs(value), fractionDigits);
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `−${formatted}`;
  return formatted;
}

export function formatPercent(ratio: number, fractionDigits = 0): string {
  return `${formatNumber(ratio * 100, fractionDigits)} %`;
}

export function formatSignedPercent(ratio: number, fractionDigits = 0): string {
  return `${formatSigned(ratio * 100, fractionDigits)} %`;
}

export function formatArea(areaM2: number): string {
  if (areaM2 >= 1_000_000) return `${formatNumber(areaM2 / 1_000_000, 2)} км²`;
  if (areaM2 >= 10_000) return `${formatNumber(areaM2 / 1_000_000, 3)} км²`;
  return `${formatNumber(areaM2)} м²`;
}

export function formatDistance(meters: number): string {
  if (meters >= 10_000) return `${formatNumber(meters / 1000)} км`;
  if (meters >= 1000) return `${formatNumber(meters / 1000, 1)} км`;
  return `${formatNumber(meters)} м`;
}
