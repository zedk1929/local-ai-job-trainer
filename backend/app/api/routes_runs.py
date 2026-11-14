from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from app.config import settings
from app.services.run_store import run_store

router = APIRouter()

class CreateRunRequest(BaseModel):
    project_id: str
    job_id: str = "survey-cleaner"
    learning_rate: Optional[float] = 2e-4
    epochs: Optional[int] = 3
    batch_size: Optional[int] = 4
    eval_split_ratio: Optional[float] = 0.15

@router.post("/runs")
async def start_run(req: CreateRunRequest):
    if settings.app_mode == "connected":
        raise HTTPException(
            status_code=400,
            detail=(
                "Adapter training is disabled in Connected Mode for this milestone. "
                "This milestone focuses on real batch baseline evaluation of your original local model (qwen2.5-coder:3b). "
                "Switch to Preview Mode if you wish to view simulated fixture runs."
            )
        )

    proj = await run_store.get_project(req.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    run_config = {
        "learning_rate": req.learning_rate,
        "epochs": req.epochs,
        "batch_size": req.batch_size,
        "eval_split_ratio": req.eval_split_ratio
    }

    run = await run_store.create_run(req.project_id, req.job_id, run_config)
    run_store.start_run_worker(run["id"])

    return run

@router.get("/runs")
async def list_runs(project_id: Optional[str] = None):
    return await run_store.list_runs(project_id)

@router.get("/runs/{run_id}")
async def get_run_status(run_id: str):
    run = await run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run

@router.get("/runs/{run_id}/events")
async def get_run_events(run_id: str):
    events = await run_store.get_run_events(run_id)
    return {"events": events}

@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    success = run_store.cancel_run(run_id)
    if not success:
        run = await run_store.get_run(run_id)
        if run and run["status"] in ["completed", "failed", "canceled", "interrupted"]:
            return {"status": run["status"], "message": f"Run already in terminal state '{run['status']}'."}
        raise HTTPException(status_code=400, detail="Unable to cancel run or run not active.")
    return {"status": "canceling", "message": "Cancellation signal sent to worker."}
