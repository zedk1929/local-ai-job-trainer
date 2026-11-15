import csv
import io
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Response, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from app.config import settings
from app.services.baseline_runner import baseline_batch_runner
from app.services.run_store import run_store

router = APIRouter()

class StartBaselineRequest(BaseModel):
    project_id: str
    dataset_id: Optional[str] = None
    rows: Optional[List[Dict[str, Any]]] = None
    response_col: str
    id_col: Optional[str] = None
    label_topics_col: Optional[str] = None
    label_sentiment_col: Optional[str] = None
    label_needs_review_col: Optional[str] = None
    concurrency: Optional[int] = 1

@router.post("/baseline/start")
async def start_baseline_batch(req: StartBaselineRequest):
    proj = await run_store.get_project(req.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    rows_to_process = []
    if req.rows and len(req.rows) > 0:
        rows_to_process = req.rows
    elif req.dataset_id:
        if req.dataset_id in ("sample_cafe_labeled", "sample_dev_60"):
            is_dev_60 = req.dataset_id == "sample_dev_60"
            sample_path = settings.dev_sample_csv_path if is_dev_60 else settings.sample_csv_path
            default_filename = "dev_survey_60_labeled.csv" if is_dev_60 else "sample_survey_labeled.csv"
            if not sample_path.exists():
                sample_path = Path(__file__).resolve().parent.parent.parent / "data" / default_filename
            with open(sample_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows_to_process = list(reader)
        else:
            # Load from disk
            ds = await run_store.get_dataset(req.dataset_id)
            if not ds:
                datasets = await run_store.list_datasets(req.project_id)
                ds = next((d for d in datasets if d["id"] == req.dataset_id), None)
            if not ds:
                raise HTTPException(status_code=404, detail=f"Dataset '{req.dataset_id}' not found")

            filepath = ds["filepath"]
            try:
                with open(filepath, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    rows_to_process = list(reader)
            except UnicodeDecodeError:
                with open(filepath, "r", encoding="latin-1") as f:
                    reader = csv.DictReader(f)
                    rows_to_process = list(reader)
    else:
        raise HTTPException(status_code=400, detail="Must provide either dataset_id or rows to process.")

    if len(rows_to_process) == 0:
        raise HTTPException(status_code=400, detail="No rows found to process.")

    # Validate required response column
    available_cols = list(rows_to_process[0].keys())
    if req.response_col not in available_cols:
        raise HTTPException(
            status_code=400,
            detail=f"Required response column '{req.response_col}' not found in dataset. Available columns: {available_cols}"
        )

    batch = await baseline_batch_runner.create_and_start_batch(
        project_id=req.project_id,
        dataset_id=req.dataset_id or "inline_rows",
        rows=rows_to_process,
        response_col=req.response_col,
        id_col=req.id_col,
        label_topics_col=req.label_topics_col,
        label_sentiment_col=req.label_sentiment_col,
        label_needs_review_col=req.label_needs_review_col,
        concurrency=req.concurrency or 1
    )
    return batch

@router.get("/baseline/active/{project_id}")
async def get_active_or_latest_batch(project_id: str):
    batch = await baseline_batch_runner.get_latest_batch_for_project(project_id)
    if not batch:
        return {"batch": None}
    return {"batch": batch}

@router.get("/baseline/batch/{batch_id}")
async def get_batch_details(batch_id: str):
    batch = await baseline_batch_runner.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")
    return {"batch": batch}

@router.post("/baseline/batch/{batch_id}/retry")
async def retry_baseline_batch(batch_id: str):
    try:
        batch = await baseline_batch_runner.retry_batch(batch_id)
        return batch
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry batch: {str(e)}")

@router.get("/baseline/batch/{batch_id}/predictions")
async def get_batch_predictions(
    batch_id: str,
    filter_mode: str = Query("all", pattern="^(all|mistakes|errors|flagged)$"),
    limit: int = 500,
    offset: int = 0
):
    preds = await baseline_batch_runner.list_batch_predictions(
        batch_id=batch_id,
        filter_mode=filter_mode,
        limit=limit,
        offset=offset
    )
    return {"predictions": preds, "count": len(preds)}

@router.post("/baseline/batch/{batch_id}/cancel")
async def cancel_batch_run(batch_id: str):
    success = baseline_batch_runner.cancel_batch(batch_id)
    if not success:
        batch = await baseline_batch_runner.get_batch(batch_id)
        if batch and batch["status"] in ["completed", "failed", "canceled", "interrupted"]:
            return {"status": batch["status"], "message": f"Batch already in terminal state '{batch['status']}'."}
        raise HTTPException(status_code=400, detail="Batch is not running or could not be canceled.")
    return {"status": "canceling", "message": "Cancellation request sent to runner."}

def _make_unique_col(base_name: str, existing_names: set) -> str:
    """Generate collision-free column name preserving existing fields."""
    candidate = base_name
    if candidate not in existing_names:
        existing_names.add(candidate)
        return candidate
    candidate = f"eval_{base_name}"
    if candidate not in existing_names:
        existing_names.add(candidate)
        return candidate
    counter = 1
    while f"{candidate}_{counter}" in existing_names:
        counter += 1
    res = f"{candidate}_{counter}"
    existing_names.add(res)
    return res

@router.post("/baseline/batch/{batch_id}/export")
async def export_baseline_csv(batch_id: str):
    batch = await baseline_batch_runner.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    predictions = await baseline_batch_runner.list_batch_predictions(batch_id, filter_mode="all", limit=50000)
    if not predictions:
        raise HTTPException(status_code=400, detail="No predictions available to export.")

    # Determine original columns from recorded rows
    first_orig = predictions[0].get("original_data", {})
    original_cols = list(first_orig.keys())
    allocated_names = set(original_cols)

    # Allocate collision-free column names consistently
    added_cols = {
        "topics": _make_unique_col("baseline_predicted_topics", allocated_names),
        "sentiment": _make_unique_col("baseline_predicted_sentiment", allocated_names),
        "summary": _make_unique_col("baseline_summary", allocated_names),
        "needs_review": _make_unique_col("baseline_needs_review", allocated_names),
        "review_reason": _make_unique_col("baseline_review_reason", allocated_names),
        "schema_valid": _make_unique_col("baseline_schema_valid", allocated_names),
        "status": _make_unique_col("baseline_status", allocated_names),
        "error": _make_unique_col("baseline_error", allocated_names),
        "is_simulated": _make_unique_col("baseline_is_simulated", allocated_names),
        "execution_mode": _make_unique_col("baseline_execution_mode", allocated_names),
        "model_identity": _make_unique_col("baseline_model_identity", allocated_names)
    }

    fieldnames = list(original_cols) + list(added_cols.values())

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()

    for p in predictions:
        row = dict(p.get("original_data", {}))
        topics = p.get("predicted_topics", [])
        row[added_cols["topics"]] = "; ".join(topics) if isinstance(topics, list) else str(topics)
        row[added_cols["sentiment"]] = p.get("predicted_sentiment", "")
        row[added_cols["summary"]] = p.get("generated_summary", "")
        row[added_cols["needs_review"]] = "YES" if p.get("predicted_needs_review") else "NO"
        row[added_cols["review_reason"]] = p.get("review_reason", "")
        row[added_cols["schema_valid"]] = "YES" if p.get("is_valid_schema") else "NO"
        row[added_cols["status"]] = p.get("status", "")
        row[added_cols["error"]] = p.get("error_message") or ""

        # Provenance metadata
        is_sim = p.get("is_simulated")
        if is_sim is None:
            is_sim = (batch.get("app_mode") == "preview")
        row[added_cols["is_simulated"]] = "YES" if is_sim else "NO"
        row[added_cols["execution_mode"]] = p.get("execution_mode") or batch.get("app_mode") or "connected"
        row[added_cols["model_identity"]] = p.get("model_name") or batch.get("model_name") or ""

        writer.writerow(row)

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=baseline_evaluation_{batch_id}.csv"
        }
    )
