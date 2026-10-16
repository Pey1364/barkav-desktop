const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

/** Show numbers with Persian digits, e.g. 3 -> ۳. */
export function toFa(value: number | string): string {
  return String(value).replace(/\d/g, (digit) => PERSIAN_DIGITS[Number(digit)]);
}

/** Back to ASCII digits for the sealed payload, e.g. ۱۴۰۵/۰۷/۲۴ -> 1405/07/24. */
export function toAsciiDigits(value: string): string {
  return value.replace(/[۰-۹]/g, (digit) => String(PERSIAN_DIGITS.indexOf(digit)));
}
