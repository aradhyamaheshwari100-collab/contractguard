"""
tools/dex_tools.py — DEX liquidity lock checker.
Currently a graceful stub that returns insufficient_data.
This demonstrates the robustness requirement: the orchestrator
continues investigation even when a tool cannot provide data.
Post-hackathon: integrate DexScreener or Uniswap subgraph.
"""
from models import ToolResult


async def check_liquidity_lock(contract_address: str, chain: str = "sepolia") -> ToolResult:
    """
    Attempt to check if liquidity is locked for the given token contract.
    Returns insufficient_data on testnet (no DEX liquidity to check).
    On mainnet, would query DexScreener API or Uniswap subgraph.
    """
    # Testnet contracts have no real liquidity — this is expected behavior
    if chain in ("sepolia", "polygon_amoy"):
        return ToolResult.insufficient(
            "check_liquidity_lock",
            f"Liquidity lock check not available on {chain} testnet — "
            "no DEX liquidity exists on testnets. "
            "On mainnet, this would query DexScreener/Uniswap subgraph."
        )

    # Placeholder for mainnet integration
    # TODO: Integrate DexScreener API: https://api.dexscreener.com/latest/dex/tokens/{address}
    return ToolResult.insufficient(
        "check_liquidity_lock",
        "Mainnet DEX integration not yet implemented. "
        "See tools/dex_tools.py for integration instructions."
    )
