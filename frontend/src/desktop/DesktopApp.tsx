import { useCallback, useEffect, useState, type ReactElement } from "react";
import { PAYMENT_METHODS, TRANSACTION_TITLES } from "../data/taxonomy";
import { toAsciiDigits, toFa } from "../lib/digits";
import { persianDateInput } from "../lib/persianDate";
import { api, type ClassifyInput, type DocumentRow, type ReportRow, type ReviewRow } from "./api";

type Tab = "review" | "new" | "documents" | "reports";

interface Row {
  doc: DocumentRow;
  review: ReviewRow | undefined;
}

const STATUS_TEXT: Record<ReviewRow["status"], string> = {
  new: "جدید · پندینگ",
  under_review: "در دست بررسی",
  approved: "تأییدشده",
  rejected: "ردشده",
};

const DATE_TIME = new Intl.DateTimeFormat("fa-IR", { dateStyle: "short", timeStyle: "short" });

function receivedText(iso: string): string {
  return toFa(DATE_TIME.format(new Date(iso)));
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "خطای ناشناخته";
}

function DocumentCard({ row, children }: { row: Row; children?: ReactElement | null }) {
  const { doc, review } = row;
  const status = review ? STATUS_TEXT[review.status] : "نامشخص";
  const photos = Array.from({ length: doc.image_count }, (_, index) => index + 1);
  return (
    <article className="glass desk-card">
      <div className="desk-card-head">
        <strong>{doc.caption || "بدون شرح"}</strong>
        <span className="chip-static">{status}</span>
      </div>
      <small className="muted">
        {receivedText(doc.received_at)} · {doc.mode === "quick" ? "ثبت سریع" : "ثبت با جزئیات"} · {toFa(doc.image_count)} عکس
      </small>
      {photos.length > 0 && (
        <div className="desk-photos">
          {photos.map((position) => (
            <img key={position} src={api.photoUrl(doc.id, position)} alt={`عکس ${toFa(position)}`} loading="lazy" />
          ))}
        </div>
      )}
      {review && review.status !== "new" && (
        <p className="desk-summary">
          {review.title} · {review.transaction_type}
          {review.event_date ? ` · ${toFa(review.event_date.replace(/-/g, "/"))}` : ""}
          {review.amount ? ` · ${toFa(review.amount)} ریال` : ""} ·{" "}
          {review.document_kind === "financial" ? "سند مالی" : "سند غیرمالی"}
        </p>
      )}
      {children}
    </article>
  );
}

