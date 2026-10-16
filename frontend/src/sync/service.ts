// What the phone sends to Google Drive and reads back. Every item is one sealed file in the inbox
// folder; the desktop reads the same folder when it opens (FD-05, FD-12, ADR-0006 and ADR-0007).
import type { DailyReport } from "../capture/DailyReportSheet";
import { open, seal, toBase64, type Payload } from "../crypto/envelope";
import type { FieldItem, ReviewInfo } from "../data/sample";
import { downloadFile, findOrCreateFolder, listFiles, uploadFile } from "../drive/drive";
import { accessToken } from "../drive/gis";
import { toAsciiDigits, toFa } from "../lib/digits";
import { compressToJpeg } from "../media/compress";
import { plainAmount } from "../lib/format";

export interface ReviewInput {
  title: string;
  /** The payment method is sent as transaction_type, the field the desktop wizard stores. */
  method: string;
  eventDate: string;
  amount: string;
  documentKind: "financial" | "non_financial";
}

export interface DocumentDraft {
  id: string;
  mode: "quick" | "detailed";
  caption: string;
  photos: File[];
  review?: ReviewInput;
}

export interface InboxState {
  items: FieldItem[];
  reports: DailyReport[];
  /** Files that could not be opened (wrong passphrase or damaged). Their contents are never shown. */
  failed: number;
}

function reviewPayload(review: ReviewInput): Payload {
  return {
    title: review.title,
    transaction_type: review.method,
    event_date: toAsciiDigits(review.eventDate).trim(),
    amount: plainAmount(review.amount),
    document_kind: review.documentKind,
  };
}

function reviewFrom(data: unknown): ReviewInfo | undefined {
  if (typeof data !== "object" || data === null) return undefined;
  const raw = data as Payload;
  const kind = raw.document_kind === "financial" || raw.document_kind === "non_financial" ? raw.document_kind : "";
  return {
    title: String(raw.title ?? ""),
    method: String(raw.transaction_type ?? ""),
    eventDate: toFa(String(raw.event_date ?? "")),
    amount: String(raw.amount ?? ""),
    kind,
  };
}

async function sendPayload(passphrase: string, fileName: string, payload: Payload): Promise<void> {
  const token = await accessToken(true);
  const folder = await findOrCreateFolder(token);
  await uploadFile(token, folder, fileName, await seal(payload, passphrase));
}

/** A new document: photos in order, the caption, and the classification when it was detailed. */
export async function sendDocument(
  passphrase: string,
  draft: DocumentDraft,
  onProgress?: (text: string) => void,
): Promise<void> {
  const images: string[] = [];
  for (let index = 0; index < draft.photos.length; index += 1) {
    onProgress?.(`آماده‌سازی عکس ${toFa(index + 1)} از ${toFa(draft.photos.length)}…`);
    images.push(toBase64(await compressToJpeg(draft.photos[index])));
  }
  onProgress?.("رمزنگاری و ارسال به Drive…");
  const payload: Payload = {
    kind: "document",
    id: draft.id,
    mode: draft.mode,
    caption: draft.caption,
    received_at: new Date().toISOString(),
    images_b64: images,
  };
  if (draft.review) payload.review = reviewPayload(draft.review);
  await sendPayload(passphrase, `${draft.id}.json`, payload);
}

/** Wizard answers for a document that was sent as quick. */
export async function sendClassification(passphrase: string, itemId: string, review: ReviewInput): Promise<void> {
  await sendPayload(passphrase, `${crypto.randomUUID()}.json`, {
    kind: "review_classification",
    item_id: itemId,
    review: reviewPayload(review),
  });
}

/** Approve or reject an item from the phone. The desktop applies the first decision it reads. */
export async function sendDecision(passphrase: string, itemId: string, decision: "approve" | "reject"): Promise<void> {
  await sendPayload(passphrase, `${crypto.randomUUID()}.json`, {
    kind: "review_decision",
    item_id: itemId,
    decision,
    decided_at: new Date().toISOString(),
  });
}

/** A daily report, with the Persian date sent as YYYY-MM-DD in the Jalali calendar. */
export async function sendReport(passphrase: string, report: DailyReport): Promise<void> {
  await sendPayload(passphrase, `${report.id}.json`, {
    kind: "daily_report",
    id: report.id,
    report_date: toAsciiDigits(report.reportDate).replace(/\//g, "-"),
    calendar: "jalali",
    body: report.body,
    phase: report.phase,
    weather: report.weather,
    temperature: report.temperature,
  });
}

function itemFrom(payload: Payload, classification: Payload | undefined): FieldItem {
  const quick = payload.mode === "quick";
  const images = Array.isArray(payload.images_b64) ? payload.images_b64.length : 0;
  const review = reviewFrom(classification ?? payload.review);
  return {
    id: String(payload.id),
    caption: String(payload.caption ?? ""),
    receivedAt: String(payload.received_at),
    mode: quick ? "quick" : "detailed",
    status: quick && !classification && !payload.review ? "pending" : "review",
    photos: images,
    review,
  };
}

function reportFrom(payload: Payload): DailyReport {
  return {
    id: String(payload.id),
    reportDate: toFa(String(payload.report_date ?? "").replace(/-/g, "/")),
    phase: String(payload.phase ?? ""),
    weather: String(payload.weather ?? ""),
    temperature: String(payload.temperature ?? ""),
    body: String(payload.body ?? ""),
  };
}

/** Read the inbox folder and open every file with the passphrase. Newest documents come first. */
export async function loadInbox(passphrase: string): Promise<InboxState> {
  const token = await accessToken(false);
  const folder = await findOrCreateFolder(token);
  const ids = await listFiles(token, folder);

  const documents: Payload[] = [];
  const reports: DailyReport[] = [];
  const classifications = new Map<string, Payload>();
  const decisions = new Map<string, "approve" | "reject">();
  // The desktop publishes its own outcome; it is the final word, so it overrides the phone's decision.
  const desktopOutcomes = new Map<string, "approve" | "reject">();
  let failed = 0;

  for (const id of ids) {
    try {
      const payload = await open(await downloadFile(token, id), passphrase);
      if (payload.kind === "document") documents.push(payload);
      else if (payload.kind === "daily_report") reports.push(reportFrom(payload));
      else if (payload.kind === "review_classification") {
        classifications.set(String(payload.item_id), (payload.review ?? {}) as Payload);
      } else if (payload.kind === "review_decision") {
        decisions.set(String(payload.item_id), payload.decision === "reject" ? "reject" : "approve");
      } else if (payload.kind === "review_status") {
        desktopOutcomes.set(String(payload.item_id), payload.status === "rejected" ? "reject" : "approve");
      }
    } catch {
      failed += 1;
    }
  }

  const items = documents.reverse().map((payload) => {
    const item = itemFrom(payload, classifications.get(String(payload.id)));
    const desktop = desktopOutcomes.get(item.id);
    if (desktop) return { ...item, status: "decided" as const, decision: desktop, decidedBy: "desktop" as const };
    const phone = decisions.get(item.id);
    return phone ? { ...item, status: "decided" as const, decision: phone, decidedBy: "phone" as const } : item;
  });
  return { items, reports: reports.reverse(), failed };
}
