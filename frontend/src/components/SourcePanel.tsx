import { useEffect, useRef } from "react";
import type { Source } from "../types";

interface Props {
  sources: Source[];
  selected: number;
  quote?: string;
  onSelect: (n: number) => void;
  onClose: () => void;
}

export function SourcePanel({ sources, selected, quote, onSelect, onClose }: Props) {
  const markRef = useRef<HTMLElement>(null);
  const current = sources.find((s) => s.n === selected);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selected, quote]);

  const body = () => {
    if (!current) return null;
    const text = current.text;
    const i = quote ? text.toLowerCase().indexOf(quote.toLowerCase()) : -1;
    if (!quote || i < 0) return text; // unverified quotes are not found word for word: show plain text
    return (
      <>
        {text.slice(0, i)}
        <mark ref={markRef}>{text.slice(i, i + quote.length)}</mark>
        {text.slice(i + quote.length)}
      </>
    );
  };

  return (
    <aside className="panel">
      <div className="panel-head">
        <h3>Sources</h3>
        <button className="link" onClick={onClose}>Close</button>
      </div>
      <div className="source-tabs">
        {sources.map((s) => (
          <button key={s.n} className={s.n === selected ? "tab active" : "tab"} onClick={() => onSelect(s.n)}>
            {s.n}. {s.label.slice(1, -1)}
          </button>
        ))}
      </div>
      {current && <pre className="source-text">{body()}</pre>}
    </aside>
  );
}
