"""
tools/etherscan.py — Etherscan REST API integration.
Provides: fetch_contract_source, fetch_wallet_history, fetch_contract_creation.
All responses are cached via cache/store.py to avoid redundant API calls.
Implements exponential backoff on 429/5xx responses.
"""
import asyncio
import httpx
from typing import Optional
from models import ToolResult
from cache.store import cache
from config import settings

# ─── Etherscan base URLs by chain ────────────────────────────────────────────
CHAIN_URLS: dict[str, str] = {
    "mainnet":      "https://api.etherscan.io/api",
    "sepolia":      "https://api-sepolia.etherscan.io/api",
    "polygon":      "https://api.polygonscan.com/api",
    "polygon_amoy": "https://api-amoy.polygonscan.com/api",
}

MAX_RETRIES = 3
BACKOFF_BASE = 0.5  # seconds


def _base_url(chain: str) -> str:
    url = CHAIN_URLS.get(chain.lower())
    if not url:
        raise ValueError(f"Unsupported chain: {chain}. Supported: {list(CHAIN_URLS.keys())}")
    return url


async def _get(params: dict, chain: str) -> dict:
    """
    Make an Etherscan GET request with retry + exponential backoff.
    Returns the raw Etherscan JSON response dict.
    """
    params["apikey"] = settings.etherscan_api_key
    base = _base_url(chain)
    last_error: Optional[Exception] = None

    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.get(base, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    wait = BACKOFF_BASE * (2 ** attempt)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                last_error = e
                wait = BACKOFF_BASE * (2 ** attempt)
                await asyncio.sleep(wait)

    raise RuntimeError(f"Etherscan request failed after {MAX_RETRIES} retries: {last_error}")


async def fetch_contract_source(address: str, chain: str = "sepolia") -> ToolResult:
    """
    Fetch verified Solidity source code + ABI from Etherscan.
    Returns ToolResult with: source_code, abi, contract_name, compiler_version,
                              is_verified, deployer_address (from creation tx).
    """
    cache_key = f"source:{chain}:{address.lower()}"
    cached = await cache.get(cache_key)
    if cached:
        return ToolResult.ok("fetch_contract_source", cached, cached=True)

    try:
        data = await _get({
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
        }, chain)

        if data.get("status") != "1" or not data.get("result"):
            return ToolResult.insufficient("fetch_contract_source", "Etherscan returned no result")

        result = data["result"][0]
        source = result.get("SourceCode", "")
        is_verified = bool(source and source.strip())

        # Fetch deployer from contract creation tx
        deployer_address = await _get_deployer(address, chain)

        payload = {
            "source_code": source if is_verified else "",
            "abi": result.get("ABI", ""),
            "contract_name": result.get("ContractName", "Unknown"),
            "compiler_version": result.get("CompilerVersion", ""),
            "is_verified": is_verified,
            "deployer_address": deployer_address,
            "proxy": result.get("Proxy", "0"),
            "implementation": result.get("Implementation", ""),
        }

        await cache.set(cache_key, payload)
        return ToolResult.ok("fetch_contract_source", payload)

    except Exception as e:
        return ToolResult.insufficient("fetch_contract_source", str(e))


async def _get_deployer(address: str, chain: str) -> str:
    """Fetch the deployer address from the contract creation transaction."""
    try:
        data = await _get({
            "module": "contract",
            "action": "getcontractcreation",
            "contractaddresses": address,
        }, chain)
        if data.get("status") == "1" and data.get("result"):
            return data["result"][0].get("contractCreator", "")
    except Exception:
        pass
    return ""


async def fetch_wallet_history(
    address: str,
    chain: str = "sepolia",
    limit: int = 100
) -> ToolResult:
    """
    Fetch the transaction history for a wallet address (e.g., deployer).
    Returns the last `limit` transactions including internal txs.
    """
    cache_key = f"txhistory:{chain}:{address.lower()}:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return ToolResult.ok("fetch_wallet_history", cached, cached=True)

    try:
        # Normal transactions
        normal_data = await _get({
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": limit,
            "sort": "desc",
        }, chain)

        normal_txs = []
        if normal_data.get("status") == "1":
            normal_txs = normal_data.get("result", [])

        # Contract creation txs for this deployer
        created_contracts_data = await _get({
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 50,
            "sort": "desc",
        }, chain)

        # Filter for contract deployments (to == "" means contract creation)
        deployments = [
            tx for tx in normal_txs
            if tx.get("to", "").lower() == "" and tx.get("contractAddress")
        ]

        payload = {
            "address": address,
            "transaction_count": len(normal_txs),
            "transactions": normal_txs[:50],  # Cap at 50 for LLM context
            "deployment_count": len(deployments),
            "deployed_contracts": [tx.get("contractAddress", "") for tx in deployments],
        }

        await cache.set(cache_key, payload)
        return ToolResult.ok("fetch_wallet_history", payload)

    except Exception as e:
        return ToolResult.insufficient("fetch_wallet_history", str(e))
