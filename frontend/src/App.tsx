import { useEffect, useState } from "react";
import { CaptureFlow } from "./capture/CaptureFlow";
import { DailyReportSheet, type DailyReport } from "./capture/DailyReportSheet";
import { SAMPLE_ITEMS, STATUS_LABEL, type FieldItem, type ItemStatus } from "./data/sample";
import { CameraIcon, DesktopIcon, GearIcon, ReceiptIcon, ReportIcon } from "./icons";
import { toFa } from "./lib/digits";
import { persianDateInput, persianLongDate } from "./lib/persianDate";

type Tab = "receipts" | "reports" | "settings";

function dotClass(status: ItemStatus): string {
  if (status === "pending" || status === "waiting") return "wait";
  if (status === "review") return "review";
  return "";
}

export function App() {
  const [tab, setTab] = useState<Tab>("receipts");
  const [items, setItems] = useState<FieldItem[]>(SAMPLE_ITEMS);
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [capture, setCapture] = useState<{ editing: FieldItem | null } | null>(null);
  const [dailyOpen, setDailyOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 2800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const todayCount = items.filter((item) => item.day === "today").length;
  const waitingCount = items.filter((item) => item.status === "waiting" || item.status === "pending").length;
  const todayReport = reports.some((report) => report.reportDate === persianDateInput());

  function saveItem(item: FieldItem) {
    setItems((current) => [item, ...current.filter((existing) => existing.id !== item.id)]);
    setCapture(null);
    setToast(
      item.status === "pending"
        ? "ثبت سریع انجام شد و در پندینگ است. (نمایشی؛ هنوز به Drive وصل نیست)"
        : "سند برای بازبینی ثبت شد. (نمایشی؛ هنوز به Drive وصل نیست)",
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          BARKAV<span>Field</span>
        </div>
        <div className="avatar" aria-hidden="true">
          پ
        </div>
      </header>

      {tab === "receipts" && (
        <>
          <section className="glass hero">
            <p className="kicker">{persianLongDate()}</p>
            <h2>رسید را از میدان بفرست</h2>
            <button className="btn-primary" type="button" onClick={() => setCapture({ editing: null })}>
              <CameraIcon /> ثبت رسید
            </button>
          </section>

          <section className="stats">
            <div className="glass stat">
              <ReceiptIcon />
              <b>{toFa(todayCount)}</b>
              <small>سند امروز</small>
            </div>
            <div className="glass stat">
              <DesktopIcon />
              <b>{toFa(waitingCount)}</b>
              <small>منتظر دسکتاپ یا پندینگ</small>
            </div>
          </section>

          <h3 className="section-title">آخرین اسناد</h3>
          <ul className="list">
            {items.map((item) => (
              <li className="glass item" key={item.id}>
                <span className={`dot ${dotClass(item.status)}`} aria-hidden="true" />
                <div className="item-body">
                  <strong>{item.caption || "بدون شرح"}</strong>
                  <small>
                    {toFa(item.time)} · {STATUS_LABEL[item.status]} · {toFa(item.photos)} عکس
                  </small>
                </div>
                {item.status === "pending" && (
                  <button className="btn-ghost" type="button" onClick={() => setCapture({ editing: item })}>
                    ویرایش
                  </button>
                )}
              </li>
            ))}
          </ul>

          <section className="glass report-card">
            <div>
              <strong>گزارش روزانه</strong>
              <small>{todayReport ? "امروز ثبت شده است" : "برای امروز هنوز نوشته نشده"}</small>
            </div>
            <button className="btn-ghost" type="button" onClick={() => setDailyOpen(true)}>
              نوشتن
            </button>
          </section>
        </>
      )}

      {tab === "reports" && (
        <>
          <h3 className="section-title">گزارش‌های روزانه</h3>
          {reports.length === 0 ? (
            <p className="empty">هنوز گزارشی ثبت نشده است.</p>
          ) : (
            <ul className="list">
              {reports.map((report) => (
                <li className="glass item" key={report.id}>
                  <div className="item-body">
                    <strong>{toFa(report.reportDate)}</strong>
                    <small>
                      {report.phase || "بدون فاز"} · {report.weather || "بدون آب‌وهوا"}
                      {report.temperature ? ` · ${toFa(report.temperature)} درجه` : ""}
                    </small>
                    <small>{report.body}</small>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <button className="btn-primary" type="button" onClick={() => setDailyOpen(true)}>
            گزارش جدید
          </button>
        </>
      )}

      {tab === "settings" && (
        <section className="glass settings-card">
          <strong>حساب کاربری</strong>
          <p>تنظیم و تغییر عبارت عبور روی این گوشی در مرحله‌ی بعد اضافه می‌شود.</p>
        </section>
      )}

      <nav className="tabs" aria-label="بخش‌ها">
        <div className="glass tabs-inner">
          <button type="button" className={tab === "receipts" ? "on" : ""} onClick={() => setTab("receipts")}>
            <ReceiptIcon />
            رسیدها
          </button>
          <button type="button" className={tab === "reports" ? "on" : ""} onClick={() => setTab("reports")}>
            <ReportIcon />
            گزارش
          </button>
          <button type="button" className={tab === "settings" ? "on" : ""} onClick={() => setTab("settings")}>
            <GearIcon />
            تنظیمات
          </button>
        </div>
      </nav>

      {capture && (
        <CaptureFlow
          editing={capture.editing}
          onClose={() => setCapture(null)}
          onSaved={saveItem}
          onDailyReport={() => {
            setCapture(null);
            setDailyOpen(true);
          }}
        />
      )}

      {dailyOpen && (
        <DailyReportSheet
          onClose={() => setDailyOpen(false)}
          onSave={(report) => {
            setReports((current) => [report, ...current]);
            setDailyOpen(false);
            setToast("گزارش روزانه ثبت شد. (نمایشی؛ هنوز به Drive وصل نیست)");
          }}
        />
      )}

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}
