"""
tools/registry.py — Tool registry mapping names to callables.
The Orchestrator uses this to dynamically dispatch tool calls
without hardcoding function references in the loop logic.
"""
from typing import Callable, Awaitable, Any
from tools.etherscan import fetch_contract_source, fetch_wallet_history
from tools.web3_tools import check_ownership_status, read_contract_function
from tools.dex_tools import check_liquidity_lock
from tools.scam_lists import search_known_scam_lists

# Registry: tool_name → async callable
TOOL_REGISTRY: dict[str, Callable[..., Awaitable[Any]]] = {
    "fetch_contract_source":  fetch_contract_source,
    "fetch_wallet_history":   fetch_wallet_history,
    "check_ownership_status": check_ownership_status,
    "read_contract_function": read_contract_function,
    "check_liquidity_lock":   check_liquidity_lock,
    "search_known_scam_lists": search_known_scam_lists,
}


def get_tool(name: str) -> Callable[..., Awaitable[Any]]:
    """Retrieve a tool callable by name. Raises KeyError if not found."""
    if name not in TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: '{name}'. Available: {list(TOOL_REGISTRY.keys())}")
    return TOOL_REGISTRY[name]
