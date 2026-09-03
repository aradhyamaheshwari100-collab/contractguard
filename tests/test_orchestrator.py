"""
tests/test_orchestrator.py — Integration test for the full orchestrator loop.
Mocks all external dependencies (LLM + Etherscan) to test the decision logic.
Run: pytest tests/test_orchestrator.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch
from models import ToolResult, AgentFindings, Finding, FindingSeverity
import os

os.environ.setdefault("ETHERSCAN_API_KEY", "test_key")
os.environ.setdefault("GEMINI_API_KEY", "test_key")
os.environ.setdefault("WEB3_PROVIDER_URL", "https://eth-sepolia.example.com")


def make_findings(agent: str, score: int, num_findings: int = 1) -> AgentFindings:
    findings = [
        Finding(
            severity=FindingSeverity.HIGH if score >= 70 else FindingSeverity.LOW,
            category="test_category",
            title=f"Test finding {i}",
            description="Test description",
        )
        for i in range(num_findings)
    ]
    return AgentFindings(
        agent=agent,
        suspicion_score=score,
        confidence="high",
        findings=findings,
        summary=f"Test summary from {agent}. Score: {score}.",
        insufficient_data=False,
    )


@pytest.mark.asyncio
async def test_orchestrator_clean_contract_fast_pass():
    """
    A clean contract (low suspicion from code analysis) should terminate
    at Phase 1 without escalating to history or cross-reference agents.
    Demonstrates: dynamic action selection.
    """
    clean_source = ToolResult.ok("fetch_contract_source", {
        "source_code": "pragma solidity ^0.8.20; contract CleanToken {}",
        "abi": "[]",
        "contract_name": "CleanToken",
        "is_verified": True,
        "deployer_address": "0xcleandeployer",
    })

    with patch("orchestrator.loop.fetch_contract_source", return_value=clean_source), \
         patch("orchestrator.loop.check_ownership_status", return_value=ToolResult.insufficient("ownership", "N/A")), \
         patch("agents.code_analysis.CodeAnalysisAgent.run", new_callable=AsyncMock,
               return_value=make_findings("code_analysis", score=15)), \
         patch("agents.synthesis.ReportSynthesisAgent.run", new_callable=AsyncMock,
               return_value=make_findings("synthesis", score=15)):

        from orchestrator.state import InvestigationState
        from orchestrator.loop import run_investigation

        state = InvestigationState("test-job-1", "0x" + "a" * 40, "sepolia")
        await run_investigation(state)

    # Should complete successfully
    assert state.final_report is not None
    assert state.final_report.verdict.value == "LOW"
    # History agent should NOT have been invoked (score was 15, below threshold 70)
    assert "history" not in state.agents_invoked
    assert "cross_reference" not in state.agents_invoked
    assert "code_analysis" in state.agents_invoked
    assert "synthesis" in state.agents_invoked


@pytest.mark.asyncio
async def test_orchestrator_suspicious_contract_escalates():
    """
    A suspicious contract (high suspicion from code analysis) should escalate
    to history investigation. Demonstrates: dynamic action selection + adaptation.
    """
    suspicious_source = ToolResult.ok("fetch_contract_source", {
        "source_code": "pragma solidity ^0.8.20; contract BackdooredToken { function emergencyWithdraw() external {} }",
        "abi": "[]",
        "contract_name": "BackdooredToken",
        "is_verified": True,
        "deployer_address": "0xsuspiciousdeployer",
    })

    history_result = ToolResult.ok("fetch_wallet_history", {
        "address": "0xsuspiciousdeployer",
        "transaction_count": 20,
        "transactions": [],
        "deployment_count": 3,
        "deployed_contracts": [],
    })

    with patch("orchestrator.loop.fetch_contract_source", return_value=suspicious_source), \
         patch("orchestrator.loop.fetch_wallet_history", return_value=history_result), \
         patch("orchestrator.loop.check_ownership_status", return_value=ToolResult.insufficient("ownership", "N/A")), \
         patch("orchestrator.loop.check_liquidity_lock", return_value=ToolResult.insufficient("liquidity", "Testnet")), \
         patch("agents.code_analysis.CodeAnalysisAgent.run", new_callable=AsyncMock,
               return_value=make_findings("code_analysis", score=82)), \
         patch("agents.history.OnChainHistoryAgent.run", new_callable=AsyncMock,
               return_value=make_findings("history", score=75)), \
         patch("agents.synthesis.ReportSynthesisAgent.run", new_callable=AsyncMock,
               return_value=make_findings("synthesis", score=82)):

        from orchestrator.state import InvestigationState
        from orchestrator.loop import run_investigation

        state = InvestigationState("test-job-2", "0x" + "b" * 40, "sepolia")
        await run_investigation(state)

    assert state.final_report is not None
    assert state.final_report.verdict.value == "HIGH"
    # History should have been invoked (score 82 > threshold 70)
    assert "history" in state.agents_invoked
    # Code analysis and synthesis always run
    assert "code_analysis" in state.agents_invoked
    assert "synthesis" in state.agents_invoked


@pytest.mark.asyncio
async def test_orchestrator_handles_tool_failure_gracefully():
    """
    When a tool fails (insufficient_data), the orchestrator should continue
    and produce a report. Demonstrates: robustness.
    """
    with patch("orchestrator.loop.fetch_contract_source",
               return_value=ToolResult.insufficient("fetch_contract_source", "API error")), \
         patch("orchestrator.loop.check_ownership_status",
               return_value=ToolResult.insufficient("check_ownership_status", "Not Ownable")), \
         patch("agents.code_analysis.CodeAnalysisAgent.run", new_callable=AsyncMock,
               return_value=AgentFindings.insufficient("code_analysis", "Source unavailable")), \
         patch("agents.synthesis.ReportSynthesisAgent.run", new_callable=AsyncMock,
               return_value=make_findings("synthesis", score=50)):

        from orchestrator.state import InvestigationState
        from orchestrator.loop import run_investigation

        state = InvestigationState("test-job-3", "0x" + "c" * 40, "sepolia")
        await run_investigation(state)

    # Should still complete, not crash
    assert state.final_report is not None
    # Insufficient data flags should be recorded
    assert len(state.insufficient_data_flags) > 0
    # Source was flagged as insufficient
    assert "fetch_contract_source" in state.insufficient_data_flags


@pytest.mark.asyncio
async def test_orchestrator_max_depth_guard():
    """
    Max depth guard prevents infinite escalation.
    Demonstrates: robustness guardrail.
    """
    from orchestrator import thresholds

    # Temporarily lower max depth for this test
    original_depth = thresholds.MAX_DEPTH
    thresholds.MAX_DEPTH = 1

    try:
        suspicious_source = ToolResult.ok("fetch_contract_source", {
            "source_code": "contract Evil {}",
            "abi": "[]",
            "contract_name": "Evil",
            "is_verified": True,
            "deployer_address": "0xevil",
        })

        with patch("orchestrator.loop.fetch_contract_source", return_value=suspicious_source), \
             patch("orchestrator.loop.check_ownership_status", return_value=ToolResult.insufficient("o", "")), \
             patch("agents.code_analysis.CodeAnalysisAgent.run", new_callable=AsyncMock,
                   return_value=make_findings("code_analysis", score=95)), \
             patch("agents.synthesis.ReportSynthesisAgent.run", new_callable=AsyncMock,
                   return_value=make_findings("synthesis", score=95)):

            from orchestrator.state import InvestigationState
            from orchestrator.loop import run_investigation

            state = InvestigationState("test-job-4", "0x" + "d" * 40, "sepolia")
            await run_investigation(state)

        assert state.final_report is not None
        # Depth should be capped at max
        assert state.depth <= 1

    finally:
        thresholds.MAX_DEPTH = original_depth


@pytest.mark.asyncio
async def test_trace_log_populated():
    """Verify trace steps are populated throughout the investigation."""
    clean_source = ToolResult.ok("fetch_contract_source", {
        "source_code": "contract Clean {}",
        "abi": "[]",
        "contract_name": "Clean",
        "is_verified": True,
        "deployer_address": "0xclean",
    })

    with patch("orchestrator.loop.fetch_contract_source", return_value=clean_source), \
         patch("orchestrator.loop.check_ownership_status", return_value=ToolResult.insufficient("o", "")), \
         patch("agents.code_analysis.CodeAnalysisAgent.run", new_callable=AsyncMock,
               return_value=make_findings("code_analysis", score=10)), \
         patch("agents.synthesis.ReportSynthesisAgent.run", new_callable=AsyncMock,
               return_value=make_findings("synthesis", score=10)):

        from orchestrator.state import InvestigationState
        from orchestrator.loop import run_investigation

        state = InvestigationState("test-job-5", "0x" + "e" * 40, "sepolia")
        await run_investigation(state)

    # Should have multiple trace steps
    assert len(state.trace) >= 4
    # First step should be a decision
    assert state.trace[0].step_type.value == "decision"
    # Last step should be termination
    assert state.trace[-1].step_type.value == "termination"
    # All steps should have sequential indices
    for i, step in enumerate(state.trace):
        assert step.step_index == i
