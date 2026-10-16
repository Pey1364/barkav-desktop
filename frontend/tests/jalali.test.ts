import { describe, expect, it } from "vitest";
import { formatJalali, jalaliMonthLength, jalaliOf, jalaliToDate, parseJalali, weekdayIndexOf } from "../src/lib/jalali";

describe("Jalali calendar", () => {
  it("converts 2026-10-16 to 24 Mehr 1405 and back", () => {
    const date = new Date(2026, 9, 16);
    expect(jalaliOf(date)).toEqual({ jy: 1405, jm: 7, jd: 24 });
    expect(jalaliToDate({ jy: 1405, jm: 7, jd: 24 }).getTime()).toBe(date.getTime());
  });

  it("finds Nowruz 1404 on 21 March 2025", () => {
    expect(jalaliToDate({ jy: 1404, jm: 1, jd: 1 }).getTime()).toBe(new Date(2025, 2, 21).getTime());
  });

  it("gives month lengths of 29 to 31 days, with leap years handled", () => {
    for (let jy = 1400; jy <= 1408; jy += 1) {
      for (let jm = 1; jm <= 12; jm += 1) {
        const length = jalaliMonthLength(jy, jm);
        expect(length).toBeGreaterThanOrEqual(29);
        expect(length).toBeLessThanOrEqual(31);
      }
    }
    expect(jalaliMonthLength(1404, 12)).toBe(29);
    expect(jalaliMonthLength(1403, 12)).toBe(30);
  });

  it("starts the week on Saturday (1 Mehr 1405 is a Wednesday)", () => {
    expect(weekdayIndexOf({ jy: 1405, jm: 7, jd: 1 })).toBe(4);
  });

  it("parses Persian and ASCII input and rejects impossible dates", () => {
    expect(parseJalali("۱۴۰۵/۰۷/۲۴")).toEqual({ jy: 1405, jm: 7, jd: 24 });
    expect(parseJalali("1405-07-24")).toEqual({ jy: 1405, jm: 7, jd: 24 });
    expect(parseJalali("1405/13/01")).toBeNull();
    expect(parseJalali("1405/07/31")).toBeNull();
    expect(parseJalali("hello")).toBeNull();
  });

  it("formats with Persian digits and zero padding", () => {
    expect(formatJalali({ jy: 1405, jm: 7, jd: 4 })).toBe("۱۴۰۵/۰۷/۰۴");
  });
});
