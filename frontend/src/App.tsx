import { useEffect, useState } from "react";
import { CaptureFlow, type CaptureResult } from "./capture/CaptureFlow";
import { DailyReportSheet, type DailyReport } from "./capture/DailyReportSheet";
import { STATUS_LABEL, sampleItems, type FieldItem, type ItemStatus } from "./data/sample";
import { accessToken } from "./drive/gis";
import { CameraIcon, DesktopIcon, GearIcon, ReceiptIcon, ReportIcon } from "./icons";
import { toFa } from "./lib/digits";
import { isToday, persianDateInput, persianLongDate, timeOf } from "./lib/persianDate";
import { clearPassphrase, loadPassphrase, savePassphrase } from "./settings/passphrase";
import {
  loadInbox,
  sendClassification,
  sendDecision,
  sendDocument,
  sendReport,
} from "./sync/service";

type Tab = "receipts" | "reports" | "settings";

function dotClass(status: ItemStatus): string {
  if (status === "pending" || status === "waiting") return "wait";
  if (status === "review") return "review";
  return "";
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "خطای ناشناخته";
}

export function App() {
  const [tab, setTab] = useState<Tab>("receipts");
  const [passphrase, setPassphrase] = useState<string | null>(() => loadPassphrase());
  const [passphraseDraft, setPassphraseDraft] = useState("");
  const [connected, setConnected] = useState(false);
  const [sample, setSample] = useState(true);
  const [items, setItems] = useState<FieldItem[]>(() => sampleItems());
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [capture, setCapture] = useState<{ editing: FieldItem | null } | null>(null);
  const [dailyOpen, setDailyOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  // On start, try a silent sign-in: it only works when this app is already allowed.
  useEffect(() => {
    if (!passphrase) return;
    accessToken(false)
      .then(() => {
        setConnected(true);
        return refresh(passphrase);
      })
      .catch(() => undefined);
  }, []);

  async function refresh(pass: string) {
    try {
      const state = await loadInbox(pass);
      setItems(state.items);
      setReports(state.reports);
      setSample(false);
      if (state.failed > 0) {
        setToast(`${toFa(state.failed)} فایل باز نشد. عبارت عبور را بررسی کن.`);
      }
    } catch (error) {
      setToast(`فهرست خوانده نشد: ${messageOf(error)}`);
    }
  }

  async function signIn() {
    try {
      await accessToken(true);
      setConnected(true);
      setToast("به Google وصل شدی.");
      if (passphrase) await refresh(passphrase);
    } catch (error) {
      setToast(`ورود انجام نشد: ${messageOf(error)}`);
    }
  }

  function requirePassphrase(): string | null {
    if (passphrase) return passphrase;
    setToast("اول عبارت عبور را در تنظیمات ذخیره کن.");
    setTab("settings");
    return null;
  }

  function saveTypedPassphrase() {
    const value = passphraseDraft.trim();
    if (!value) return;
    try {
      savePassphrase(value);
      setPassphrase(value);
      setPassphraseDraft("");
      setToast("عبارت عبور روی همین گوشی ذخیره شد.");
      if (connected) void refresh(value);
    } catch (error) {
      setToast(messageOf(error));
    }
  }

  function forgetPassphrase() {
    clearPassphrase();
    setPassphrase(null);
    setToast("عبارت عبور از این گوشی پاک شد. سندهای Drive پاک نشده‌اند.");
  }

  async function submitCapture(result: CaptureResult) {
    const pass = requirePassphrase();
    if (!pass) {
      setCapture(null);
      return;
    }
    setBusy(true);
    try {
      if (result.editingId && result.review) {
        await sendClassification(pass, result.editingId, result.review);
        const editedId = result.editingId;
        setItems((current) =>
          current.map((item) => (item.id === editedId ? { ...item, mode: "detailed", status: "review" } : item)),
        );
        setToast("سند تکمیل شد و برای بازبینی ارسال شد.");
      } else {
        const id = crypto.randomUUID();
        await sendDocument(pass, { id, mode: result.mode, caption: result.caption, photos: result.photos, review: result.review });
        const item: FieldItem = {
          id,
          caption: result.caption,
          receivedAt: new Date().toISOString(),
          mode: result.mode,
          status: result.mode === "quick" ? "pending" : "review",
          photos: result.photos.length,
        };
        // The first real document replaces the example items.
        setItems((current) => (sample ? [item] : [item, ...current]));
        setSample(false);
        setToast(
          result.mode === "quick"
            ? "ثبت سریع رمزشده و ارسال شد؛ در پندینگ است."
            : "سند رمزشده و برای بازبینی ارسال شد.",
        );
      }
      setCapture(null);
    } catch (error) {
      setToast(`ارسال انجام نشد: ${messageOf(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function submitDaily(report: DailyReport) {
    const pass = requirePassphrase();
    if (!pass) {
      setDailyOpen(false);
      return;
    }
    setBusy(true);
    try {
      await sendReport(pass, report);
      setReports((current) => [report, ...current]);
      setDailyOpen(false);
      setToast("گزارش روزانه رمزشده و ارسال شد.");
    } catch (error) {
      setToast(`ارسال گزارش انجام نشد: ${messageOf(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function decide(item: FieldItem, decision: "approve" | "reject") {
    const pass = requirePassphrase();
    if (!pass) return;
    setBusy(true);
    try {
      await sendDecision(pass, item.id, decision);
      setItems((current) =>
        current.map((existing) => (existing.id === item.id ? { ...existing, status: "decided", decision } : existing)),
      );
      setToast(decision === "approve" ? "تأیید از گوشی ارسال شد." : "رد از گوشی ارسال شد.");
    } catch (error) {
      setToast(`تصمیم ارسال نشد: ${messageOf(error)}`);
    } finally {
      setBusy(false);
    }
  }

  const todayCount = items.filter((item) => isToday(item.receivedAt)).length;
  const waitingCount = items.filter((item) => item.status === "waiting" || item.status === "pending").length;
  const todayReport = reports.some((report) => report.reportDate === persianDateInput());

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

          {sample && (
            <p className="empty">
              نمایشی. برای دیدن سندهای واقعی، از تنظیمات وارد Google شو و عبارت عبور را ذخیره کن.
            </p>
          )}

          <h3 className="section-title">آخرین اسناد</h3>
          {items.length === 0 ? (
            <p className="empty">هنوز سندی ثبت نشده است.</p>
          ) : (
            <ul className="list">
              {items.map((item) => (
                <li className="glass item" key={item.id}>
                  <span className={`dot ${dotClass(item.status)}`} aria-hidden="true" />
                  <div className="item-body">
                    <strong>{item.caption || "بدون شرح"}</strong>
                    <small>
                      {toFa(timeOf(item.receivedAt))} · {STATUS_LABEL[item.status]} · {toFa(item.photos)} عکس
                    </small>
                    {item.status === "review" && !sample && (
                      <div className="actions">
                        <button className="btn-ghost" type="button" disabled={busy} onClick={() => decide(item, "approve")}>
                          تأیید
                        </button>
                        <button className="btn-ghost" type="button" disabled={busy} onClick={() => decide(item, "reject")}>
                          رد
                        </button>
                      </div>
                    )}
                  </div>
                  {item.status === "pending" && !sample && (
                    <button className="btn-ghost" type="button" disabled={busy} onClick={() => setCapture({ editing: item })}>
                      تکمیل
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

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
                    <strong>{report.reportDate}</strong>
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
        <>
          <section className="glass settings-card">
            <strong>حساب Google</strong>
            <p>{connected ? "به Google Drive وصل است." : "هنوز وصل نیست. برای ارسال و خواندن سندها لازم است."}</p>
            <div className="actions">
              {!connected && (
                <button className="btn-primary" type="button" onClick={signIn}>
                  ورود با Google
                </button>
              )}
              {connected && passphrase && (
                <button className="btn-ghost" type="button" onClick={() => refresh(passphrase)}>
                  به‌روزرسانی فهرست
                </button>
              )}
            </div>
          </section>

          <section className="glass settings-card">
            <strong>عبارت عبور</strong>
            <p>
              {passphrase
                ? "روی همین گوشی ذخیره شده است. هیچ‌جا جز این مرورگر نیست و به Google فرستاده نمی‌شود."
                : "این عبارت را یک بار وارد کن. فقط روی همین گوشی می‌ماند. اگر آن را گم کنی، سندهای رمزشده قابل خواندن نیستند."}
            </p>
            {!passphrase && (
              <div className="field">
                <label htmlFor="passphrase">عبارت عبور</label>
                <input
                  id="passphrase"
                  className="input"
                  type="password"
                  autoComplete="off"
                  value={passphraseDraft}
                  onChange={(event) => setPassphraseDraft(event.target.value)}
                />
                <div className="actions">
                  <button className="btn-primary" type="button" disabled={!passphraseDraft.trim()} onClick={saveTypedPassphrase}>
                    ذخیره روی این گوشی
                  </button>
                </div>
              </div>
            )}
            {passphrase && (
              <div className="actions">
                <button className="btn-ghost" type="button" onClick={forgetPassphrase}>
                  حذف از این گوشی
                </button>
              </div>
            )}
          </section>
        </>
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
          busy={busy}
          onClose={() => setCapture(null)}
          onSubmit={submitCapture}
          onDailyReport={() => {
            setCapture(null);
            setDailyOpen(true);
          }}
        />
      )}

      {dailyOpen && <DailyReportSheet onClose={() => setDailyOpen(false)} onSave={submitDaily} />}

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}
