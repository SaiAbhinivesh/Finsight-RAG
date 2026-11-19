export type Mode = "fast" | "accurate";

export interface Citation {
  source: number;
  label: string | null;
  quote: string;
  verified: boolean;
}

export interface Source {
  n: number;
  label: string;
  company: string;
  fiscal_year: number;
  page: number;
  text: string;
}

export interface StatusEvent {
  event: "status";
  step: string;
  message: string;
}

export interface Usage {
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  llm_seconds: number;
  cost_usd: number;
  by_model: Record<string, { calls: number; input_tokens: number; output_tokens: number; cost_usd: number }>;
}

export interface AnswerEvent {
  event: "answer";
  answer: string;
  citations: Citation[];
  sources: Source[];
  steps: string[];
  mode: Mode;
  question: string;
  session_id: string;
  run_id: string;
  seconds: number;
  usage?: Usage;
  timings?: Record<string, number>;
  cached?: boolean;
  cache?: { matched_question: string; similarity: number };
}

export interface Turn {
  id: number;
  question: string;
  mode: Mode;
  status: StatusEvent[];
  result?: AnswerEvent;
  error?: string;
}
