export enum RiskVerdict {
  LOW = "LOW",
  MEDIUM = "MEDIUM",
  HIGH = "HIGH",
  INSUFFICIENT_DATA = "INSUFFICIENT_DATA",
}

export enum StepType {
  DECISION = "decision",
  TOOL_CALL = "tool_call",
  AGENT_INVOCATION = "agent_invocation",
  THRESHOLD_CHECK = "threshold_check",
  TERMINATION = "termination",
  ERROR = "error",
}

export enum InvestigationStatus {
  PENDING = "pending",
  RUNNING = "running",
  COMPLETE = "complete",
  FAILED = "failed",
}

export enum FindingSeverity {
  CRITICAL = "critical",
  HIGH = "high",
  MEDIUM = "medium",
  LOW = "low",
  INFO = "info",
}

export interface ToolResult {
  tool: string;
  success: boolean;
  insufficient_data: boolean;
  data: Record<string, any> | null;
  error: string | null;
  cached: boolean;
  fetched_at: string;
}

export interface Finding {
  id: string;
  severity: FindingSeverity;
  category: string;
  title: string;
  description: string;
  evidence?: string | null;
  raw_snippet?: string | null;
  agent: string;
}

export interface AgentFindings {
  agent: string;
  suspicion_score: number;
  confidence: "low" | "medium" | "high";
  findings: Finding[];
  summary: string;
  insufficient_data: boolean;
}

export interface TraceStep {
  step_index: number;
  timestamp: string;
  step_type: StepType;
  actor: string;
  action: string;
  input_summary?: string | null;
  output_summary?: string | null;
  suspicion_before?: number | null;
  suspicion_after?: number | null;
  suspicion_delta?: number | null;
  decision?: string | null;
  tool_result_ref?: string | null;
}

export interface KeyFinding {
  severity: FindingSeverity;
  title: string;
  agent: string;
}

export interface FinalReport {
  job_id: string;
  address: string;
  chain: string;
  verdict: RiskVerdict;
  verdict_label: string;
  overall_suspicion_score: number;
  confidence: string;
  investigation_depth: number;
  agents_invoked: string[];
  key_findings: KeyFinding[];
  all_findings: Finding[];
  reasoning_trail: string;
  trace: TraceStep[];
  insufficient_data_flags: string[];
  generated_at: string;
}

export interface InvestigationJobResponse {
  job_id: string;
  stream_url: string;
  report_url: string;
  status: InvestigationStatus;
}
