const ISO_TIMESTAMP_PATTERN =
  /\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b/g;

const localDateTimeParts = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const localZoneParts = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZoneName: "shortOffset",
});

function getPart(parts: Intl.DateTimeFormatPart[], type: Intl.DateTimeFormatPartTypes): string {
  return parts.find((part) => part.type === type)?.value ?? "";
}

function normalizeHour(hour: string): string {
  return hour === "24" ? "00" : hour;
}

export function formatLocalTimestamp(value?: string | null): string {
  const input = typeof value === "string" ? value.trim() : "";
  if (!input) return "";

  const date = new Date(input);
  if (Number.isNaN(date.getTime())) return input;

  const parts = localDateTimeParts.formatToParts(date);
  const zone =
    localZoneParts.formatToParts(date).find((part) => part.type === "timeZoneName")?.value ||
    Intl.DateTimeFormat().resolvedOptions().timeZone ||
    "local";

  return [
    `${getPart(parts, "year")}-${getPart(parts, "month")}-${getPart(parts, "day")}`,
    `${normalizeHour(getPart(parts, "hour"))}:${getPart(parts, "minute")}:${getPart(parts, "second")}`,
    zone,
  ].join(" ");
}

export function formatLocalTextTimestamps(value?: string | null): string {
  const input = value ?? "";
  return input.replace(ISO_TIMESTAMP_PATTERN, (match) => formatLocalTimestamp(match));
}
