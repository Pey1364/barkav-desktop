import { useCallback, useEffect, useState, type ReactElement } from "react";
import { CONSTRUCTION_PHASES, PAYMENT_METHODS, TRANSACTION_TITLES } from "../data/taxonomy";
import { toFa } from "../lib/digits";
import { formatAmount, plainAmount } from "../lib/format";
import { formatJalali, parseJalali, todayJalali } from "../lib/jalali";
import { ConfirmAction, ConfirmDialog } from "../ui/Confirm";
import { JalaliDatePicker } from "../ui/JalaliDatePicker";
import { api, type DocumentRow, type EditInput, type ReportRow, type ReviewRow } from "./api";

type Tab = "documents" | "review" | "pending" | "reports";

interface Row {
  doc: DocumentRow;
  review: ReviewRow | undefined;
}

interface Dialog {
  title: string;
  lines: string[];
}

const STATUS_TEXT: Record<ReviewRow["status"], string> = {
  new: "پندینگ",
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

/** A document with its photos and what the wizard recorded. Actions are passed as children. */
function DocumentCard({ row, children }: { row: Row; children?: ReactElement | null }) {
  const { doc, review } = row;
  const status = review ? STATUS_TEXT[review.status] : "پندینگ";
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
          {review.phase ? ` · ${review.phase}` : ""}
          {review.event_date ? ` · ${toFa(review.event_date.replace(/-/g, "/"))}` : ""}
          {review.amount ? ` · ${formatAmount(review.amount)} ریال` : ""} ·{" "}
          {review.document_kind === "financial" ? "سند مالی" : "سند غیرمالی"}
        </p>
      )}
      {children}
    </article>
  );
}

