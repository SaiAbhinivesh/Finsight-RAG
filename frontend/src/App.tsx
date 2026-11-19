import { useEffect, useRef, useState } from "react";
import { getFilings, streamAsk } from "./api";
import { AnswerCard } from "./components/AnswerCard";
import { SourcePanel } from "./components/SourcePanel";
import { LiveSteps } from "./components/StepList";
import type { Mode, Turn } from "./types";

const EXAMPLES = [
  "What production rate changes is Boeing forecasting for FY2023?",
  "What is the FY2022 unadjusted EBITDA % margin for PepsiCo? Use D&A from the cash flow statement.",
  "Does AMD have a reasonably healthy liquidity profile based on its quick ratio for FY22?",
  "What is Verizon's dividend policy for 2030?",
];

export default function App() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<Mode>("fast");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [filings, setFilings] = useState<Record<string, number[]>>({});
  const [panel, setPanel] = useState<{ turnId: number; n: number; quote?: string } | null>(null);
  const stopRef = useRef<(() => void) | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const busy = turns.some((t) => !t.result && !t.error);

  useEffect(() => {
    getFilings().then(setFilings).catch(() => {});
  }, []);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const update = (id: number, change: (t: Turn) => Turn) =>
    setTurns((ts) => ts.map((t) => (t.id === id ? change(t) : t)));

  function submit(text = question) {
    const q = text.trim();
    if (q.length < 3 || busy) return;
    const id = Date.now();
    setTurns((ts) => [...ts, { id, question: q, mode, status: [] }]);
    setQuestion("");
    stopRef.current = streamAsk(q, mode, sessionId, {
      onStatus: (s) => update(id, (t) => ({ ...t, status: [...t.status, s] })),
      onAnswer: (a) => {
        update(id, (t) => ({ ...t, result: a }));
        setSessionId(a.session_id); // next question is a follow-up in the same session
      },
      onError: (message) => update(id, (t) => ({ ...t, error: message })),
    });
  }

  function newConversation() {
    stopRef.current?.();
    setTurns([]);
    setSessionId(null);
    setPanel(null);
  }

  const panelTurn = turns.find((t) => t.id === panel?.turnId);
  const covered = Object.entries(filings).map(([c, ys]) => `${c} (${ys.join(", ")})`).join(" · ");

  return (
    <div className={panel ? "app with-panel" : "app"}>
      <main>
        <header>
          <h1>FinSight</h1>
          <p className="sub">
            Answers from SEC 10-K filings, with every quote checked against the source.
            {covered && <> Covers {covered}.</>}
          </p>
          {turns.length > 0 && (
            <button className="link" onClick={newConversation}>New conversation</button>
          )}
        </header>

        {turns.length === 0 && (
          <div className="examples">
            {EXAMPLES.map((e) => (
              <button key={e} className="example" onClick={() => submit(e)}>{e}</button>
            ))}
          </div>
        )}

        {turns.map((t) => (
          <section key={t.id} className="turn">
            <div className="question">
              {t.question} <span className="mode-tag">{t.mode}</span>
            </div>
            {t.result ? (
              <>
                {t.result.question !== t.question && (
                  <div className="understood">Understood as: {t.result.question}</div>
                )}
                <AnswerCard result={t.result} onOpenSource={(n, quote) => setPanel({ turnId: t.id, n, quote })} />
              </>
            ) : t.error ? (
              <div className="error">Something went wrong: {t.error}</div>
            ) : (
              <LiveSteps status={t.status} />
            )}
          </section>
        ))}
        <div ref={bottomRef} />

        <form className="ask" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <textarea
            rows={2}
            value={question}
            placeholder={sessionId ? "Ask a follow-up…" : "Ask about a company's 10-K…"}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
            }}
          />
          <div className="controls">
            <div className="toggle">
              {(["fast", "accurate"] as Mode[]).map((m) => (
                <button key={m} type="button" className={mode === m ? "on" : ""} onClick={() => setMode(m)}
                  title={m === "fast" ? "One search, about 25 s" : "Plans, searches several times, calculates, about 60 s"}>
                  {m === "fast" ? "Fast" : "Accurate"}
                </button>
              ))}
            </div>
            <button type="submit" disabled={busy || question.trim().length < 3}>
              {busy ? "Working…" : "Ask"}
            </button>
          </div>
        </form>
      </main>

      {panel && panelTurn?.result && (
        <SourcePanel
          sources={panelTurn.result.sources}
          selected={panel.n}
          quote={panel.quote}
          onSelect={(n) => setPanel({ ...panel, n, quote: undefined })}
          onClose={() => setPanel(null)}
        />
      )}
    </div>
  );
}
