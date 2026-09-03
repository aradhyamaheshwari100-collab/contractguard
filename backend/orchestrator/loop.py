"""
orchestrator/loop.py — Core agent investigation loop.
Implements the explicit, inspectable decision cycle:
  decide next action → call tool → evaluate result → decide again → terminate

Five agentic behaviors demonstrated here:
  - Goal-driven:        always drives toward a final report
  - Dynamic selection:  Phases 2/3 only run if thresholds are crossed
  - Multi-step:         4 phases, each building on prior results
  - Adaptation:         ABI fallback if source unavailable; skips phases for clean contracts
  - Robustness:         every tool failure handled; max-depth guardrail prevents runaway loops
"""
from __future__ import annotations
import asyncio
from models import FinalReport, Finding, KeyFinding, RiskVerdict
from orchestrator.state import InvestigationState
from orchestrator.thresholds import (
    THRESHOLD_ESCALATE_HISTORY,
    THRESHOLD_ESCALATE_CROSSREF,
    MAX_DEPTH,
    score_to_verdict,
)
from tools.etherscan import fetch_contract_source, fetch_wallet_history
from tools.web3_tools import check_ownership_status
from tools.dex_tools import check_liquidity_lock
from tools.scam_lists import search_known_scam_lists
from agents.code_analysis import CodeAnalysisAgent
from agents.history import OnChainHistoryAgent
from agents.cross_reference import CrossReferenceAgent
from agents.synthesis import ReportSynthesisAgent


async def run_investigation(state: InvestigationState) -> None:
    """
    Main investigation coroutine. Mutates `state` throughout.
    Called as a background task after job creation.
    """
    try:
        await _phase_1_code_analysis(state)
        await _phase_2_history(state)
        await _phase_3_cross_reference(state)
        await _phase_4_synthesis(state)
    except Exception as e:
        state.mark_failed(str(e))


# ─── Phase 1: Fetch source + Code Analysis (always runs) ─────────────────────

async def _phase_1_code_analysis(state: InvestigationState) -> None:
    state.trace_decision(
        "Starting investigation. Phase 1: fetch contract source and run code analysis.",
        action="start"
    )

    # Fetch source
    source_result = await fetch_contract_source(state.address, state.chain)
    state.store_tool_result(source_result, "source_result")
    state.trace_tool_call(
        "fetch_contract_source",
        f"address={state.address}, chain={state.chain}",
        source_result,
        "source_result",
    )

    # Adaptation: if source unavailable, try ownership check as fallback signal
    if source_result.insufficient_data or not source_result.data:
        state.trace_decision(
            "Source code unavailable (unverified contract). "
            "Adapting: checking ownership status and proceeding with ABI-only analysis.",
            action="adapt"
        )
        ownership = await check_ownership_status(state.address)
        state.store_tool_result(ownership, "ownership_result")
        state.trace_tool_call(
            "check_ownership_status",
            f"address={state.address}",
            ownership,
            "ownership_result",
        )

    # Always run code analysis (even on insufficient data — agent handles it)
    score_before = state.suspicion_score
    agent = CodeAnalysisAgent()
    findings = await agent.run(
        source_result=source_result,
        ownership_result=state.tool_results.get("ownership_result"),
    )
    state.update_suspicion(findings.suspicion_score)
    state.store_agent_findings(findings)
    state.trace_agent("code_analysis", findings, score_before)

    state.trace_threshold(
        f"Code analysis complete. Score: {state.suspicion_score}/100. "
        f"Threshold for history escalation: {THRESHOLD_ESCALATE_HISTORY}.",
        THRESHOLD_ESCALATE_HISTORY,
        state.suspicion_score,
    )


# ─── Phase 2: On-Chain History (conditional) ──────────────────────────────────

