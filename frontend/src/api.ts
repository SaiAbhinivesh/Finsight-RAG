import type { AnswerEvent, Mode, StatusEvent } from "./types";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function getFilings(): Promise<Record<string, number[]>> {
  const res = await fetch(`${API}/filings`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

interface Handlers {
  onStatus: (e: StatusEvent) => void;
  onAnswer: (e: AnswerEvent) => void;
  onError: (message: string) => void;
}

/** Open the SSE stream for one question. Returns a function that closes it. */
export function streamAsk(question: string, mode: Mode, sessionId: string | null, h: Handlers): () => void {
  const params = new URLSearchParams({ question, mode });
  if (sessionId) params.set("session_id", sessionId);
  const es = new EventSource(`${API}/ask/stream?${params}`);

  es.addEventListener("status", (e) => h.onStatus(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("answer", (e) => {
    h.onAnswer(JSON.parse((e as MessageEvent).data));
    es.close(); // done: stop EventSource from auto-reconnecting
  });
  // Fires for our server's "error" event (has data) and for connection problems (no data)
  es.addEventListener("error", (e) => {
    const data = (e as MessageEvent).data;
    h.onError(data ? JSON.parse(data).message : "Connection to the API was lost");
    es.close();
  });

  return () => es.close();
}

/** Thumbs up (1) or down (0) for one answer; stored on its LangSmith trace. */
export async function sendFeedback(runId: string, score: 0 | 1, comment?: string): Promise<void> {
  const res = await fetch(`${API}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, score, comment: comment || null }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}
