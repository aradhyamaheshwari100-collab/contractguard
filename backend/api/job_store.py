"""
api/job_store.py — In-memory job registry.
Maps job_id → InvestigationState for the lifetime of the server process.
For production: replace with Redis or a database-backed store.
"""
from __future__ import annotations
from typing import Optional
from orchestrator.state import InvestigationState

_jobs: dict[str, InvestigationState] = {}


def create_job(job_id: str, address: str, chain: str) -> InvestigationState:
    state = InvestigationState(job_id=job_id, address=address, chain=chain)
    _jobs[job_id] = state
    return state


def get_job(job_id: str) -> Optional[InvestigationState]:
    return _jobs.get(job_id)


def list_jobs() -> list[str]:
    return list(_jobs.keys())
