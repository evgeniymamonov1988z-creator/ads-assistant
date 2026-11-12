export const SOURCE_LABEL: Record<string, string> = {
  yandex: "Яндекс Директ",
  google: "Google Ads",
};

export const ACTION_LABEL: Record<string, string> = {
  bid: "Ставки",
  minus_words: "Минус-слова",
  budget: "Бюджет",
};

export const STATUS_LABEL: Record<string, string> = {
  proposed: "предложено",
  confirmed: "подтверждено",
  failed: "ошибка",
  rejected: "отклонено",
  stale: "устарело",
};

export const PRIORITY_LABEL: Record<string, string> = {
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};

export function money(value: number | null | undefined, currency = "RUB"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = currency === "RUB" ? "₽" : currency;
  const formatted = value.toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${formatted} ${sign}`;
}

export function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("ru-RU", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function int(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Math.round(value).toLocaleString("ru-RU");
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
