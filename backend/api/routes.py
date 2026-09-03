"""
api/routes.py — FastAPI route definitions.
POST /investigate  → creates job, launches background investigation
GET  /stream/{id}  → SSE stream of live trace steps
GET  /report/{id}  → final report JSON (poll after stream completes)
GET  /health       → health check
"""
from __future__ import annotations
import uuid
import json
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from models import (
    InvestigationRequest, InvestigationJobResponse,
    InvestigationStatus, TraceStep
)
from api.job_store import create_job, get_job
from orchestrator.loop import run_investigation

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "ContractGuard"}


@router.post("/investigate", response_model=InvestigationJobResponse, status_code=202)
async def start_investigation(
    request: InvestigationRequest,
    background_tasks: BackgroundTasks,
):
    """
    Create a new investigation job and launch it as a background task.
    Returns immediately with job_id and URLs for streaming and the final report.
    """
    # Validate address format
    if not request.address.startswith("0x") or len(request.address) != 42:
        raise HTTPException(
            status_code=422,
            detail="Invalid contract address. Must be a 42-character hex string starting with 0x."
        )

    job_id = str(uuid.uuid4())
    state = create_job(job_id, request.address, request.chain.value)

    # Launch investigation as a background task (non-blocking)
    background_tasks.add_task(_run_investigation_bg, job_id)

    logger.info(f"Investigation started: job_id={job_id} address={request.address} chain={request.chain}")

    return InvestigationJobResponse(
        job_id=job_id,
        stream_url=f"/stream/{job_id}",
        report_url=f"/report/{job_id}",
        status=InvestigationStatus.PENDING,
    )


async def _run_investigation_bg(job_id: str) -> None:
    """Background wrapper that catches all errors and marks job as failed."""
    state = get_job(job_id)
    if not state:
        logger.error(f"Background task: job {job_id} not found in store")
        return
    try:
        await run_investigation(state)
    except Exception as e:
        logger.exception(f"Investigation {job_id} failed with unhandled error: {e}")
        state.mark_failed(str(e))


@router.get("/stream/{job_id}")
async def stream_investigation(job_id: str):
    """
    SSE endpoint: streams TraceStep events as they are produced by the orchestrator.
    The client subscribes with EventSource; each event is a JSON-encoded TraceStep.
    Final event has step_type=termination to signal completion.
    """
    state = get_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    async def event_generator():
        # SSE headers comment (keep-alive)
        yield ": ContractGuard SSE stream started\n\n"

        async for step in state.stream_steps():
            if step is None:
                # Sentinel — stream complete
                payload = json.dumps({"step_type": "complete", "job_id": job_id})
                yield f"data: {payload}\n\n"
                break

            # Serialize TraceStep to SSE event
            step_dict = {
                "step_index": step.step_index,
                "step_type": step.step_type.value,
                "actor": step.actor,
                "action": step.action,
                "output_summary": step.output_summary,
                "decision": step.decision,
                "suspicion_after": step.suspicion_after,
                "suspicion_delta": step.suspicion_delta,
                "timestamp": step.timestamp.isoformat(),
            }
            payload = json.dumps(step_dict)
            yield f"data: {payload}\n\n"

            # Small delay to prevent overwhelming the client
            await asyncio.sleep(0.05)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
            "Connection": "keep-alive",
        },
    )


@router.get("/report/{job_id}")
async def get_report(job_id: str):
    """
    Returns the final investigation report once the job is complete.
    Returns 202 with status if still running, 200 with report if done.
    """
    state = get_job(job_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if state.status == InvestigationStatus.RUNNING or state.status == InvestigationStatus.PENDING:
        return JSONResponse(
            status_code=202,
            content={"status": state.status.value, "job_id": job_id, "message": "Investigation in progress"}
        )

    if state.status == InvestigationStatus.FAILED:
        return JSONResponse(
            status_code=500,
            content={"status": "failed", "job_id": job_id, "message": "Investigation failed"}
        )

    if not state.final_report:
        raise HTTPException(status_code=500, detail="Investigation completed but report is missing")

    return state.final_report.model_dump(mode="json")
