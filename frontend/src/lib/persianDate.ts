// Persian (Jalali) calendar, from the browser's own Intl support.
const INPUT_FORMAT = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const LONG_FORMAT = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

/** Today as a Persian date for an input, e.g. ۱۴۰۵/۰۷/۲۵. */
export function persianDateInput(date: Date = new Date()): string {
  return INPUT_FORMAT.format(date);
}

/** Today as a Persian sentence, e.g. جمعه ۲۴ مهر ۱۴۰۵. The order is fixed here, not left to the browser. */
export function persianLongDate(date: Date = new Date()): string {
  const parts = LONG_FORMAT.formatToParts(date);
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value ?? "";
  return `${value("weekday")} ${value("day")} ${value("month")} ${value("year")}`;
}
