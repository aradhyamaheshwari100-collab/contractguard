"""
orchestrator/state.py — InvestigationState: the mutable job state.
Holds all tool results, agent findings, the ordered trace log,
and helper methods for appending steps and updating the suspicion score.
This object is the single source of truth for one investigation job.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Optional, AsyncGenerator
import asyncio
from models import (
    TraceStep, StepType, ToolResult, AgentFindings,
    FinalReport, InvestigationStatus, RiskVerdict
)
from orchestrator.thresholds import score_to_verdict


class InvestigationState:
    def __init__(self, job_id: str, address: str, chain: str):
        self.job_id = job_id
        self.address = address
        self.chain = chain
        self.status = InvestigationStatus.RUNNING
        self.created_at = datetime.utcnow()

        # Mutable state
        self.suspicion_score: int = 0
        self.depth: int = 0
        self.agents_invoked: list[str] = []
        self.insufficient_data_flags: list[str] = []

        # Storage
        self.tool_results: dict[str, ToolResult] = {}     # ref_key → ToolResult
        self.agent_findings: dict[str, AgentFindings] = {} # agent_name → findings
        self.trace: list[TraceStep] = []
        self.final_report: Optional[FinalReport] = None

        # SSE: new trace steps are queued here for streaming
        self._sse_queue: asyncio.Queue[Optional[TraceStep]] = asyncio.Queue()

    # ── Trace helpers ─────────────────────────────────────────────────────────

    def _append_step(self, step: TraceStep) -> None:
        self.trace.append(step)
        self._sse_queue.put_nowait(step)

    def _next_index(self) -> int:
        return len(self.trace)

    def trace_decision(self, decision: str, action: str = "evaluate") -> TraceStep:
        step = TraceStep(
            step_index=self._next_index(),
            step_type=StepType.DECISION,
            actor="orchestrator",
            action=action,
            decision=decision,
            suspicion_before=self.suspicion_score,
            suspicion_after=self.suspicion_score,
        )
        self._append_step(step)
        return step

    def trace_tool_call(
        self,
        tool_name: str,
        input_summary: str,
        result: ToolResult,
        ref_key: str,
    ) -> TraceStep:
        output_summary = (
            f"✓ {result.data.get('contract_name', '')} retrieved"
            if result.success and result.data
            else f"⚠ Insufficient data: {result.error or 'Unknown error'}"
        )
        step = TraceStep(
            step_index=self._next_index(),
            step_type=StepType.TOOL_CALL,
            actor="orchestrator",
            action=tool_name,
            input_summary=input_summary,
            output_summary=output_summary,
            suspicion_before=self.suspicion_score,
            suspicion_after=self.suspicion_score,
            tool_result_ref=ref_key,
        )
        self._append_step(step)
        return step

    def trace_agent(
        self,
        agent_name: str,
        findings: AgentFindings,
        score_before: int,
    ) -> TraceStep:
        step = TraceStep(
            step_index=self._next_index(),
            step_type=StepType.AGENT_INVOCATION,
            actor=agent_name,
            action=f"invoke_{agent_name}",
            output_summary=(
                f"Suspicion score: {findings.suspicion_score}/100 | "
                f"{len(findings.findings)} finding(s) | "
                f"Confidence: {findings.confidence}"
            ),
            suspicion_before=score_before,
            suspicion_after=self.suspicion_score,
            decision=findings.summary[:200] if findings.summary else "",
        )
        self._append_step(step)
        return step

    def trace_threshold(self, message: str, threshold: int, current: int) -> TraceStep:
        triggered = current >= threshold
        step = TraceStep(
            step_index=self._next_index(),
            step_type=StepType.THRESHOLD_CHECK,
            actor="orchestrator",
            action="threshold_check",
            output_summary=f"Score {current} {'≥' if triggered else '<'} threshold {threshold}",
            decision=message,
            suspicion_before=current,
            suspicion_after=current,
        )
        self._append_step(step)
        return step

    def trace_termination(self, reason: str) -> TraceStep:
        step = TraceStep(
            step_index=self._next_index(),
            step_type=StepType.TERMINATION,
            actor="orchestrator",
            action="terminate",
            decision=reason,
            suspicion_before=self.suspicion_score,
            suspicion_after=self.suspicion_score,
        )
        self._append_step(step)
        # Signal SSE stream end
        self._sse_queue.put_nowait(None)
        return step

    # ── Score management ──────────────────────────────────────────────────────

    def update_suspicion(self, new_score: int) -> None:
        """Set suspicion score from agent output (takes the max — score never goes down)."""
        self.suspicion_score = max(self.suspicion_score, new_score)

    def add_suspicion_delta(self, delta: int) -> None:
        """Increase suspicion score by delta, capped at 100."""
        self.suspicion_score = min(100, self.suspicion_score + delta)

    # ── Storage helpers ───────────────────────────────────────────────────────

    def store_tool_result(self, result: ToolResult, ref_key: str) -> None:
        self.tool_results[ref_key] = result
        if result.insufficient_data:
            self.insufficient_data_flags.append(result.tool)

    def store_agent_findings(self, findings: AgentFindings) -> None:
        self.agent_findings[findings.agent] = findings
        if findings.agent not in self.agents_invoked:
            self.agents_invoked.append(findings.agent)

    def all_findings_flat(self) -> list[dict]:
        """Return all findings from all agents as a flat list of dicts."""
        result = []
        for agent_findings in self.agent_findings.values():
            for f in agent_findings.findings:
                d = f.model_dump()
                d["agent"] = agent_findings.agent
                result.append(d)
        return result

    # ── SSE stream ────────────────────────────────────────────────────────────

    async def stream_steps(self) -> AsyncGenerator[Optional[TraceStep], None]:
        """
        Async generator that yields TraceStep objects as they are appended.
        Yields None as the final sentinel (stream is complete).
        """
        while True:
            step = await self._sse_queue.get()
            yield step
            if step is None:
                break

    # ── Finalise ──────────────────────────────────────────────────────────────

    def finalise(self, report: FinalReport) -> None:
        self.final_report = report
        self.status = InvestigationStatus.COMPLETE

    def mark_failed(self, reason: str) -> None:
        self.status = InvestigationStatus.FAILED
        self.trace_termination(f"Investigation failed: {reason}")
