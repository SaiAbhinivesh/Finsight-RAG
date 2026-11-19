import { useState } from "react";
import { sendFeedback } from "../api";

export function Feedback({ runId }: { runId: string }) {
  const [score, setScore] = useState<0 | 1 | null>(null);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  async function send(s: 0 | 1, text?: string) {
    setState("sending");
    try {
      await sendFeedback(runId, s, text);
      setState("sent");
    } catch {
      setState("error");
    }
  }

  if (state === "sent") return <div className="feedback">Thanks for the feedback.</div>;

  return (
    <div className="feedback">
      <span>Was this helpful?</span>
      <button className={score === 1 ? "fb on" : "fb"} disabled={state === "sending"}
        onClick={() => { setScore(1); send(1); }} aria-label="Helpful">👍</button>
      <button className={score === 0 ? "fb on" : "fb"} disabled={state === "sending"}
        onClick={() => setScore(0)} aria-label="Not helpful">👎</button>
      {score === 0 && (
        <form className="fb-form" onSubmit={(e) => { e.preventDefault(); send(0, comment.trim() || undefined); }}>
          <input autoFocus value={comment} onChange={(e) => setComment(e.target.value)}
            placeholder="What was wrong? (optional)" maxLength={2000} />
          <button type="submit" disabled={state === "sending"}>Send</button>
        </form>
      )}
      {state === "error" && <span className="error">Could not send feedback. Is the API running?</span>}
    </div>
  );
}
