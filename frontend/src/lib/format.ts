import { toAsciiDigits } from "./digits";

// Persian digits with thousands separators (٬), e.g. 250000000 -> ۲۵۰٬۰۰۰٬۰۰۰.
const FA_NUMBER = new Intl.NumberFormat("fa-IR");

/** Show an amount stored as plain digits. Empty stays empty. */
export function formatAmount(value: string | number): string {
  const digits = toAsciiDigits(String(value)).replace(/\D/g, "");
  return digits ? FA_NUMBER.format(Number(digits)) : "";
}

/** The value sent in the sealed payload: plain ASCII digits. */
export function plainAmount(value: string): string {
  return toAsciiDigits(value).replace(/\D/g, "");
}