async def _phase_2_history(state: InvestigationState) -> None:
    if state.suspicion_score < THRESHOLD_ESCALATE_HISTORY:
        state.trace_decision(
            f"Score {state.suspicion_score} < {THRESHOLD_ESCALATE_HISTORY}. "
            "History investigation not warranted. Proceeding to synthesis.",
            action="skip_phase_2"
        )
        return

    if state.depth >= MAX_DEPTH:
        state.trace_decision(
            f"Max depth ({MAX_DEPTH}) reached. Skipping further escalation.",
            action="depth_guard"
        )
        return

    state.depth += 1
    deployer = (
        state.tool_results.get("source_result", {})
        .data.get("deployer_address", "") if state.tool_results.get("source_result")
        and state.tool_results["source_result"].data
        else ""
    )

    state.trace_decision(
        f"Score {state.suspicion_score} ≥ {THRESHOLD_ESCALATE_HISTORY}. "
        f"Escalating to on-chain history investigation. Deployer: {deployer or 'unknown'}",
        action="escalate_phase_2"
    )

    if deployer:
        history_result = await fetch_wallet_history(deployer, state.chain)
        state.store_tool_result(history_result, "history_result")
        state.trace_tool_call(
            "fetch_wallet_history",
            f"deployer={deployer}, chain={state.chain}",
            history_result,
            "history_result",
        )
    else:
        from models import ToolResult
        history_result = ToolResult.insufficient(
            "fetch_wallet_history", "Deployer address not available"
        )
        state.store_tool_result(history_result, "history_result")

    score_before = state.suspicion_score
    agent = OnChainHistoryAgent()
    findings = await agent.run(history_result=history_result, deployer=deployer)
    state.update_suspicion(findings.suspicion_score)
    state.store_agent_findings(findings)
    state.trace_agent("history", findings, score_before)

    # Liquidity check (demonstrating tool diversity; graceful on testnet)
    liq_result = await check_liquidity_lock(state.address, state.chain)
    state.store_tool_result(liq_result, "liquidity_result")
    state.trace_tool_call(
        "check_liquidity_lock",
        f"address={state.address}, chain={state.chain}",
        liq_result,
        "liquidity_result",
    )

    state.trace_threshold(
        f"History analysis complete. Score: {state.suspicion_score}/100. "
        f"Threshold for cross-reference escalation: {THRESHOLD_ESCALATE_CROSSREF}.",
        THRESHOLD_ESCALATE_CROSSREF,
        state.suspicion_score,
    )


# ─── Phase 3: Cross-Reference (conditional) ───────────────────────────────────

async def _phase_3_cross_reference(state: InvestigationState) -> None:
    if state.suspicion_score < THRESHOLD_ESCALATE_CROSSREF:
        state.trace_decision(
            f"Score {state.suspicion_score} < {THRESHOLD_ESCALATE_CROSSREF}. "
            "Cross-reference check not triggered.",
            action="skip_phase_3"
        )
        return

    if state.depth >= MAX_DEPTH:
        state.trace_decision(
            f"Max depth ({MAX_DEPTH}) reached. Skipping cross-reference.",
            action="depth_guard"
        )
        return

    state.depth += 1
    deployer = (
        state.tool_results["source_result"].data.get("deployer_address", "")
        if state.tool_results.get("source_result") and state.tool_results["source_result"].data
        else ""
    )

    state.trace_decision(
        f"Score {state.suspicion_score} ≥ {THRESHOLD_ESCALATE_CROSSREF}. "
        "Escalating to cross-reference check against known scam lists.",
        action="escalate_phase_3"
    )

    # Check both contract address and deployer
    addresses_to_check = list(filter(None, [state.address, deployer]))
    xref_results = []
    for addr in addresses_to_check:
        result = await search_known_scam_lists(addr)
        state.store_tool_result(result, f"scam_check_{addr[:8]}")
        state.trace_tool_call(
            "search_known_scam_lists",
            f"address={addr}",
            result,
            f"scam_check_{addr[:8]}",
        )
        xref_results.append(result)

    score_before = state.suspicion_score
    agent = CrossReferenceAgent()
    findings = await agent.run(scam_results=xref_results, addresses_checked=addresses_to_check)
    state.update_suspicion(findings.suspicion_score)
    state.store_agent_findings(findings)
    state.trace_agent("cross_reference", findings, score_before)


# ─── Phase 4: Report Synthesis (always runs) ─────────────────────────────────

async def _phase_4_synthesis(state: InvestigationState) -> None:
    state.trace_decision(
        f"All investigation phases complete. Final score: {state.suspicion_score}/100. "
        "Invoking Report Synthesis Agent.",
        action="start_synthesis"
    )

    score_before = state.suspicion_score
    agent = ReportSynthesisAgent()
    findings = await agent.run(state=state)
    state.store_agent_findings(findings)
    state.trace_agent("synthesis", findings, score_before)

    verdict_value, verdict_label = score_to_verdict(state.suspicion_score)

    # Build key findings for report card
    all_raw_findings: list[Finding] = []
    for af in state.agent_findings.values():
        for f in af.findings:
            f.agent = af.agent
            all_raw_findings.append(f)

    key_findings = [
        KeyFinding(severity=f.severity, title=f.title, agent=f.agent)
        for f in sorted(all_raw_findings, key=lambda x: ["critical","high","medium","low","info"].index(x.severity.value))
        [:5]  # Top 5 findings for the report card
    ]

    report = FinalReport(
        job_id=state.job_id,
        address=state.address,
        chain=state.chain,
        verdict=RiskVerdict(verdict_value),
        verdict_label=verdict_label,
        overall_suspicion_score=state.suspicion_score,
        confidence=findings.confidence,
        investigation_depth=state.depth,
        agents_invoked=state.agents_invoked,
        key_findings=key_findings,
        all_findings=all_raw_findings,
        reasoning_trail=findings.summary,
        trace=state.trace,
        insufficient_data_flags=state.insufficient_data_flags,
    )
    state.finalise(report)
    state.trace_termination(
        f"Investigation complete. Verdict: {verdict_label} ({state.suspicion_score}/100). "
        f"Agents invoked: {', '.join(state.agents_invoked)}."
    )
