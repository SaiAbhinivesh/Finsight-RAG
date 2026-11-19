import type { AnswerEvent } from "../types";
import { Feedback } from "./Feedback";
import { StepSummary } from "./StepList";

// Matches labels like [PepsiCo 2022, p. 62]; the capture group keeps them in split()
const LABEL = /(\[[^\]]+?, p\. \d+\])/g;

interface Props {
  result: AnswerEvent;
  onOpenSource: (n: number, quote?: string) => void;
}

export function AnswerCard({ result, onOpenSource }: Props) {
  // A label in the text -> the citation (source number + quote) that backs it
  const lookup = (label: string) => {
    const c = result.citations.find((c) => c.label === label);
    if (c) return { n: c.source, quote: c.quote };
    const s = result.sources.find((s) => s.label === label);
    return s ? { n: s.n } : null;
  };

  const parts = result.answer.split(LABEL); // odd indexes are labels

  return (
    <div className="answer">
      {result.cached && result.cache && (
        <div className="cached" title={`Similarity ${result.cache.similarity}`}>
          Saved answer · reused from an earlier question: “{result.cache.matched_question}”
        </div>
      )}
      <p className="answer-text">
        {parts.map((part, i) => {
          if (i % 2 === 0) return <span key={i}>{part}</span>;
          const hit = lookup(part);
          return (
            <button key={i} className="chip" disabled={!hit} onClick={() => hit && onOpenSource(hit.n, hit.quote)}>
              {part.slice(1, -1)}
            </button>
          );
        })}
      </p>

      {result.citations.length > 0 && (
        <div className="citations">
          <h4>Evidence</h4>
          {result.citations.map((c, i) => (
            <button key={i} className="citation" onClick={() => onOpenSource(c.source, c.quote)}>
              <span className={c.verified ? "badge ok" : "badge warn"}>{c.verified ? "verified" : "unverified"}</span>
              <span className="cite-label">{c.label ?? `source ${c.source}`}</span>
              <span>“{c.quote}”</span>
            </button>
          ))}
        </div>
      )}

      <div className="meta">
        {result.cached ? (
          <span>Saved answer · {result.seconds} s</span>
        ) : result.mode === "accurate" ? (
          <StepSummary steps={result.steps} seconds={result.seconds} />
        ) : (
          <span>Fast mode · {result.seconds} s</span>
        )}
        <span> · {result.sources.length} sources read</span>
        {result.usage && !result.cached && (
          <span title={Object.entries(result.usage.by_model)
              .map(([m, u]) => `${m}: ${u.calls} calls, $${u.cost_usd.toFixed(4)}`).join("\n")}>
            {" "}· {result.usage.llm_calls} LLM calls · {(result.usage.input_tokens + result.usage.output_tokens).toLocaleString()} tokens
            {" "}· ${result.usage.cost_usd.toFixed(4)}
          </span>
        )}
      </div>

      <Feedback runId={result.run_id} />
    </div>
  );
}
