// Jalali (Persian) calendar. The browser's own Persian calendar (Intl) does the conversion, so
// the result is the same calendar the phone and the desktop show. Works in the phone's time zone.
import { toAsciiDigits, toFa } from "./digits";

export interface JalaliDate {
  jy: number;
  jm: number;
  jd: number;
}

export const MONTH_NAMES = [
  "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
  "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
];

// Saturday first, the first day of the week in Iran.
export const WEEKDAY_SHORT = ["ش", "ی", "د", "س", "چ", "پ", "ج"];

const DAY_MS = 86_400_000;
const PARTS = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "numeric", day: "numeric" });
const ASCII = "۰۱۲۳۴۵۶۷۸۹";

function readNumber(parts: Intl.DateTimeFormatPart[], type: Intl.DateTimeFormatPartTypes): number {
  const value = parts.find((part) => part.type === type)?.value ?? "";
  return Number(value.replace(/[۰-۹]/g, (digit) => String(ASCII.indexOf(digit))));
}

/** The Jalali date of a JavaScript Date. */
export function jalaliOf(date: Date): JalaliDate {
  const parts = PARTS.formatToParts(date);
  return { jy: readNumber(parts, "year"), jm: readNumber(parts, "month"), jd: readNumber(parts, "day") };
}

const key = (date: JalaliDate) => date.jy * 10_000 + date.jm * 100 + date.jd;

/** The Gregorian day (local midnight) on which a Jalali day falls. */
export function jalaliToDate(target: JalaliDate): Date {
  // Nowruz falls near 21 March, so start there and walk to the day, one day at a time.
  const current = new Date(target.jy + 621, 2, 21 + Math.round((target.jm - 1) * 30.4) + (target.jd - 1));
  for (let steps = 0; steps < 800; steps += 1) {
    const found = jalaliOf(current);
    if (found.jy === target.jy && found.jm === target.jm && found.jd === target.jd) return current;
    current.setDate(current.getDate() + (key(found) < key(target) ? 1 : -1));
  }
  throw new Error("the Jalali date could not be found");
}

/** Number of days in a Jalali month (29 to 31). */
export function jalaliMonthLength(jy: number, jm: number): number {
  const first = jalaliToDate({ jy, jm, jd: 1 });
  const nextMonth = jm === 12 ? { jy: jy + 1, jm: 1, jd: 1 } : { jy, jm: jm + 1, jd: 1 };
  const next = jalaliToDate(nextMonth);
  return Math.round((Date.UTC(next.getFullYear(), next.getMonth(), next.getDate()) - Date.UTC(first.getFullYear(), first.getMonth(), first.getDate())) / DAY_MS);
}

/** Saturday = 0 ... Friday = 6 for the Jalali day given. */
export function weekdayIndexOf(date: JalaliDate): number {
  return (jalaliToDate(date).getDay() + 1) % 7;
}

export function sameDate(a: JalaliDate, b: JalaliDate): boolean {
  return a.jy === b.jy && a.jm === b.jm && a.jd === b.jd;
}

/** "۱۴۰۵/۰۷/۲۴" with Persian digits and zero padding. */
export function formatJalali(date: JalaliDate): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return toFa(`${date.jy}/${pad(date.jm)}/${pad(date.jd)}`);
}

/** Accepts Persian or ASCII digits, "/" or "-". Returns null when the text is not a real date. */
export function parseJalali(text: string): JalaliDate | null {
  const match = /^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$/.exec(toAsciiDigits(text));
  if (!match) return null;
  const jy = Number(match[1]);
  const jm = Number(match[2]);
  const jd = Number(match[3]);
  if (jm < 1 || jm > 12 || jd < 1 || jd > jalaliMonthLength(jy, jm)) return null;
  return { jy, jm, jd };
}

export function todayJalali(): JalaliDate {
  return jalaliOf(new Date());
}
