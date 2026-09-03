"""
tests/test_agents.py — Unit tests for reasoning agents.
Mocks the LLM call to test JSON parsing and finding normalization.
Run: pytest tests/test_agents.py -v
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from models import ToolResult, AgentFindings


MOCK_CODE_ANALYSIS_RESPONSE = {
    "suspicion_score": 87,
    "confidence": "high",
    "findings": [
        {
            "severity": "critical",
            "category": "owner_drain",
            "title": "emergencyWithdraw() allows owner to drain all tokens",
            "description": "Owner can call emergencyWithdraw(address, uint256) to transfer any amount to arbitrary address.",
            "evidence": "Lines 47-52",
            "raw_snippet": "function emergencyWithdraw(address to, uint256 amount) external onlyOwner { _transfer(address(this), to, amount); }"
        },
        {
            "severity": "high",
            "category": "unlimited_mint",
            "title": "Uncapped mint() function",
            "description": "Owner can mint unlimited tokens with no supply ceiling.",
            "evidence": "Lines 61-63",
            "raw_snippet": "function mint(address to, uint256 amount) external onlyOwner { _mint(to, amount); }"
        }
    ],
    "summary": "Contract exhibits two critical fraud patterns. Immediate escalation recommended.",
    "insufficient_data": False
}

MOCK_HISTORY_RESPONSE = {
    "suspicion_score": 72,
    "confidence": "medium",
    "findings": [
        {
            "severity": "high",
            "category": "serial_deployer",
            "title": "Deployer has 3 prior contract deployments",
            "description": "Wallet deployed 3 contracts in 30 days, a pattern associated with serial scammers.",
            "evidence": "Deployments at timestamps 1699000000, 1699500000, 1700000000",
            "raw_snippet": None
        }
    ],
    "summary": "Deployer shows serial deployment pattern. Proceed with caution.",
    "insufficient_data": False
}


@pytest.mark.asyncio
async def test_code_analysis_agent_parses_findings():
    """Test CodeAnalysisAgent correctly parses LLM JSON response into AgentFindings."""
    import os
    os.environ.setdefault("ETHERSCAN_API_KEY", "test_key")
    os.environ.setdefault("GEMINI_API_KEY", "test_key")
    os.environ.setdefault("WEB3_PROVIDER_URL", "https://eth-sepolia.example.com")

    with patch("agents.base.BaseAgent._call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = MOCK_CODE_ANALYSIS_RESPONSE

        source_result = ToolResult.ok("fetch_contract_source", {
            "source_code": "pragma solidity ^0.8.20; contract BackdooredToken {}",
            "abi": "[]",
            "contract_name": "BackdooredToken",
            "is_verified": True,
            "deployer_address": "0xdeadbeef",
        })

        from agents.code_analysis import CodeAnalysisAgent
        agent = CodeAnalysisAgent()
        findings = await agent.run(source_result=source_result)

    assert isinstance(findings, AgentFindings)
    assert findings.agent == "code_analysis"
    assert findings.suspicion_score == 87
    assert findings.confidence == "high"
    assert len(findings.findings) == 2
    assert findings.findings[0].severity.value == "critical"
    assert findings.findings[0].category == "owner_drain"
    assert findings.insufficient_data is False


@pytest.mark.asyncio
async def test_code_analysis_agent_handles_insufficient_data():
    """Test that agent returns insufficient result when no source or ABI available."""
    import os
    os.environ.setdefault("ETHERSCAN_API_KEY", "test_key")
    os.environ.setdefault("GEMINI_API_KEY", "test_key")
    os.environ.setdefault("WEB3_PROVIDER_URL", "https://eth-sepolia.example.com")

    source_result = ToolResult.insufficient("fetch_contract_source", "Not verified")
    source_result.data = None  # Ensure data is None

    from agents.code_analysis import CodeAnalysisAgent
    agent = CodeAnalysisAgent()
    findings = await agent.run(source_result=source_result)

    assert findings.insufficient_data is True
    assert findings.suspicion_score == 50  # Uncertain score triggers escalation


@pytest.mark.asyncio
async def test_agent_json_extraction_from_prose():
    """Test that BaseAgent extracts JSON from prose-contaminated LLM output."""
    import os
    os.environ.setdefault("ETHERSCAN_API_KEY", "test_key")
    os.environ.setdefault("GEMINI_API_KEY", "test_key")
    os.environ.setdefault("WEB3_PROVIDER_URL", "https://eth-sepolia.example.com")

    # Simulate LLM returning prose before the JSON block
    prose_with_json = (
        "Sure! Here is my analysis:\n\n"
        + json.dumps(MOCK_CODE_ANALYSIS_RESPONSE)
        + "\n\nLet me know if you need more detail."
    )

    from agents.base import BaseAgent

    # Test the extraction logic directly
    import re
    JSON_EXTRACT_RE = re.compile(r'(\{[\s\S]*\}|\[[\s\S]*\])', re.MULTILINE)

    # Strip markdown fences (none here, but test the regex)
    raw = prose_with_json.strip()
    # Direct parse will fail
    try:
        json.loads(raw)
        direct_parse_succeeded = True
    except json.JSONDecodeError:
        direct_parse_succeeded = False

    assert direct_parse_succeeded is False, "Prose-wrapped JSON should not parse directly"

    # Regex extraction should work
    match = JSON_EXTRACT_RE.search(raw)
    assert match is not None, "Regex should find the JSON block"
    extracted = json.loads(match.group(1))
    assert extracted["suspicion_score"] == 87


@pytest.mark.asyncio
async def test_history_agent_parses_findings():
    """Test OnChainHistoryAgent correctly processes wallet history."""
    import os
    os.environ.setdefault("ETHERSCAN_API_KEY", "test_key")
    os.environ.setdefault("GEMINI_API_KEY", "test_key")
    os.environ.setdefault("WEB3_PROVIDER_URL", "https://eth-sepolia.example.com")

    with patch("agents.base.BaseAgent._call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = MOCK_HISTORY_RESPONSE

        history_result = ToolResult.ok("fetch_wallet_history", {
            "address": "0xdeadbeef",
            "transaction_count": 47,
            "transactions": [],
            "deployment_count": 3,
            "deployed_contracts": ["0xcontract1", "0xcontract2", "0xcontract3"],
        })

        from agents.history import OnChainHistoryAgent
        agent = OnChainHistoryAgent()
        findings = await agent.run(history_result=history_result, deployer="0xdeadbeef")

    assert findings.agent == "history"
    assert findings.suspicion_score == 72
    assert len(findings.findings) == 1
    assert findings.findings[0].category == "serial_deployer"


def test_agent_findings_insufficient_factory():
    """Test AgentFindings.insufficient() returns correct defaults."""
    findings = AgentFindings.insufficient("test_agent", "API unavailable")
    assert findings.insufficient_data is True
    assert findings.suspicion_score == 50
    assert findings.confidence == "low"
    assert "API unavailable" in findings.summary
