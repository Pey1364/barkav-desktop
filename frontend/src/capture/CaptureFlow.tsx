import { useEffect, useRef, useState } from "react";
import type { FieldItem } from "../data/sample";
import { CONSTRUCTION_PHASES, PAYMENT_METHODS, TRANSACTION_TITLES } from "../data/taxonomy";
import { toFa } from "../lib/digits";
import { formatAmount, plainAmount } from "../lib/format";
import { formatJalali, todayJalali } from "../lib/jalali";
import { CloseIcon } from "../icons";
import type { ReviewInput } from "../sync/service";
import { JalaliDatePicker } from "../ui/JalaliDatePicker";

type Step = "photos" | "mode" | "structure" | "title" | "method" | "phase" | "details" | "kind";

export interface CaptureResult {
  mode: "quick" | "detailed";
  caption: string;
  photos: File[];
  review?: ReviewInput;
  /** Set when an existing document is changed: only its caption and classification are sent. */
  editingId?: string;
}

interface Props {
  /** An existing document being changed or completed; null for a new one. */
  editing: FieldItem | null;
  busy: boolean;
  onClose: () => void;
  onSubmit: (result: CaptureResult) => void;
  onDailyReport: () => void;
}

interface Photo {
  file: File;
  url: string;
}

const PREVIOUS: Partial<Record<Step, Step>> = {
  mode: "photos",
  structure: "mode",
  title: "structure",
  method: "title",
  phase: "method",
  details: "phase",
  kind: "details",
};

// The transaction path has five numbered steps.
const STEP_NUMBER: Partial<Record<Step, number>> = { title: 1, method: 2, phase: 3, details: 4, kind: 5 };