function ClassifyForm({ docId, onDone, onError }: { docId: string; onDone: () => void; onError: (text: string) => void }) {
  const [title, setTitle] = useState("");
  const [method, setMethod] = useState("");
  const [eventDate, setEventDate] = useState(persianDateInput());
  const [amount, setAmount] = useState("");
  const [kind, setKind] = useState<"financial" | "non_financial" | "">("");
  const [saving, setSaving] = useState(false);
  const amountLocked = title === "یادداشت";

  async function save() {
    if (!title || !method || !kind) return;
    const input: ClassifyInput = {
      title,
      transaction_type: method,
      document_kind: kind,
      event_date: toAsciiDigits(eventDate).trim(),
      amount: amountLocked ? "" : toAsciiDigits(amount).replace(/[,\s]/g, ""),
    };
    setSaving(true);
    try {
      await api.classify(docId, input);
      onDone();
    } catch (error) {
      onError(errorText(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="desk-form">
      <div className="desk-grid">
        <label className="field">
          <span>عنوان تراکنش</span>
          <select className="select" value={title} onChange={(event) => setTitle(event.target.value)}>
            <option value="">انتخاب کنید</option>
            {TRANSACTION_TITLES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>روش پرداخت</span>
          <select className="select" value={method} onChange={(event) => setMethod(event.target.value)}>
            <option value="">انتخاب کنید</option>
            {PAYMENT_METHODS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>تاریخ شمسی</span>
          <input className="input" inputMode="numeric" value={eventDate} onChange={(event) => setEventDate(event.target.value)} />
        </label>
        <label className="field">
          <span>مبلغ (ریال)</span>
          <input
            className="input"
            inputMode="numeric"
            value={amountLocked ? "" : amount}
            disabled={amountLocked}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
      </div>
      <div className="chips">
        <button type="button" className={`chip${kind === "financial" ? " on" : ""}`} aria-pressed={kind === "financial"} onClick={() => setKind("financial")}>
          سند مالی
        </button>
        <button
          type="button"
          className={`chip${kind === "non_financial" ? " on" : ""}`}
          aria-pressed={kind === "non_financial"}
          onClick={() => setKind("non_financial")}
        >
          سند غیرمالی
        </button>
      </div>
      <div className="actions">
        <button className="btn-primary" type="button" disabled={!title || !method || !kind || saving} onClick={save}>
          {saving ? "در حال ثبت…" : "ثبت برای بازبینی"}
        </button>
      </div>
    </div>
  );
}

export function DesktopApp() {
  const [tab, setTab] = useState<Tab>("review");
  const [rows, setRows] = useState<Row[]>([]);
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [documents, reviews, dailyReports] = await Promise.all([api.documents(), api.reviews(), api.reports()]);
      const byId = new Map(reviews.map((review) => [review.id, review]));
      setRows(documents.map((doc) => ({ doc, review: byId.get(doc.id) })));
      setReports(dailyReports);
      setError(null);
    } catch {
      setError("سرور محلی روشن نیست. در پوشه‌ی backend این دستور را اجرا کن:");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(docId: string, decision: "approve" | "reject") {
    setBusy(true);
    try {
      await api.decide(docId, decision);
      setNotice(
        decision === "approve"
          ? "تأیید شد. با اجرای pull به گوشی فرستاده می‌شود. وارد ۱۹.۱.۱ نمی‌شود (FD-08 بعد از انتقال ۱۹.۱.۱)."
          : "رد شد. با اجرای pull به گوشی فرستاده می‌شود.",
      );
      await load();
    } catch (exception) {
      setNotice(`تصمیم ثبت نشد: ${errorText(exception)}`);
    } finally {
      setBusy(false);
    }
  }

  const reviewRows = rows.filter((row) => row.review?.status === "under_review");
  const newRows = rows.filter((row) => row.review?.status === "new" || (!row.review && row.doc.mode === "quick"));

  return (
    <div className="desk">
      <header className="desk-head">
        <div className="brand">
          BARKAV<span>Field</span> <small className="muted">· دسکتاپ</small>
        </div>
        <button className="btn-ghost" type="button" onClick={() => void load()}>
          به‌روزرسانی
        </button>
      </header>

      {error && (
        <section className="glass desk-note">
          <p>{error}</p>
          <pre>py -3 -m uvicorn barkav_field.server:app --host 127.0.0.1 --port 8765</pre>
        </section>
      )}

      {notice && (
        <div className="toast desk-toast" role="status" onClick={() => setNotice(null)}>
          {notice}
        </div>
      )}

      <nav className="desk-tabs" aria-label="بخش‌ها">
        <button type="button" className={tab === "review" ? "on" : ""} onClick={() => setTab("review")}>
          در دست بررسی ({toFa(reviewRows.length)})
        </button>
        <button type="button" className={tab === "new" ? "on" : ""} onClick={() => setTab("new")}>
          پندینگ ({toFa(newRows.length)})
        </button>
        <button type="button" className={tab === "documents" ? "on" : ""} onClick={() => setTab("documents")}>
          همه‌ی اسناد ({toFa(rows.length)})
        </button>
        <button type="button" className={tab === "reports" ? "on" : ""} onClick={() => setTab("reports")}>
          گزارش‌ها ({toFa(reports.length)})
        </button>
      </nav>

      <p className="muted desk-hint">
        سندهای تازه از گوشی را با دستور <code>py -3 -m barkav_field.pull</code> بخوان، سپس به‌روزرسانی را بزن.
      </p>

      {tab === "review" && (
        <section className="desk-list">
          {reviewRows.length === 0 && <p className="empty">سندی در دست بررسی نیست.</p>}
          {reviewRows.map((row) => (
            <DocumentCard key={row.doc.id} row={row}>
              <div className="actions">
                <button className="btn-primary" type="button" disabled={busy} onClick={() => decide(row.doc.id, "approve")}>
                  تأیید
                </button>
                <button className="btn-ghost" type="button" disabled={busy} onClick={() => decide(row.doc.id, "reject")}>
                  رد
                </button>
              </div>
            </DocumentCard>
          ))}
        </section>
      )}

      {tab === "new" && (
        <section className="desk-list">
          {newRows.length === 0 && <p className="empty">سند پندینگی نیست.</p>}
          {newRows.map((row) => (
            <DocumentCard key={row.doc.id} row={row}>
              <ClassifyForm
                docId={row.doc.id}
                onDone={() => {
                  setNotice("دسته‌بندی ثبت شد و سند در دست بررسی است.");
                  void load();
                }}
                onError={(text) => setNotice(`ثبت نشد: ${text}`)}
              />
            </DocumentCard>
          ))}
        </section>
      )}

      {tab === "documents" && (
        <section className="desk-list">
          {rows.length === 0 && <p className="empty">هنوز سندی خوانده نشده است.</p>}
          {rows.map((row) => (
            <DocumentCard key={row.doc.id} row={row} />
          ))}
        </section>
      )}

      {tab === "reports" && (
        <section className="desk-list">
          {reports.length === 0 && <p className="empty">هنوز گزارشی خوانده نشده است.</p>}
          {reports.map((report) => (
            <article className="glass desk-card" key={report.id}>
              <div className="desk-card-head">
                <strong>{toFa(report.report_date.replace(/-/g, "/"))}</strong>
                <span className="chip-static">{report.details.phase || "بدون فاز"}</span>
              </div>
              <small className="muted">
                {report.details.weather || "بدون آب‌وهوا"}
                {report.details.temperature ? ` · ${toFa(report.details.temperature)} درجه` : ""}
              </small>
              <p className="desk-summary">{report.body}</p>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
