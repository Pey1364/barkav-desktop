import { useEffect, useState } from "react";
import { CaptureFlow, type CaptureResult } from "./capture/CaptureFlow";
import { DailyReportSheet, type DailyReport } from "./capture/DailyReportSheet";
import { DocumentsList } from "./documents/DocumentsList";
import { sampleItems, type FieldItem } from "./data/sample";
import { accessToken, preloadGoogle } from "./drive/gis";
import { CameraIcon, GearIcon, ReceiptIcon, ReportIcon } from "./icons";
import { isNativeApp } from "./native/camera";
import { withTimeout } from "./lib/async";
import { toFa } from "./lib/digits";
import { formatAmount } from "./lib/format";
import { persianLongDate } from "./lib/persianDate";
import { clearPassphrase, loadPassphrase, savePassphrase } from "./settings/passphrase";
import { ConfirmAction, ConfirmDialog } from "./ui/Confirm";
import { loadInbox, sendClassification, sendDecision, sendDelete, sendDocument, sendEdit, sendReport } from "./sync/service";

type Tab = "documents" | "reports" | "settings";

const SIGN_IN_WAIT_MS = 120_000;
const UPLOAD_WAIT_MS = 300_000;
const SIGN_IN_FAILED = "ورود به Google انجام نشد. پنجره‌ی ورود را باز کن و دوباره امتحان کن.";
const UPLOAD_TOO_SLOW = "ارسال زمان‌بر شد. اتصال اینترنت را بررسی کن.";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "خطای ناشناخته";
}

interface Dialog {
  title: string;
  lines: string[];
}

