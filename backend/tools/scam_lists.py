"""
tools/scam_lists.py — Known scam address lookup.
Primary: static CSV from data/known_scams.csv (curated CryptoScamDB snapshot).
Optional fallback: GoPlus Security API if GOPLUS_API_KEY is configured.
"""
import csv
import os
import httpx
from functools import lru_cache
from models import ToolResult
from config import settings

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
KNOWN_SCAMS_CSV = os.path.join(DATA_DIR, "known_scams.csv")


@lru_cache(maxsize=1)
def _load_scam_addresses() -> set[str]:
    """Load and cache known scam addresses from CSV (lowercased)."""
    addresses: set[str] = set()
    try:
        with open(KNOWN_SCAMS_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                addr = row.get("address", "").strip().lower()
                if addr.startswith("0x") and len(addr) == 42:
                    addresses.add(addr)
    except FileNotFoundError:
        pass  # CSV missing — will rely on GoPlus or return no-match
    return addresses


async def _check_goplus(address: str) -> dict | None:
    """Optional GoPlus Security API check. Returns None if key not configured."""
    if not settings.goplus_api_key:
        return None
    try:
        url = f"https://api.gopluslabs.io/api/v1/token_security/1"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url,
                params={"contract_addresses": address},
                headers={"Authorization": settings.goplus_api_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result", {}).get(address.lower(), {})
                return result
    except Exception:
        pass
    return None


async def search_known_scam_lists(address: str) -> ToolResult:
    """
    Check the given address (contract or deployer wallet) against:
    1. Local CSV of known scam addresses (always checked)
    2. GoPlus Security API (if API key configured)

    Returns match status, confidence, and source of the match.
    """
    addr_lower = address.lower()
    scam_addresses = _load_scam_addresses()

    csv_match = addr_lower in scam_addresses
    csv_confidence = "high" if csv_match else None

    # GoPlus check
    goplus_result = await _check_goplus(address)
    goplus_flagged = False
    goplus_details: dict = {}

    if goplus_result:
        # GoPlus returns is_honeypot, is_blacklisted, is_whitelisted etc.
        goplus_flagged = (
            goplus_result.get("is_honeypot") == "1"
            or goplus_result.get("is_blacklisted") == "1"
        )
        goplus_details = {
            "is_honeypot": goplus_result.get("is_honeypot"),
            "is_blacklisted": goplus_result.get("is_blacklisted"),
            "honeypot_with_same_creator": goplus_result.get("honeypot_with_same_creator"),
            "trading_cooldown": goplus_result.get("trading_cooldown"),
            "cannot_sell_all": goplus_result.get("cannot_sell_all"),
        }

    matched = csv_match or goplus_flagged
    sources = []
    if csv_match:
        sources.append("CryptoScamDB static list")
    if goplus_flagged:
        sources.append("GoPlus Security API")

    confidence = "high" if len(sources) > 1 else ("high" if csv_match else ("medium" if goplus_flagged else "none"))

    return ToolResult.ok("search_known_scam_lists", {
        "address": address,
        "matched": matched,
        "confidence": confidence,
        "match_sources": sources,
        "csv_match": csv_match,
        "goplus_flagged": goplus_flagged,
        "goplus_details": goplus_details if goplus_details else None,
        "total_known_scams_in_db": len(scam_addresses),
    })