export function CaptureFlow({ editing, busy, onClose, onSubmit, onDailyReport }: Props) {
  const known = editing?.review;
  const [step, setStep] = useState<Step>(editing ? "title" : "photos");
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [caption, setCaption] = useState(editing?.caption ?? "");
  const [title, setTitle] = useState(known?.title ?? "");
  const [method, setMethod] = useState(known?.method ?? "");
  const [phase, setPhase] = useState(known?.phase ?? "");
  const [eventDate, setEventDate] = useState(known?.eventDate || formatJalali(todayJalali()));
  const [amount, setAmount] = useState(known?.amount ?? "");
  const [kind, setKind] = useState<"financial" | "non_financial" | "">(known?.kind ?? "");

  // Keep the latest photos so the preview links can be released when the sheet closes.
  const photosRef = useRef(photos);
  photosRef.current = photos;
  useEffect(() => {
    return () => photosRef.current.forEach((photo) => URL.revokeObjectURL(photo.url));
  }, []);

  const photoCount = editing ? editing.photos : photos.length;

  function addFiles(list: FileList | null) {
    if (!list) return;
    const added = Array.from(list).map((file) => ({ file, url: URL.createObjectURL(file) }));
    setPhotos((current) => [...current, ...added]);
  }

  function removePhoto(index: number) {
    setPhotos((current) => {
      const copy = [...current];
      const [gone] = copy.splice(index, 1);
      if (gone) URL.revokeObjectURL(gone.url);
      return copy;
    });
  }

  function submitQuick() {
    onSubmit({ mode: "quick", caption: caption.trim(), photos: photos.map((photo) => photo.file) });
  }

  function submitDetailed() {
    onSubmit({
      mode: "detailed",
      caption: caption.trim(),
      photos: photos.map((photo) => photo.file),
      editingId: editing?.id,
      review: {
        title,
        method,
        phase,
        eventDate,
        amount: title === "یادداشت" ? "" : plainAmount(amount),
        documentKind: kind === "financial" ? "financial" : "non_financial",
      },
    });
  }

  const number = STEP_NUMBER[step];
  const back = PREVIOUS[step];
  const amountLocked = title === "یادداشت";

  return (
    <div className="sheet-backdrop" role="dialog" aria-modal="true" aria-label="ثبت سند">
      <div className="sheet">
        <div className="sheet-head">
          <h3>{editing ? "ویرایش سند" : "سند جدید"}</h3>
          <button className="icon-btn" type="button" aria-label="بستن" onClick={onClose} disabled={busy}>
            <CloseIcon />
          </button>
        </div>

        {number && <p className="step-label">مرحله‌ی {toFa(number)} از ۵</p>}

        {step === "photos" && (
          <>
            <div className="photos">
              {photos.map((photo, index) => (
                <div className="photo" key={photo.url}>
                  <img src={photo.url} alt={`عکس ${toFa(index + 1)}`} />
                  <button type="button" aria-label="حذف عکس" onClick={() => removePhoto(index)}>
                    <CloseIcon />
                  </button>
                </div>
              ))}
              <label className="add-photo">
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  onChange={(event) => {
                    addFiles(event.target.files);
                    event.target.value = "";
                  }}
                />
                دوربین
              </label>
              <label className="add-photo">
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={(event) => {
                    addFiles(event.target.files);
                    event.target.value = "";
                  }}
                />
                از گالری
              </label>
            </div>

            <div className="field">
              <label htmlFor="caption">شرح سند</label>
              <textarea
                id="caption"
                className="textarea"
                value={caption}
                onChange={(event) => setCaption(event.target.value)}
                placeholder="مثلاً: فاکتور آجر نما از فروشگاه ..."
              />
              <small>مثل پیام تلگرام بنویس.</small>
            </div>

            <div className="actions">
              <button className="btn-primary" type="button" disabled={photos.length === 0} onClick={() => setStep("mode")}>
                ادامه
              </button>
            </div>
          </>
        )}

        {step === "mode" && (
          <>
            <p className="step-label">{toFa(photoCount)} عکس آماده است</p>
            <div className="choice-grid">
              <button className="choice" type="button" disabled={busy} onClick={submitQuick}>
                <strong>ثبت سریع</strong>
                <small>فقط عکس‌ها و شرح. سند در پندینگ می‌ماند و بعداً می‌توانی تکمیلش کنی.</small>
              </button>
              <button className="choice" type="button" disabled={busy} onClick={() => setStep("structure")}>
                <strong>ثبت با جزئیات</strong>
                <small>عنوان، نوع تراکنش، فاز ساخت و بقیه‌ی جزئیات را همین‌جا پر می‌کنی.</small>
              </button>
            </div>
          </>
        )}

        {step === "structure" && (
          <>
            <p className="step-label">این ثبت چیست؟</p>
            <div className="choice-grid">
              <button className="choice" type="button" onClick={() => setStep("title")}>
                <strong>تراکنش</strong>
                <small>هزینه، ورودی یا خروجی.</small>
              </button>
              <button className="choice" type="button" onClick={onDailyReport}>
                <strong>گزارش روزانه</strong>
                <small>در پنجره‌ی جدا: فاز، آب‌وهوا و شرح کارگاه.</small>
              </button>
            </div>
          </>
        )}

        {step === "title" && (
          <div className="field">
            <span>عنوان تراکنش</span>
            <div className="chips" role="radiogroup" aria-label="عنوان تراکنش">
              {TRANSACTION_TITLES.map((item) => (
                <button
                  key={item}
                  type="button"
                  role="radio"
                  aria-checked={title === item}
                  className={`chip${title === item ? " on" : ""}`}
                  onClick={() => setTitle(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        )}

        {step === "method" && (
          <div className="field">
            <span>نوع تراکنش</span>
            <div className="chips" role="radiogroup" aria-label="نوع تراکنش">
              {PAYMENT_METHODS.map((item) => (
                <button
                  key={item}
                  type="button"
                  role="radio"
                  aria-checked={method === item}
                  className={`chip${method === item ? " on" : ""}`}
                  onClick={() => setMethod(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        )}

        {step === "phase" && (
          <div className="field">
            <label htmlFor="phase">فاز ساخت</label>
            <select id="phase" className="select" value={phase} onChange={(event) => setPhase(event.target.value)}>
              <option value="">انتخاب کنید</option>
              {CONSTRUCTION_PHASES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
        )}

        {step === "details" && (
          <>
            <div className="field">
              <label htmlFor="event-date">تاریخ شمسی</label>
              <JalaliDatePicker id="event-date" value={eventDate} onChange={setEventDate} />
              <small>تاریخ اجرای تراکنش؛ پیش‌فرض امروز است.</small>
            </div>
            <div className="field">
              <label htmlFor="amount">مبلغ (ریال)</label>
              <input
                id="amount"
                className="input"
                inputMode="numeric"
                value={amountLocked ? "" : formatAmount(amount)}
                disabled={amountLocked}
                onChange={(event) => setAmount(plainAmount(event.target.value))}
              />
              {amountLocked && <small>برای یادداشت مبلغ لازم نیست.</small>}
            </div>
            <div className="field">
              <label htmlFor="caption-detail">شرح سند</label>
              <textarea
                id="caption-detail"
                className="textarea"
                value={caption}
                onChange={(event) => setCaption(event.target.value)}
              />
            </div>
          </>
        )}

        {step === "kind" && (
          <>
            <p className="step-label">نوع سند را مشخص کن. تا انتخاب نکنی، ثبت نمی‌شود.</p>
            <div className="choice-grid">
              <button className={`choice${kind === "financial" ? " on" : ""}`} type="button" aria-pressed={kind === "financial"} onClick={() => setKind("financial")}>
                <strong>سند مالی</strong>
                <small>بعد از تأیید، وارد جدول ثبت دیتا و تراکنش‌ها می‌شود.</small>
              </button>
              <button className={`choice${kind === "non_financial" ? " on" : ""}`} type="button" aria-pressed={kind === "non_financial"} onClick={() => setKind("non_financial")}>
                <strong>سند غیرمالی</strong>
                <small>برای بایگانی است و تراکنش مالی نمی‌سازد.</small>
              </button>
            </div>
          </>
        )}

        <div className="actions">
          {back && (
            <button className="btn-ghost" type="button" disabled={busy} onClick={() => setStep(back)}>
              قبلی
            </button>
          )}
          {step === "title" && (
            <button className="btn-primary" type="button" disabled={!title} onClick={() => setStep("method")}>
              بعدی
            </button>
          )}
          {step === "method" && (
            <button className="btn-primary" type="button" disabled={!method} onClick={() => setStep("phase")}>
              بعدی
            </button>
          )}
          {step === "phase" && (
            <button className="btn-primary" type="button" disabled={!phase} onClick={() => setStep("details")}>
              بعدی
            </button>
          )}
          {step === "details" && (
            <button className="btn-primary" type="button" onClick={() => setStep("kind")}>
              بعدی
            </button>
          )}
          {step === "kind" && (
            <button className="btn-primary" type="button" disabled={!kind || busy} onClick={submitDetailed}>
              {busy ? "در حال ارسال…" : editing ? "ذخیره تغییرات" : "ثبت برای بازبینی"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