export function App() {
  const [tab, setTab] = useState<Tab>("documents");
  const [passphrase, setPassphrase] = useState<string | null>(() => loadPassphrase());
  const [passphraseDraft, setPassphraseDraft] = useState("");
  const [connected, setConnected] = useState(false);
  const [sample, setSample] = useState(true);
  const [items, setItems] = useState<FieldItem[]>(() => sampleItems());
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [capture, setCapture] = useState<{ editing: FieldItem | null } | null>(null);
  const [dailyOpen, setDailyOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<FieldItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  // Load Google's script now, so a tap can open the sign-in window at once. Then try a silent sign-in.
  useEffect(() => {
    preloadGoogle();
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
      if (state.failed > 0) setToast(`${toFa(state.failed)} فایل باز نشد. عبارت عبور را بررسی کن.`);
    } catch (error) {
      setToast(`فهرست خوانده نشد: ${messageOf(error)}`);
    }
  }

  async function signIn() {
    try {
      await withTimeout(accessToken(true), SIGN_IN_WAIT_MS, SIGN_IN_FAILED);
      setConnected(true);
      setToast("به Google وصل شدی.");
      if (passphrase) await refresh(passphrase);
    } catch (error) {
      setToast(messageOf(error));
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
      setDialog({ title: "عبارت عبور ذخیره شد", lines: ["روی همین گوشی ذخیره شد و به Google فرستاده نمی‌شود."] });
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
      // Sign in first, while the tap is still fresh; a window opened after a long wait is blocked.
      setProgress("ورود به Google…");
      await withTimeout(accessToken(true), SIGN_IN_WAIT_MS, SIGN_IN_FAILED);

      if (result.editingId) {
        const editedId = result.editingId;
        const review = result.review;
        const caption = result.caption;
        const isQuickCompletion = items.find((item) => item.id === editedId)?.status === "pending";
        setProgress("رمزنگاری و ارسال…");
        if (isQuickCompletion && review) {
          await withTimeout(sendClassification(pass, editedId, review), UPLOAD_WAIT_MS, UPLOAD_TOO_SLOW);
        } else {
          await withTimeout(sendEdit(pass, editedId, caption, review), UPLOAD_WAIT_MS, UPLOAD_TOO_SLOW);
        }
        setItems((current) =>
          current.map((item) => {
            if (item.id !== editedId) return item;
            const nextStatus = item.status === "decided" ? item.status : "review";
            return {
              ...item,
              caption,
              status: nextStatus,
              review: review
                ? {
                    title: review.title,
                    method: review.method,
                    phase: review.phase,
                    eventDate: review.eventDate,
                    amount: review.amount,
                    kind: review.documentKind,
                  }
                : item.review,
            };
          }),
        );
        setCapture(null);
        setDialog({
          title: "تغییرات ذخیره شد",
          lines: [review ? `${review.title} · ${review.method} · ${review.phase}` : "شرح سند به‌روز شد."],
        });
      } else {
        const id = crypto.randomUUID();
        await withTimeout(
          sendDocument(pass, { id, mode: result.mode, caption: result.caption, photos: result.photos, review: result.review }, setProgress),
          UPLOAD_WAIT_MS,
          UPLOAD_TOO_SLOW,
        );
        const item: FieldItem = {
          id,
          caption: result.caption,
          receivedAt: new Date().toISOString(),
          mode: result.mode,
          status: result.mode === "quick" ? "pending" : "review",
          photos: result.photos.length,
          review: result.review
            ? {
                title: result.review.title,
                method: result.review.method,
                phase: result.review.phase,
                eventDate: result.review.eventDate,
                amount: result.review.amount,
                kind: result.review.documentKind,
              }
            : undefined,
        };
        setItems((current) => (sample ? [item] : [item, ...current]));
        setSample(false);
        setCapture(null);
        setDialog(
          result.mode === "quick"
            ? {
                title: "ثبت سریع انجام شد",
                lines: [`${toFa(result.photos.length)} عکس با شرح ذخیره شد.`, "سند در پندینگ است؛ بعداً می‌توانی تکمیلش کنی."],
              }
            : {
                title: "سند ثبت شد",
                lines: [
                  `${result.review?.title ?? ""} · ${result.review?.method ?? ""} · ${result.review?.phase ?? ""}`,
                  result.review?.amount ? `مبلغ: ${formatAmount(result.review.amount)} ریال` : "",
                  "سند برای بازبینی ارسال شد.",
                ].filter(Boolean),
              },
        );
      }
    } catch (error) {
      setToast(`ارسال انجام نشد: ${messageOf(error)}`);
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }

  async function removeDocument(item: FieldItem) {
    const pass = requirePassphrase();
    if (!pass) return;
    setBusy(true);
    setProgress("حذف سند…");
    try {
      await withTimeout(accessToken(true), SIGN_IN_WAIT_MS, SIGN_IN_FAILED);
      await withTimeout(sendDelete(pass, item.id), UPLOAD_WAIT_MS, UPLOAD_TOO_SLOW);
      setItems((current) => current.filter((existing) => existing.id !== item.id));
      setDeleteTarget(null);
      setDialog({ title: "سند حذف شد", lines: [item.caption || "سند بدون شرح", "از دسکتاپ هم پاک می‌شود وقتی آن را بخواند."] });
    } catch (error) {
      setToast(`حذف انجام نشد: ${messageOf(error)}`);
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }

  async function decide(item: FieldItem, decision: "approve" | "reject") {
    const pass = requirePassphrase();
    if (!pass) return;
    setBusy(true);
    setProgress("ارسال تصمیم…");
    try {
      await withTimeout(accessToken(true), SIGN_IN_WAIT_MS, SIGN_IN_FAILED);
      await withTimeout(sendDecision(pass, item.id, decision), UPLOAD_WAIT_MS, UPLOAD_TOO_SLOW);
      setItems((current) =>
        current.map((existing) =>
          existing.id === item.id ? { ...existing, status: "decided", decision, decidedBy: "phone" } : existing,
        ),
      );
      setDialog({
        title: decision === "approve" ? "تأیید ثبت شد" : "رد ثبت شد",
        lines: [`${item.caption || "سند"} ${decision === "approve" ? "تأیید" : "رد"} شد.`, "دسکتاپ بعد از خواندن، همین وضعیت را نشان می‌دهد."],
      });
    } catch (error) {
      setToast(`تصمیم ارسال نشد: ${messageOf(error)}`);
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }

  async function submitDaily(report: DailyReport) {
    const pass = requirePassphrase();
    if (!pass) {
      setDailyOpen(false);
      return;
    }
    setBusy(true);
    setProgress("ارسال گزارش…");
    try {
      await withTimeout(accessToken(true), SIGN_IN_WAIT_MS, SIGN_IN_FAILED);
      await withTimeout(sendReport(pass, report), UPLOAD_WAIT_MS, UPLOAD_TOO_SLOW);
      setReports((current) => [report, ...current]);
      setDailyOpen(false);
      setDialog({ title: "گزارش روزانه ثبت شد", lines: [`${report.reportDate} · ${report.phase || "بدون فاز"}`] });
    } catch (error) {
      setToast(`ارسال گزارش انجام نشد: ${messageOf(error)}`);
    } finally {
      setBusy(false);
      setProgress(null);
    }
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

      {tab === "documents" && (
        <>
          <section className="glass hero">
            <p className="kicker">{persianLongDate()}</p>
            <button className="btn-primary" type="button" disabled={busy} onClick={() => setCapture({ editing: null })}>
              <CameraIcon /> ثبت سند جدید
            </button>
          </section>

          {sample && (
            <p className="empty">نمایشی. برای دیدن سندهای واقعی، از تنظیمات وارد Google شو و عبارت عبور را ذخیره کن.</p>
          )}

          <DocumentsList
            items={items}
            sample={sample}
            busy={busy}
            onEdit={(item) => setCapture({ editing: item })}
            onDelete={(item) => setDeleteTarget(item)}
            onDecide={decide}
          />
        </>
      )}

      {tab === "reports" && (
        <>
          <section className="glass hero">
            <p className="kicker">{persianLongDate()}</p>
            <button className="btn-primary" type="button" disabled={busy} onClick={() => setDailyOpen(true)}>
              ثبت گزارش روزانه
            </button>
          </section>
          <h3 className="section-title">گزارش‌های ثبت‌شده</h3>
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
        </>
      )}

      {tab === "settings" && (
        <>
          <section className="glass settings-card">
            <strong>حساب Google</strong>
            {isNativeApp() ? (
              <p>در برنامه‌ی اندروید ورود با Google فعلاً کار نمی‌کند؛ Google این ورود را داخل برنامه مسدود می‌کند. از نسخه‌ی گوشی در مرورگر استفاده کن یا منتظر راه‌اندازی سرور شخصی بمان.</p>
            ) : (
              <p>{connected ? "به Google Drive وصل است." : "هنوز وصل نیست. برای ارسال و خواندن سندها لازم است."}</p>
            )}
            <div className="actions">
              {!connected && !isNativeApp() && (
                <button className="btn-primary" type="button" onClick={signIn}>
                  ورود با Google
                </button>
              )}
              {connected && passphrase && (
                <button className="btn-ghost" type="button" onClick={() => passphrase && refresh(passphrase)}>
                  به‌روزرسانی فهرست
                </button>
              )}
            </div>
          </section>

          <section className="glass settings-card">
            <strong>عبارت عبور</strong>
            <p>
              {passphrase
                ? "روی همین گوشی ذخیره شده است. به Google فرستاده نمی‌شود."
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
          <button type="button" className={tab === "documents" ? "on" : ""} onClick={() => setTab("documents")}>
            <ReceiptIcon />
            سندها
          </button>
          <button type="button" className={tab === "reports" ? "on" : ""} onClick={() => setTab("reports")}>
            <ReportIcon />
            گزارش روزانه
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

      {dailyOpen && <DailyReportSheet busy={busy} onClose={() => setDailyOpen(false)} onSave={submitDaily} />}

      {deleteTarget && (
        <ConfirmAction
          title="حذف سند؟"
          lines={[deleteTarget.caption || "سند بدون شرح", "سند و عکس‌هایش از همه‌ی جاها حذف می‌شوند. این کار برگشت ندارد."]}
          confirmLabel="بله، حذف کن"
          danger
          busy={busy}
          onConfirm={() => removeDocument(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {busy && progress && (
        <div className="toast progress" role="status">
          {progress}
        </div>
      )}

      {toast && !busy && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}

      {dialog && <ConfirmDialog title={dialog.title} lines={dialog.lines} onClose={() => setDialog(null)} />}
    </div>
  );
}
