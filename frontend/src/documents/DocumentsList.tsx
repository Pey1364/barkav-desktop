import { useState } from "react";
import { labelOf, type FieldItem } from "../data/sample";
import { toFa } from "../lib/digits";
import { formatAmount } from "../lib/format";
import { timeOf } from "../lib/persianDate";

type Filter = "all" | "pending" | "review" | "decided";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "همه" },
  { value: "pending", label: "پندینگ" },
  { value: "review", label: "در دست بررسی" },
  { value: "decided", label: "تصمیم گرفته شد" },
];

interface Props {
  items: FieldItem[];
  /** Example items are shown with no actions. */
  sample: boolean;
  busy: boolean;
  onComplete: (item: FieldItem) => void;
  onDecide: (item: FieldItem, decision: "approve" | "reject") => void;
}

/** The registered documents, filtered by where they are. Tapping an action changes only that item. */
export function DocumentsList({ items, sample, busy, onComplete, onDecide }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const matches = (item: FieldItem, value: Filter) => value === "all" || item.status === value;
  const shown = items.filter((item) => matches(item, filter));

  return (
    <section className="doc-list">
      <div className="chips" role="radiogroup" aria-label="فیلتر سندها">
        {FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={filter === option.value}
            className={`chip${filter === option.value ? " on" : ""}`}
            onClick={() => setFilter(option.value)}
          >
            {option.label} {toFa(items.filter((item) => matches(item, option.value)).length)}
          </button>
        ))}
      </div>

      {shown.length === 0 && <p className="empty">سندی در این بخش نیست.</p>}

      <ul className="list">
        {shown.map((item) => (
          <li className="glass item doc-item" key={item.id}>
            <div className="item-body">
              <strong>{item.caption || "بدون شرح"}</strong>
              <small>
                {toFa(timeOf(item.receivedAt))} · {labelOf(item)} · {toFa(item.photos)} عکس
              </small>
              {item.review && (
                <small>
                  {item.review.title}
                  {item.review.method ? ` · ${item.review.method}` : ""}
                  {item.review.amount ? ` · ${formatAmount(item.review.amount)} ریال` : ""}
                  {item.review.kind ? ` · ${item.review.kind === "financial" ? "سند مالی" : "سند غیرمالی"}` : ""}
                </small>
              )}
              {!sample && item.status === "review" && (
                <div className="actions">
                  <button className="btn-primary" type="button" disabled={busy} onClick={() => onDecide(item, "approve")}>
                    تأیید
                  </button>
                  <button className="btn-ghost" type="button" disabled={busy} onClick={() => onDecide(item, "reject")}>
                    رد
                  </button>
                </div>
              )}
            </div>
            {!sample && item.status === "pending" && (
              <button className="btn-ghost" type="button" disabled={busy} onClick={() => onComplete(item)}>
                تکمیل
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
