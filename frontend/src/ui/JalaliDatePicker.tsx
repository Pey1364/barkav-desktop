import { useState } from "react";
import { toFa } from "../lib/digits";
import {
  MONTH_NAMES,
  WEEKDAY_SHORT,
  formatJalali,
  jalaliMonthLength,
  parseJalali,
  sameDate,
  todayJalali,
  weekdayIndexOf,
} from "../lib/jalali";
import { CalendarIcon, ChevronLeftIcon, ChevronRightIcon } from "../icons";

interface Props {
  id: string;
  value: string;
  onChange: (value: string) => void;
}

/** A Jalali date field with a month calendar, written right to left, next to the text box. */
export function JalaliDatePicker({ id, value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const selected = parseJalali(value);
  const [shown, setShown] = useState(() => {
    const base = selected ?? todayJalali();
    return { jy: base.jy, jm: base.jm };
  });
  const today = todayJalali();

  function move(delta: number) {
    setShown((current) => {
      const index = current.jy * 12 + (current.jm - 1) + delta;
      return { jy: Math.floor(index / 12), jm: (index % 12) + 1 };
    });
  }

  function toggle() {
    if (!open) {
      const base = parseJalali(value) ?? todayJalali();
      setShown({ jy: base.jy, jm: base.jm });
    }
    setOpen(!open);
  }

  const leading = weekdayIndexOf({ jy: shown.jy, jm: shown.jm, jd: 1 });
  const length = jalaliMonthLength(shown.jy, shown.jm);
  const cells: (number | null)[] = [...Array(leading).fill(null), ...Array.from({ length }, (_, index) => index + 1)];
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div className="jdp">
      <div className="jdp-field">
        <input
          id={id}
          className="input"
          inputMode="numeric"
          dir="ltr"
          value={value}
          placeholder="۱۴۰۵/۰۷/۲۴"
          onChange={(event) => onChange(event.target.value)}
        />
        <button type="button" className="icon-btn" aria-label="باز کردن تقویم" aria-expanded={open} onClick={toggle}>
          <CalendarIcon />
        </button>
      </div>

      {open && (
        <div className="jdp-pop glass" dir="rtl" role="dialog" aria-label="تقویم شمسی">
          <div className="jdp-head">
            <button type="button" className="icon-btn" aria-label="ماه بعد" onClick={() => move(1)}>
              <ChevronLeftIcon />
            </button>
            <strong>
              {MONTH_NAMES[shown.jm - 1]} {toFa(shown.jy)}
            </strong>
            <button type="button" className="icon-btn" aria-label="ماه قبل" onClick={() => move(-1)}>
              <ChevronRightIcon />
            </button>
          </div>
          <div className="jdp-grid jdp-weekdays">
            {WEEKDAY_SHORT.map((name) => (
              <span key={name}>{name}</span>
            ))}
          </div>
          <div className="jdp-grid">
            {cells.map((day, index) =>
              day === null ? (
                <span key={`blank-${index}`} />
              ) : (
                <button
                  key={day}
                  type="button"
                  className={[
                    "jdp-day",
                    selected && sameDate(selected, { jy: shown.jy, jm: shown.jm, jd: day }) ? "on" : "",
                    sameDate(today, { jy: shown.jy, jm: shown.jm, jd: day }) ? "today" : "",
                  ].join(" ")}
                  onClick={() => {
                    onChange(formatJalali({ jy: shown.jy, jm: shown.jm, jd: day }));
                    setOpen(false);
                  }}
                >
                  {toFa(day)}
                </button>
              ),
            )}
          </div>
          <div className="actions">
            <button type="button" className="btn-ghost" onClick={() => { onChange(formatJalali(today)); setOpen(false); }}>
              امروز
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
