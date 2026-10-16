// Example items, shown only until the phone is connected and the real list is read from Drive.
// They are not records.
export type ItemStatus = "pending" | "review" | "decided" | "sent" | "waiting" | "read";

export interface FieldItem {
  id: string;
  caption: string;
  /** ISO time the phone registered the document. */
  receivedAt: string;
  mode: "quick" | "detailed";
  status: ItemStatus;
  photos: number;
  /** Set when a decision exists: from this phone, or published by the desktop (it wins). */
  decision?: "approve" | "reject";
  decidedBy?: "phone" | "desktop";
}

export const STATUS_LABEL: Record<ItemStatus, string> = {
  pending: "ثبت سریع · در پندینگ",
  review: "در دست بررسی",
  decided: "تصمیم از گوشی ارسال شد",
  sent: "رمزشده ارسال شد",
  waiting: "منتظر دسکتاپ",
  read: "خوانده شد",
};

function ago(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

/** The label for an item, including who made its decision. */
export function labelOf(item: FieldItem): string {
  if (item.status !== "decided") return STATUS_LABEL[item.status];
  const who = item.decidedBy === "desktop" ? "از دسکتاپ" : "از گوشی ارسال شد";
  return `${item.decision === "reject" ? "رد شد" : "تأیید شد"} ${who}`;
}

export function sampleItems(): FieldItem[] {
  return [
    { id: "s1", caption: "بابت آجر نما", receivedAt: ago(35), mode: "detailed", status: "sent", photos: 2 },
    { id: "s2", caption: "خرید میلگرد", receivedAt: ago(70), mode: "quick", status: "waiting", photos: 1 },
    { id: "s3", caption: "کرایه‌ی ماشین", receivedAt: ago(60 * 26), mode: "detailed", status: "read", photos: 1 },
  ];
}
