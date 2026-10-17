interface Props {
  title: string;
  lines: string[];
  onClose: () => void;
}

/** A plain confirmation window: shown after something was saved, so the user knows it worked. */
export function ConfirmDialog({ title, lines, onClose }: Props) {
  return (
    <div className="sheet-backdrop centered" role="dialog" aria-modal="true" aria-label={title}>
      <div className="dialog glass">
        <h3>{title}</h3>
        {lines.map((line) => (
          <p key={line}>{line}</p>
        ))}
        <button className="btn-primary" type="button" onClick={onClose}>
          باشه
        </button>
      </div>
    </div>
  );
}

interface ActionProps {
  title: string;
  lines: string[];
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** A question with two answers, used before anything is deleted. */
export function ConfirmAction({ title, lines, confirmLabel, danger, busy, onConfirm, onCancel }: ActionProps) {
  return (
    <div className="sheet-backdrop centered" role="dialog" aria-modal="true" aria-label={title}>
      <div className="dialog glass">
        <h3>{title}</h3>
        {lines.map((line) => (
          <p key={line}>{line}</p>
        ))}
        <div className="actions">
          <button className={danger ? "btn-danger" : "btn-primary"} type="button" disabled={busy} onClick={onConfirm}>
            {busy ? "در حال انجام…" : confirmLabel}
          </button>
          <button className="btn-ghost" type="button" disabled={busy} onClick={onCancel}>
            انصراف
          </button>
        </div>
      </div>
    </div>
  );
}