/** Edit a document's caption and wizard answers. Used to complete a pending document and to change any document. */
function DocEditor({
  row,
  onSaved,
  onCancel,
  onError,
}: {
  row: Row;
  onSaved: () => void;
  onCancel: () => void;
  onError: (text: string) => void;
}) {
  const known = row.review;
  const [caption, setCaption] = useState(row.doc.caption);
  const [title, setTitle] = useState(known?.title ?? "");
  const [method, setMethod] = useState(known?.transaction_type ?? "");
  const [phase, setPhase] = useState(known?.phase ?? "");
  const [eventDate, setEventDate] = useState(
    known?.event_date ? formatJalali(parseJalali(known.event_date.replace(/-/g, "/")) ?? todayJalali()) : formatJalali(todayJalali()),
  );
  const [amount, setAmount] = useState(known?.amount ?? "");
  const [kind, setKind] = useState<"financial" | "non_financial" | "">(known?.document_kind ?? "");
  const [saving, setSaving] = useState(false);
  const amountLocked = title === "یادداشت";

  async function save() {
    if (!title || !method || !phase || !kind) return;
    const input: EditInput = {
      caption: caption.trim(),
      title,
      transaction_type: method,
      phase,
      document_kind: kind,
      event_date: eventDate.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))).replace(/\//g, "-").trim(),
      amount: amountLocked ? "" : plainAmount(amount),
    };
    setSaving(true);
    try {
      await api.edit(row.doc.id, input);
      onSaved();
    } catch (error) {
      onError(errorText(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="desk-form">
      <label className="field">
        <span>شرح سند</span>
        <textarea className="textarea" value={caption} onChange={(event) => setCaption(event.target.value)} />
      </label>
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
          <span>نوع تراکنش</span>
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
          <span>فاز ساخت</span>
          <select className="select" value={phase} onChange={(event) => setPhase(event.target.value)}>
            <option value="">انتخاب کنید</option>
            {CONSTRUCTION_PHASES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <div className="field">
          <span>تاریخ شمسی</span>
          <JalaliDatePicker id={`date-${row.doc.id}`} value={eventDate} onChange={setEventDate} />
        </div>
        <label className="field">
          <span>مبلغ (ریال)</span>
          <input
            className="input"
            inputMode="numeric"
            value={amountLocked ? "" : formatAmount(amount)}
            disabled={amountLocked}
            onChange={(event) => setAmount(plainAmount(event.target.value))}
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
        <button className="btn-primary" type="button" disabled={!title || !method || !phase || !kind || saving} onClick={save}>
          {saving ? "در حال ذخیره…" : "ذخیره"}
        </button>
        <button className="btn-ghost" type="button" disabled={saving} onClick={onCancel}>
          انصراف
        </button>
      </div>
    </div>
  );
}

export function DesktopApp() {
  const [tab, setTab] = useState<Tab>("documents");
  const [rows, setRows] = useState<Row[]>([]);
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [documents, reviews, dailyReports] = await Promise.all([api.documents(), api.reviews(), api.reports()]);
      const byId = new Map(reviews.map((review) => [review.id, review]));
      setRows(documents.map((doc) => ({ doc, review: byId.get(doc.id) })));
      setReports(dailyReports);
      setError(null);
    } catch {
      setError("سرور محلی روشن نیست. دابل‌کلیک روی start-desktop-server.bat را بزن.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(docId: string, decision: "approve" | "reject") {
    setBusy(true);
    try {
      await api.decide(docId, decision);
      setDialog({
        title: decision === "approve" ? "تأیید ثبت شد" : "رد ثبت شد",
        lines: ["به گوشی با دابل‌کلیک روی pull-from-drive.bat فرستاده می‌شود.", "این تأیید هنوز سندی را وارد ۱۹.۱.۱ نمی‌کند."],
      });
      await load();
    } catch (exception) {
      setNotice(`تصمیم ثبت نشد: ${errorText(exception)}`);
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: Row) {
    setBusy(true);
    try {
      await api.remove(row.doc.id);
      setDeleting(null);
      setDialog({ title: "سند حذف شد", lines: ["به گوشی هم فرستاده می‌شود وقتی pull-from-drive.bat اجرا شود."] });
      await load();
    } catch (exception) {
      setNotice(`حذف انجام نشد: ${errorText(exception)}`);
    } finally {
      setBusy(false);
    }
  }

  const reviewRows = rows.filter((row) => row.review?.status === "under_review");
  const pendingRows = rows.filter((row) => row.review?.status === "new" || (!row.review && row.doc.mode === "quick"));

  function actionsFor(row: Row) {
    return (
      <div className="actions">
        {row.review?.status === "under_review" && (
          <>
            <button className="btn-primary" type="button" disabled={busy} onClick={() => decide(row.doc.id, "approve")}>
              تأیید
            </button>
            <button className="btn-ghost" type="button" disabled={busy} onClick={() => decide(row.doc.id, "reject")}>
              رد
            </button>
          </>
        )}
        <button className="btn-ghost" type="button" disabled={busy} onClick={() => setEditingId(row.doc.id)}>
          {row.review?.status === "new" || !row.review ? "تکمیل" : "ویرایش"}
        </button>
        <button className="btn-ghost danger" type="button" disabled={busy} onClick={() => setDeleting(row)}>
          حذف
        </button>
      </div>
    );
  }

  function listFor(list: Row[], empty: string) {
    if (list.length === 0) return <p className="empty">{empty}</p>;
    return list.map((row) => (
      <DocumentCard key={row.doc.id} row={row}>
        {editingId === row.doc.id ? (
          <DocEditor
            row={row}
            onSaved={() => {
              setEditingId(null);
              setDialog({ title: "تغییرات ذخیره شد", lines: ["سند با اطلاعات تازه به‌روز شد."] });
              void load();
            }}
            onCancel={() => setEditingId(null)}
            onError={(text) => setNotice(`ذخیره نشد: ${text}`)}
          />
        ) : (
          actionsFor(row)
        )}
      </DocumentCard>
    ));
  }

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
        </section>
      )}

      {notice && (
        <div className="toast desk-toast" role="status" onClick={() => setNotice(null)}>
          {notice}
        </div>
      )}

      <nav className="desk-tabs" aria-label="بخش‌ها">
        <button type="button" className={tab === "documents" ? "on" : ""} onClick={() => setTab("documents")}>
          سندها ({toFa(rows.length)})
        </button>
        <button type="button" className={tab === "review" ? "on" : ""} onClick={() => setTab("review")}>
          در دست بررسی ({toFa(reviewRows.length)})
        </button>
        <button type="button" className={tab === "pending" ? "on" : ""} onClick={() => setTab("pending")}>
          پندینگ ({toFa(pendingRows.length)})
        </button>
        <button type="button" className={tab === "reports" ? "on" : ""} onClick={() => setTab("reports")}>
          گزارش‌ها ({toFa(reports.length)})
        </button>
      </nav>

      <p className="muted desk-hint">
        سندهای تازه از گوشی را با دابل‌کلیک روی <code>pull-from-drive.bat</code> بخوان، سپس به‌روزرسانی را بزن.
      </p>

      {tab === "documents" && <section className="desk-list">{listFor(rows, "هنوز سندی خوانده نشده است.")}</section>}
      {tab === "review" && <section className="desk-list">{listFor(reviewRows, "سندی در دست بررسی نیست.")}</section>}
      {tab === "pending" && <section className="desk-list">{listFor(pendingRows, "سند پندینگی نیست.")}</section>}

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

      {deleting && (
        <ConfirmAction
          title="حذف سند؟"
          lines={[deleting.doc.caption || "سند بدون شرح", "سند و عکس‌هایش حذف می‌شوند. این کار برگشت ندارد."]}
          confirmLabel="بله، حذف کن"
          danger
          busy={busy}
          onConfirm={() => remove(deleting)}
          onCancel={() => setDeleting(null)}
        />
      )}

      {dialog && <ConfirmDialog title={dialog.title} lines={dialog.lines} onClose={() => setDialog(null)} />}
    </div>
  );
}
