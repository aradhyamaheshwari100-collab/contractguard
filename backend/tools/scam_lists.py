"""Static scam list threat intelligence tool using data/known_scams.csv.

Provides offline, reliable scam and honeypot detection without relying
on external third-party APIs or GOPLUS_API_KEY.
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config import settings


class ScamRecord:
    def __init__(self, address: str, label: str, source: str, date_added: str, is_scam: bool):
        self.address = address
        self.label = label
        self.source = source
        self.date_added = date_added
        self.is_scam = is_scam

    def to_dict(self) -> Dict[str, Any]:
        return {
            "address": self.address,
            "label": self.label,
            "source": self.source,
            "date_added": self.date_added,
            "is_scam": self.is_scam,
        }


_cached_scam_db: Optional[Tuple[Dict[str, ScamRecord], int]] = None


def resolve_csv_path() -> Optional[Path]:
    configured = getattr(settings, "known_scams_file_path", "data/known_scams.csv")
    candidates = [
        Path(configured),
        Path(os.getcwd()) / configured,
        Path(os.getcwd()) / "data" / "known_scams.csv",
        Path(__file__).resolve().parent.parent.parent / "data" / "known_scams.csv",
        Path("/data/known_scams.csv"),
    ]

    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def load_scam_database() -> Tuple[Dict[str, ScamRecord], int]:
    global _cached_scam_db
    if _cached_scam_db is not None:
        return _cached_scam_db

    scam_map: Dict[str, ScamRecord] = {}
    scam_count = 0

    csv_path = resolve_csv_path()
    if csv_path and csv_path.exists():
        try:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    addr = (row.get("address") or "").strip().lower()
                    if addr and addr.startswith("0x") and len(addr) == 42:
                        label = (row.get("label") or "Reported scam entity").strip()
                        source = (row.get("source") or "Threat Intelligence CSV").strip()
                        date_added = (row.get("date_added") or "").strip()

                        lower_label = label.lower()
                        is_not_scam = "not scam" in lower_label or "false positive" in lower_label
                        is_scam = not is_not_scam

                        record = ScamRecord(
                            address=addr,
                            label=label,
                            source=source,
                            date_added=date_added,
                            is_scam=is_scam,
                        )
                        scam_map[addr] = record
                        if is_scam:
                            scam_count += 1
        except Exception as e:
            print(f"Warning: Failed to parse known_scams.csv: {e}")
    else:
        print("Warning: Could not locate known_scams.csv threat intelligence database.")

    _cached_scam_db = (scam_map, scam_count)
    return _cached_scam_db


def search_known_scam_lists(address: str) -> Dict[str, Any]:
    """Search known scam threat list CSV offline without any external API calls."""
    clean_addr = address.strip().lower()
    scam_map, scam_count = load_scam_database()
    record = scam_map.get(clean_addr)

    matched = bool(record and record.is_scam)
    sources: List[str] = []
    if matched and record:
        sources.append(record.source or "CryptoScamDB static list")

    confidence = "high" if matched else "none"

    return {
        "tool": "search_known_scam_lists",
        "success": True,
        "insufficient_data": False,
        "data": {
            "address": address,
            "matched": matched,
            "confidence": confidence,
            "match_sources": sources,
            "csv_match": matched,
            "record": record.to_dict() if record else None,
            "known_benign": bool(record and not record.is_scam),
            "total_known_scams_in_db": scam_count,
        },
        "error": None,
        "cached": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
