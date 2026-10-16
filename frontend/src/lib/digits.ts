const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

/** Show numbers with Persian digits, e.g. 3 -> ۳. */
export function toFa(value: number | string): string {
  return String(value).replace(/\d/g, (digit) => PERSIAN_DIGITS[Number(digit)]);
}
