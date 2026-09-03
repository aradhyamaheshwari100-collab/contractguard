"""
tools/web3_tools.py — Live read-only contract interaction via web3.py.
Provides: check_ownership_status, read_contract_function.
Connects to Sepolia (or configured chain) via Alchemy/Infura RPC.
"""
from typing import Any
from models import ToolResult
from config import settings

# Lazy import web3 to avoid import errors if not installed during testing
try:
    from web3 import AsyncWeb3
    from web3.middleware import async_geth_poa_middleware  # type: ignore
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False

# Standard ERC-20 / Ownable ABI fragments (read-only subset)
OWNABLE_ABI = [
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

ERC20_ABI = [
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "name",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
]

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _get_web3() -> Any:
    if not WEB3_AVAILABLE:
        raise RuntimeError("web3 package not installed")
    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(settings.web3_provider_url))
    return w3


async def check_ownership_status(contract_address: str) -> ToolResult:
    """
    Read the `owner()` function from the contract on-chain.
    Returns whether ownership is renounced (owner == zero address).
    This is a key "proof moment" — live on-chain confirmation.
    """
    if not WEB3_AVAILABLE:
        return ToolResult.insufficient(
            "check_ownership_status",
            "web3 package not installed — skipping ownership check"
        )

    try:
        w3 = _get_web3()
        checksum_addr = AsyncWeb3.to_checksum_address(contract_address)
        contract = w3.eth.contract(address=checksum_addr, abi=OWNABLE_ABI)
        owner = await contract.functions.owner().call()

        is_renounced = owner.lower() == ZERO_ADDRESS
        return ToolResult.ok("check_ownership_status", {
            "contract_address": contract_address,
            "owner": owner,
            "is_renounced": is_renounced,
            "renouncement_note": (
                "Ownership renounced — owner is zero address" if is_renounced
                else f"Active owner: {owner}"
            ),
        })

    except Exception as e:
        # Contract may not implement Ownable — not necessarily suspicious
        return ToolResult.insufficient(
            "check_ownership_status",
            f"Contract does not implement Ownable or call failed: {e}"
        )


async def read_contract_function(
    contract_address: str,
    function_name: str,
    abi: list | None = None,
) -> ToolResult:
    """
    Generic read-only call to any view/pure function on a contract.
    Used for live "proof" demonstrations (e.g., totalSupply, name, symbol).
    """
    if not WEB3_AVAILABLE:
        return ToolResult.insufficient(
            "read_contract_function",
            "web3 package not installed"
        )

    if abi is None:
        abi = ERC20_ABI  # Default to ERC-20 read functions

    try:
        w3 = _get_web3()
        checksum_addr = AsyncWeb3.to_checksum_address(contract_address)
        contract = w3.eth.contract(address=checksum_addr, abi=abi)

        func = getattr(contract.functions, function_name, None)
        if func is None:
            return ToolResult.insufficient(
                "read_contract_function",
                f"Function '{function_name}' not found in provided ABI"
            )

        result = await func().call()
        return ToolResult.ok("read_contract_function", {
            "contract_address": contract_address,
            "function": function_name,
            "result": str(result),
        })

    except Exception as e:
        return ToolResult.insufficient(
            "read_contract_function",
            f"Call to {function_name} failed: {e}"
        )
