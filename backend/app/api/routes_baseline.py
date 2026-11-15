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

            if ds.get("project_id") != req.project_id:
                raise HTTPException(
                    status_code=404,
                    detail=f"Dataset '{req.dataset_id}' does not belong to project '{req.project_id}'."
                )

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

    # Validate required response column (with whitespace tolerance for column matching)
    available_cols = list(rows_to_process[0].keys())
    col_map = {c.strip(): c for c in available_cols}

    def resolve_col_name(c: Optional[str]) -> Optional[str]:
        if not c:
            return c
        if c in available_cols:
            return c
        if c.strip() in col_map:
            return col_map[c.strip()]
        return c

    actual_response_col = resolve_col_name(req.response_col)
    if not actual_response_col or actual_response_col not in available_cols:
        raise HTTPException(
            status_code=400,
            detail=f"Required response column '{req.response_col}' not found in dataset. Available columns: {available_cols}"
        )

    actual_id_col = resolve_col_name(req.id_col)
    actual_label_topics_col = resolve_col_name(req.label_topics_col)
    actual_label_sentiment_col = resolve_col_name(req.label_sentiment_col)
    actual_label_needs_review_col = resolve_col_name(req.label_needs_review_col)

    batch = await baseline_batch_runner.create_and_start_batch(
        project_id=req.project_id,
        dataset_id=req.dataset_id or "inline_rows",
        rows=rows_to_process,
        response_col=actual_response_col,
        id_col=actual_id_col,
        label_topics_col=actual_label_topics_col,
        label_sentiment_col=actual_label_sentiment_col,
        label_needs_review_col=actual_label_needs_review_col,
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

    # Determine all original columns from recorded rows (preserving header order)
    original_cols = []
    seen_cols = set()
    for p in predictions:
        for k in p.get("original_data", {}).keys():
            if k not in seen_cols:
                seen_cols.add(k)
                original_cols.append(k)
    allocated_names = set(original_cols)

    # Allocate collision-free column names consistently
    added_cols = {
        "topics": _make_unique_col("baseline_predicted_topics", allocated_names),
        "topics_valid": _make_unique_col("baseline_topics_valid", allocated_names),
        "sentiment": _make_unique_col("baseline_predicted_sentiment", allocated_names),
        "sentiment_valid": _make_unique_col("baseline_sentiment_valid", allocated_names),
        "summary": _make_unique_col("baseline_summary", allocated_names),
        "needs_review": _make_unique_col("baseline_needs_review", allocated_names),
        "needs_review_valid": _make_unique_col("baseline_needs_review_valid", allocated_names),
        "review_reason": _make_unique_col("baseline_review_reason", allocated_names),
        "schema_valid": _make_unique_col("baseline_schema_valid", allocated_names),
        "validation_details": _make_unique_col("baseline_validation_details", allocated_names),
        "status": _make_unique_col("baseline_status", allocated_names),
        "error": _make_unique_col("baseline_error", allocated_names),
        "is_simulated": _make_unique_col("baseline_is_simulated", allocated_names),
        "execution_mode": _make_unique_col("baseline_execution_mode", allocated_names),
        "model_identity": _make_unique_col("baseline_model_identity", allocated_names),
        "source_batch": _make_unique_col("baseline_source_batch", allocated_names),
        "analysis_id": _make_unique_col("baseline_analysis_id", allocated_names),
        "evaluation_role": _make_unique_col("baseline_evaluation_role", allocated_names)
    }

    fieldnames = list(original_cols) + list(added_cols.values())

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()

    for p in predictions:
        row = dict(p.get("original_data", {}))

        # Output validity vs unavailable
        topics_valid = bool(p.get("topics_valid"))
        sentiment_valid = bool(p.get("sentiment_valid"))
        needs_review_valid = bool(p.get("needs_review_valid"))

        # Topics: show valid topics or [unavailable]
        if topics_valid:
            topics = p.get("predicted_topics", [])
            row[added_cols["topics"]] = "; ".join(topics) if isinstance(topics, list) else str(topics)
        else:
            row[added_cols["topics"]] = "[unavailable]"

        row[added_cols["topics_valid"]] = "YES" if topics_valid else "NO"

        # Sentiment: show valid sentiment or [unavailable]
        if sentiment_valid:
            row[added_cols["sentiment"]] = p.get("predicted_sentiment", "")
        else:
            row[added_cols["sentiment"]] = "[unavailable]"

        row[added_cols["sentiment_valid"]] = "YES" if sentiment_valid else "NO"

        row[added_cols["summary"]] = p.get("generated_summary", "")

        # Needs review: show valid YES/NO or [unavailable]
        if needs_review_valid:
            row[added_cols["needs_review"]] = "YES" if p.get("predicted_needs_review") else "NO"
        else:
            row[added_cols["needs_review"]] = "[unavailable]"

        row[added_cols["needs_review_valid"]] = "YES" if needs_review_valid else "NO"

        row[added_cols["review_reason"]] = p.get("review_reason", "")
        row[added_cols["schema_valid"]] = "YES" if p.get("is_valid_schema") else "NO"

        # Validation details and error explanation
        schema_errs = p.get("schema_errors", [])
        val_details = "; ".join(schema_errs) if isinstance(schema_errs, list) else str(schema_errs)
        row[added_cols["validation_details"]] = val_details

        # Transport/inference status preserved distinctly
        row[added_cols["status"]] = p.get("status", "")

        err_msg = p.get("error_message") or ""
        if not err_msg and not p.get("is_valid_schema") and val_details:
            err_msg = f"Schema validation failed: {val_details}"
        row[added_cols["error"]] = err_msg

        # Provenance metadata
        is_sim = p.get("is_simulated")
        if is_sim is None:
            is_sim = (batch.get("app_mode") == "preview")
        row[added_cols["is_simulated"]] = "YES" if is_sim else "NO"
        row[added_cols["execution_mode"]] = p.get("execution_mode") or batch.get("app_mode") or "connected"
        row[added_cols["model_identity"]] = p.get("model_name") or batch.get("model_name") or ""
        row[added_cols['source_batch']] = batch['snapshot'].get('source_batch_id', '')
        row[added_cols['analysis_id']] = batch['snapshot'].get('analysis_id', '')
        row[added_cols['evaluation_role']] = batch['snapshot'].get('evaluation_role', 'original_baseline')

        writer.writerow(row)

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=baseline_evaluation_{batch_id}.csv"
        }
    )
