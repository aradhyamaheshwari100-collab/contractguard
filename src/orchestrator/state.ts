import {
  TraceStep,
  StepType,
  ToolResult,
  AgentFindings,
  FinalReport,
  InvestigationStatus,
} from "../types.js";

export class InvestigationState {
  jobId: string;
  address: string;
  chain: string;
  status: InvestigationStatus = InvestigationStatus.RUNNING;
  createdAt: string = new Date().toISOString();

  suspicionScore: number = 0;
  depth: number = 0;
  agentsInvoked: string[] = [];
  insufficientDataFlags: string[] = [];

  toolResults: Map<string, ToolResult> = new Map();
  agentFindings: Map<string, AgentFindings> = new Map();
  trace: TraceStep[] = [];
  finalReport: FinalReport | null = null;

  private sseListeners: Array<(step: TraceStep | null) => void> = [];

  constructor(jobId: string, address: string, chain: string) {
    this.jobId = jobId;
    this.address = address;
    this.chain = chain;
  }

  // ── SSE Subscriber registration ──────────────────────────────────────────
  subscribe(listener: (step: TraceStep | null) => void): () => void {
    // Replay existing steps
    for (const step of this.trace) {
      listener(step);
    }
    if (this.status === InvestigationStatus.COMPLETE || this.status === InvestigationStatus.FAILED) {
      listener(null); // End stream
      return () => {};
    }

    this.sseListeners.push(listener);
    return () => {
      this.sseListeners = this.sseListeners.filter((l) => l !== listener);
    };
  }

  private appendStep(step: TraceStep): void {
    this.trace.push(step);
    for (const listener of this.sseListeners) {
      try {
        listener(step);
      } catch (err) {
        console.error("Error in SSE listener:", err);
      }
    }
  }

  private nextIndex(): number {
    return this.trace.length;
  }

  traceDecision(decision: string, action: string = "evaluate"): TraceStep {
    const step: TraceStep = {
      step_index: this.nextIndex(),
      timestamp: new Date().toISOString(),
      step_type: StepType.DECISION,
      actor: "orchestrator",
      action,
      decision,
      suspicion_before: this.suspicionScore,
      suspicion_after: this.suspicionScore,
    };
    this.appendStep(step);
    return step;
  }

  traceToolCall(
    toolName: string,
    inputSummary: string,
    result: ToolResult,
    refKey: string
  ): TraceStep {
    const outputSummary =
      result.success && result.data
        ? `✓ ${result.data.contract_name || toolName} retrieved`
        : `⚠ Insufficient data: ${result.error || "Unknown error"}`;

    const step: TraceStep = {
      step_index: this.nextIndex(),
      timestamp: new Date().toISOString(),
      step_type: StepType.TOOL_CALL,
      actor: "orchestrator",
      action: toolName,
      input_summary: inputSummary,
      output_summary: outputSummary,
      suspicion_before: this.suspicionScore,
      suspicion_after: this.suspicionScore,
      tool_result_ref: refKey,
    };
    this.appendStep(step);
    return step;
  }

  traceAgent(agentName: string, findings: AgentFindings, scoreBefore: number): TraceStep {
    const delta = this.suspicionScore - scoreBefore;
    const step: TraceStep = {
      step_index: this.nextIndex(),
      timestamp: new Date().toISOString(),
      step_type: StepType.AGENT_INVOCATION,
      actor: agentName,
      action: `invoke_${agentName}`,
      output_summary: `Suspicion score: ${findings.suspicion_score}/100 | ${findings.findings.length} finding(s) | Confidence: ${findings.confidence}`,
      suspicion_before: scoreBefore,
      suspicion_after: this.suspicionScore,
      suspicion_delta: delta !== 0 ? delta : null,
      decision: findings.summary.slice(0, 200),
    };
    this.appendStep(step);
    return step;
  }

  traceThreshold(message: string, threshold: number, current: number): TraceStep {
    const triggered = current >= threshold;
    const step: TraceStep = {
      step_index: this.nextIndex(),
      timestamp: new Date().toISOString(),
      step_type: StepType.THRESHOLD_CHECK,
      actor: "orchestrator",
      action: "threshold_check",
      output_summary: `Score ${current} ${triggered ? "≥" : "<"} threshold ${threshold}`,
      decision: message,
      suspicion_before: current,
      suspicion_after: current,
    };
    this.appendStep(step);
    return step;
  }

  traceTermination(reason: string): TraceStep {
    const step: TraceStep = {
      step_index: this.nextIndex(),
      timestamp: new Date().toISOString(),
      step_type: StepType.TERMINATION,
      actor: "orchestrator",
      action: "terminate",
      decision: reason,
      suspicion_before: this.suspicionScore,
      suspicion_after: this.suspicionScore,
    };
    this.appendStep(step);

    // Notify listeners of completion
    for (const listener of this.sseListeners) {
      try {
        listener(null);
      } catch {}
    }
    this.sseListeners = [];
    return step;
  }

  updateSuspicion(newScore: number): void {
    this.suspicionScore = Math.max(this.suspicionScore, newScore);
  }

  storeToolResult(result: ToolResult, refKey: string): void {
    this.toolResults.set(refKey, result);
    if (result.insufficient_data && !this.insufficientDataFlags.includes(result.tool)) {
      this.insufficientDataFlags.push(result.tool);
    }
  }

  storeAgentFindings(findings: AgentFindings): void {
    this.agentFindings.set(findings.agent, findings);
    if (!this.agentsInvoked.includes(findings.agent)) {
      this.agentsInvoked.push(findings.agent);
    }
  }

  finalise(report: FinalReport): void {
    this.finalReport = report;
    this.status = InvestigationStatus.COMPLETE;
  }

  markFailed(reason: string): void {
    this.status = InvestigationStatus.FAILED;
    this.traceTermination(`Investigation failed: ${reason}`);
  }
}
