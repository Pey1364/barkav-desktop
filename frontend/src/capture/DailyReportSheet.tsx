import { useState } from "react";
import { CONSTRUCTION_PHASES, WEATHER_OPTIONS } from "../data/taxonomy";
import { CloseIcon } from "../icons";
import { persianDateInput, persianLongDate } from "../lib/persianDate";

export interface DailyReport {
  id: string;
  reportDate: string;
  phase: string;
  weather: string;
  temperature: string;
  body: string;
}

interface Props {
  onClose: () => void;
  onSave: (report: DailyReport) => void;
}

export function DailyReportSheet({ onClose, onSave }: Props) {
  const [reportDate, setReportDate] = useState(persianDateInput());
  const [phase, setPhase] = useState("");
  const [weather, setWeather] = useState("");
  const [temperature, setTemperature] = useState("");
  const [body, setBody] = useState("");

  return (
    <div className="sheet-backdrop" role="dialog" aria-modal="true" aria-label="گزارش روزانه">
      <div className="sheet">
        <div className="sheet-head">
          <h3>گزارش روزانه</h3>
          <button className="icon-btn" type="button" aria-label="بستن" onClick={onClose}>
            <CloseIcon />
          </button>
        </div>
        <p className="step-label">{persianLongDate()}</p>

        <div className="field">
          <label htmlFor="report-date">تاریخ شمسی</label>
          <input id="report-date" className="input" inputMode="numeric" value={reportDate} onChange={(event) => setReportDate(event.target.value)} />
          <small>پیش‌فرض: تاریخ امروز.</small>
        </div>

        <div className="field">
          <label htmlFor="report-phase">فاز ساخت</label>
          <select id="report-phase" className="select" value={phase} onChange={(event) => setPhase(event.target.value)}>
            <option value="">انتخاب کنید</option>
            {CONSTRUCTION_PHASES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <span>آب‌وهوا</span>
          <div className="chips" role="radiogroup" aria-label="آب‌وهوا">
            {WEATHER_OPTIONS.map((item) => (
              <button
                key={item}
                type="button"
                role="radio"
                aria-checked={weather === item}
                className={`chip${weather === item ? " on" : ""}`}
                onClick={() => setWeather(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label htmlFor="report-temp">دما (درجه‌ی سانتی‌گراد)</label>
          <input id="report-temp" className="input" inputMode="numeric" value={temperature} onChange={(event) => setTemperature(event.target.value)} placeholder="اختیاری" />
        </div>

        <div className="field">
          <label htmlFor="report-body">شرح گزارش روزانه</label>
          <textarea id="report-body" className="textarea" value={body} onChange={(event) => setBody(event.target.value)} />
        </div>

        <div className="actions">
          <button
            className="btn-primary"
            type="button"
            disabled={!body.trim()}
            onClick={() =>
              onSave({
                id: `report-${Date.now()}`,
                reportDate: reportDate.trim(),
                phase,
                weather,
                temperature: temperature.trim(),
                body: body.trim(),
              })
            }
          >
            ثبت گزارش
          </button>
        </div>
      </div>
    </div>
  );
}
