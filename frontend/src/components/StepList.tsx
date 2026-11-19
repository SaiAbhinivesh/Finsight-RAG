import { useState } from "react";
import type { StatusEvent } from "../types";

export function LiveSteps({ status }: { status: StatusEvent[] }) {
  return (
    <ul className="steps live">
      {status.map((s, i) => (
        <li key={i}>{s.message}</li>
      ))}
      <li className="working">Working…</li>
    </ul>
  );
}

export function StepSummary({ steps, seconds }: { steps: string[]; seconds: number }) {
  const [open, setOpen] = useState(false);
  return (
    <span>
      <button className="link" onClick={() => setOpen(!open)}>
        {open ? "Hide" : "Show"} how this was answered ({steps.length} steps, {seconds} s)
      </button>
      {open && (
        <ol className="steps">
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      )}
    </span>
  );
}
