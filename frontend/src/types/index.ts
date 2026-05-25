export interface ChatRequest {
  prompt: string;
  session_id?: string;
  history: { role: string; content: string }[];
}

export interface StrategyData {
  recommended_strategy: string;
  pit_window: string;
  predicted_position: string;
  predicted_total_time?: string;
  key_assumptions: string[];
  risk_factors: { risk: string; probability: string; impact: string }[];
  alternatives: string[];
  confidence: number;
  reasoning: string;
}

export interface TrackCardData {
  name: string;
  locality: string;
  country: string;
}

export interface WeatherCardData {
  air_temp_c: number;
  track_temp_c: number;
  humidity_pct: number;
  rainfall: boolean;
  wind_speed_kmh: number;
  sessions: string[];
}

export interface QualifyingResult {
  position: number;
  driver: string;
  team: string;
  q3_time: string;
}

export interface QualifyingCardData {
  results: QualifyingResult[];
}

export interface PracticeCardData {
  session: string;
  drivers_analyzed: number;
  summary: string;
}

export interface AgentOutput {
  summary?: string;
  [key: string]: unknown;
}

export type SSEEvent =
  | { type: "routing"; mode: string; message: string }
  | { type: "progress"; step: string; message: string }
  | { type: "data_card"; card_type: string; data: unknown }
  | { type: "agent_start"; agent: string }
  | { type: "agent_thinking"; agent: string; delta: string }
  | { type: "agent_text"; agent: string; delta: string }
  | { type: "agent_tool_call"; agent: string; tool: string; params: unknown }
  | { type: "agent_tool_result"; agent: string; tool: string; result: unknown }
  | { type: "agent_complete"; agent: string; output?: AgentOutput }
  | { type: "strategy_card"; strategy: StrategyData }
  | { type: "comparison_card"; comparison: ComparisonData }
  | { type: "complete"; elapsed_s?: number }
  | { type: "error"; message: string };

export type MessageRole = "user" | "system" | "agent";

export interface ComparisonData {
  season: number;
  round: number;
  actual: {
    results?: { driver: string; position: number; total_time_seconds?: number }[];
    error?: string;
  };
  prediction: Record<string, unknown>;
  has_prediction: boolean;
  reward?: number;
  trace_id?: string;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  agent?: string;
  content: string;
  thinking?: string;
  isStreaming?: boolean;
  dataCard?: { card_type: string; data: unknown };
  strategy?: StrategyData;
  comparison?: ComparisonData;
}

let _msgId = 0;
export function nextMsgId(): string {
  return `msg_${++_msgId}_${Date.now()}`;
}