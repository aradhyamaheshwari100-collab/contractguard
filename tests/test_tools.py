"""
tests/test_tools.py — Unit tests for the tool layer.
Uses respx to mock Etherscan HTTP responses.
Run: pytest tests/test_tools.py -v
"""
import pytest
import respx
import httpx
import asyncio
from unittest.mock import AsyncMock, patch

# ── Fixtures ──────────────────────────────────────────────────────────────────

MOCK_SOURCE_RESPONSE = {
    "status": "1",
    "message": "OK",
    "result": [{
        "SourceCode": "pragma solidity ^0.8.20; contract TestToken {}",
        "ABI": '[{"inputs":[],"name":"totalSupply","outputs":[],"type":"function"}]',
        "ContractName": "TestToken",
        "CompilerVersion": "v0.8.20+commit.a1b79de6",
        "Proxy": "0",
        "Implementation": "",
    }]
}

MOCK_TX_RESPONSE = {
    "status": "1",
    "message": "OK",
    "result": [
        {"hash": "0xabc123", "from": "0xdeployer", "to": "", "value": "0",
         "contractAddress": "0xcontract1", "timeStamp": "1700000000", "isError": "0"},
        {"hash": "0xdef456", "from": "0xdeployer", "to": "0xrecipient", "value": "1000000000000000000",
         "contractAddress": "", "timeStamp": "1699000000", "isError": "0"},
    ]
}

MOCK_CREATION_RESPONSE = {
    "status": "1",
    "message": "OK",
    "result": [{"contractCreator": "0xdeadbeef1234"}]
}


@pytest.mark.asyncio
async def test_fetch_contract_source_success():
    """Test that fetch_contract_source correctly parses a successful Etherscan response."""
    # We need to set env vars before importing modules that use them
    import os
    os.environ.setdefault("ETHERSCAN_API_KEY", "test_key")
    os.environ.setdefault("GEMINI_API_KEY", "test_key")
    os.environ.setdefault("WEB3_PROVIDER_URL", "https://eth-sepolia.example.com")

    with respx.mock(base_url="https://api-sepolia.etherscan.io") as mock:
        # Mock source code endpoint
        mock.get("/api", params={"module": "contract", "action": "getsourcecode"}).mock(
            return_value=httpx.Response(200, json=MOCK_SOURCE_RESPONSE)
        )
        # Mock contract creation endpoint
        mock.get("/api", params={"module": "contract", "action": "getcontractcreation"}).mock(
            return_value=httpx.Response(200, json=MOCK_CREATION_RESPONSE)
        )

        from tools.etherscan import fetch_contract_source
        result = await fetch_contract_source("0x" + "a" * 40, "sepolia")

    assert result.success is True
    assert result.insufficient_data is False
    assert result.data is not None
    assert result.data["contract_name"] == "TestToken"
    assert result.data["is_verified"] is True
    assert result.data["deployer_address"] == "0xdeadbeef1234"


@pytest.mark.asyncio
async def test_fetch_contract_source_not_verified():
    """Test that unverified contracts return insufficient_data=False but is_verified=False."""
    import os
    os.environ.setdefault("ETHERSCAN_API_KEY", "test_key")
    os.environ.setdefault("GEMINI_API_KEY", "test_key")
    os.environ.setdefault("WEB3_PROVIDER_URL", "https://eth-sepolia.example.com")

    unverified_response = {
        "status": "1",
        "message": "OK",
        "result": [{"SourceCode": "", "ABI": "Contract source code not verified",
                     "ContractName": "", "CompilerVersion": "", "Proxy": "0", "Implementation": ""}]
    }

    with respx.mock(base_url="https://api-sepolia.etherscan.io") as mock:
        mock.get("/api").mock(return_value=httpx.Response(200, json=unverified_response))

        from tools.etherscan import fetch_contract_source
        result = await fetch_contract_source("0x" + "b" * 40, "sepolia")

    assert result.success is True
    assert result.data["is_verified"] is False
    assert result.data["source_code"] == ""


@pytest.mark.asyncio
async def test_fetch_contract_source_api_error():
    """Test graceful handling of Etherscan API errors."""
    import os
    os.environ.setdefault("ETHERSCAN_API_KEY", "test_key")
    os.environ.setdefault("GEMINI_API_KEY", "test_key")
    os.environ.setdefault("WEB3_PROVIDER_URL", "https://eth-sepolia.example.com")

    with respx.mock(base_url="https://api-sepolia.etherscan.io") as mock:
        mock.get("/api").mock(return_value=httpx.Response(500))

        from tools.etherscan import fetch_contract_source
        result = await fetch_contract_source("0x" + "c" * 40, "sepolia")

    assert result.success is False
    assert result.insufficient_data is True
    assert result.error is not None


@pytest.mark.asyncio
async def test_scam_list_csv_match():
    """Test that a known scam address is correctly identified from CSV."""
    import os
    os.environ.setdefault("ETHERSCAN_API_KEY", "test_key")
    os.environ.setdefault("GEMINI_API_KEY", "test_key")
    os.environ.setdefault("WEB3_PROVIDER_URL", "https://eth-sepolia.example.com")

    from tools.scam_lists import search_known_scam_lists, _load_scam_addresses
    # Clear the lru_cache to ensure fresh load
    _load_scam_addresses.cache_clear()

    # Known address from our CSV
    result = await search_known_scam_lists("0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a")
    assert result.success is True
    assert result.data["csv_match"] is True
    assert result.data["matched"] is True


@pytest.mark.asyncio
async def test_scam_list_no_match():
    """Test that a clean address is correctly not flagged."""
    from tools.scam_lists import search_known_scam_lists, _load_scam_addresses
    _load_scam_addresses.cache_clear()

    result = await search_known_scam_lists("0x" + "0" * 40)
    assert result.success is True
    assert result.data["matched"] is False


def test_tool_result_ok():
    """Test ToolResult.ok() factory method."""
    from models import ToolResult
    r = ToolResult.ok("test_tool", {"key": "value"})
    assert r.success is True
    assert r.insufficient_data is False
    assert r.data == {"key": "value"}


def test_tool_result_insufficient():
    """Test ToolResult.insufficient() factory method."""
    from models import ToolResult
    r = ToolResult.insufficient("test_tool", "Network error")
    assert r.success is False
    assert r.insufficient_data is True
    assert "Network error" in r.error
