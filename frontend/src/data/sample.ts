// Example items for the first screen. They are not real records; they are removed once the
// real list comes from Google Drive.
export type ItemStatus = "pending" | "review" | "sent" | "waiting" | "read";

export interface FieldItem {
  id: string;
  caption: string;
  time: string;
  day: "today" | "yesterday";
  mode: "quick" | "detailed";
  status: ItemStatus;
  photos: number;
}

export const STATUS_LABEL: Record<ItemStatus, string> = {
  pending: "ثبت سریع · در پندینگ",
  review: "در دست بررسی",
  sent: "رمزشده ارسال شد",
  waiting: "منتظر دسکتاپ",
  read: "خوانده شد",
};

export const SAMPLE_ITEMS: FieldItem[] = [
  { id: "s1", caption: "بابت آجر نما", time: "۱۰:۱۲", day: "today", mode: "detailed", status: "sent", photos: 2 },
  { id: "s2", caption: "خرید میلگرد", time: "۰۹:۴۰", day: "today", mode: "quick", status: "waiting", photos: 1 },
  { id: "s3", caption: "کرایه‌ی ماشین", time: "۱۷:۰۵", day: "yesterday", mode: "detailed", status: "read", photos: 1 },
];
