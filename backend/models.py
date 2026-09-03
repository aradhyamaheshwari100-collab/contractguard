"""
models.py — All Pydantic data contracts for ContractGuard.
These schemas are the single source of truth passed between:
  Orchestrator ↔ Agents ↔ Tools ↔ API ↔ Frontend
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class RiskVerdict(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class StepType(str, Enum):
    DECISION = "decision"
    TOOL_CALL = "tool_call"
    AGENT_INVOCATION = "agent_invocation"
    THRESHOLD_CHECK = "threshold_check"
    TERMINATION = "termination"
    ERROR = "error"


class InvestigationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SupportedChain(str, Enum):
    SEPOLIA = "sepolia"
    MAINNET = "mainnet"
    POLYGON_AMOY = "polygon_amoy"
    POLYGON = "polygon"


# ─────────────────────────────────────────────────────────────────────────────
# Tool Layer Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ToolResult(BaseModel):
    """Consistent envelope returned by every tool call."""
    tool: str
    success: bool
    insufficient_data: bool = False
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    cached: bool = False
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def ok(cls, tool: str, data: dict, cached: bool = False) -> "ToolResult":
        return cls(tool=tool, success=True, data=data, cached=cached)

    @classmethod
    def insufficient(cls, tool: str, error: str) -> "ToolResult":
        return cls(tool=tool, success=False, insufficient_data=True, error=error)

    @classmethod
    def failure(cls, tool: str, error: str) -> "ToolResult":
        return cls(tool=tool, success=False, insufficient_data=True, error=error)


# ─────────────────────────────────────────────────────────────────────────────
# Agent Schemas
# ─────────────────────────────────────────────────────────────────────────────

class Finding(BaseModel):
    """A single security finding from any reasoning agent."""
    id: str = Field(default_factory=lambda: f"FINDING-{uuid.uuid4().hex[:6].upper()}")
    severity: FindingSeverity
    category: str
    title: str
    description: str
    evidence: Optional[str] = None
    raw_snippet: Optional[str] = None
    agent: str = ""


class AgentFindings(BaseModel):
    """Structured output from any reasoning agent."""
    agent: str
    suspicion_score: int = Field(ge=0, le=100)
    confidence: str = "medium"  # low | medium | high
    findings: list[Finding] = Field(default_factory=list)
    summary: str = ""
    insufficient_data: bool = False

    @classmethod
    def insufficient(cls, agent: str, reason: str) -> "AgentFindings":
        return cls(
            agent=agent,
            suspicion_score=50,  # Uncertain — triggers escalation
            confidence="low",
            findings=[],
            summary=f"Insufficient data: {reason}",
            insufficient_data=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator / Trace Schemas
# ─────────────────────────────────────────────────────────────────────────────

class TraceStep(BaseModel):
    """One step in the investigation trace log — used by UI + final report."""
    step_index: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    step_type: StepType
    actor: str = "orchestrator"
    action: str
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    suspicion_before: Optional[int] = None
    suspicion_after: Optional[int] = None
    decision: Optional[str] = None
    tool_result_ref: Optional[str] = None

    @property
    def suspicion_delta(self) -> Optional[int]:
        if self.suspicion_before is not None and self.suspicion_after is not None:
            return self.suspicion_after - self.suspicion_before
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Final Report
# ─────────────────────────────────────────────────────────────────────────────

class KeyFinding(BaseModel):
    severity: FindingSeverity
    title: str
    agent: str


class FinalReport(BaseModel):
    """The complete investigation report returned to the frontend."""
    job_id: str
    address: str
    chain: str
    verdict: RiskVerdict
    verdict_label: str
    overall_suspicion_score: int
    confidence: str
    investigation_depth: int
    agents_invoked: list[str]
    key_findings: list[KeyFinding]
    all_findings: list[Finding] = Field(default_factory=list)
    reasoning_trail: str
    trace: list[TraceStep]
    insufficient_data_flags: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# API Request / Response
# ─────────────────────────────────────────────────────────────────────────────

class InvestigationRequest(BaseModel):
    address: str = Field(..., description="Contract address to investigate (0x...)")
    chain: SupportedChain = Field(default=SupportedChain.SEPOLIA)


class InvestigationJobResponse(BaseModel):
    job_id: str
    stream_url: str
    report_url: str
    status: InvestigationStatus = InvestigationStatus.PENDING


class SSEEvent(BaseModel):
    """Serialized form sent over the SSE stream."""
    step_index: int
    step_type: str
    actor: str = "orchestrator"
    action: str
    output_summary: Optional[str] = None
    suspicion_after: Optional[int] = None
    decision: Optional[str] = None
    verdict: Optional[str] = None  # Only set on final "complete" event
