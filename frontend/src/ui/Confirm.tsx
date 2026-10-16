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
