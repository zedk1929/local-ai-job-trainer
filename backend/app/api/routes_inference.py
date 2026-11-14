import csv
import io
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from app.config import settings
from app.services.run_store import run_store
from app.services.model_backend import LocalModelBackend
from app.core.registry import registry

router = APIRouter()

class SingleInferRequest(BaseModel):
    project_id: str
    response_text: str
    use_adapter: bool = False

class BatchInferRequest(BaseModel):
    project_id: str
    items: List[Dict[str, Any]]
    response_col: str
    id_col: Optional[str] = None
    use_adapter: bool = False

class ExportCsvRequest(BaseModel):
    project_id: str
    processed_rows: List[Dict[str, Any]]
    original_columns: List[str]

@router.post("/specialist/infer-single")
async def infer_single_response(req: SingleInferRequest):
    proj = await run_store.get_project(req.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    job = registry.get(proj["job_id"])
    model_backend = LocalModelBackend()

    # In connected mode, adapter training is not implemented yet; always original model - no adapter
    effective_use_adapter = req.use_adapter if settings.app_mode == "preview" else False

    result = await model_backend.infer_single(
        response_text=req.response_text,
        context=proj["survey_context"],
        taxonomy=proj["taxonomy"],
        rules=proj["coding_rules"],
        use_adapter=effective_use_adapter
    )

    if job:
        validated = job.validate_output(result, proj["taxonomy"])
        result.update(validated)

    return {
        "result": result,
        "job_version": job.version if job else "1.0.0",
        "active_adapter": None if not effective_use_adapter else "survey-cleaner-lora-v1",
        "adapter_note": "Original model — no adapter" if not effective_use_adapter else "Simulated LoRA preview"
    }

@router.post("/specialist/infer-batch")
async def infer_batch_responses(req: BatchInferRequest):
    proj = await run_store.get_project(req.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    job = registry.get(proj["job_id"])
    model_backend = LocalModelBackend()
    effective_use_adapter = req.use_adapter if settings.app_mode == "preview" else False

    processed = []
    for item in req.items:
        text = item.get(req.response_col, "")
        pred = await model_backend.infer_single(
            response_text=text,
            context=proj["survey_context"],
            taxonomy=proj["taxonomy"],
            rules=proj["coding_rules"],
            use_adapter=effective_use_adapter
        )
        if job:
            pred.update(job.validate_output(pred, proj["taxonomy"]))

        merged_row = {**item}
        topics = pred.get("topics", [])
        merged_row["predicted_topics"] = "; ".join(topics) if isinstance(topics, list) else str(topics)
        merged_row["predicted_sentiment"] = pred.get("sentiment", "neutral")
        merged_row["generated_summary"] = pred.get("summary", "")
        merged_row["needs_review"] = "YES" if pred.get("needs_review") else "NO"
        merged_row["review_reason"] = pred.get("review_reason") or ""
        processed.append(merged_row)

    return {
        "processed_rows": processed,
        "count": len(processed),
        "job_version": job.version if job else "1.0.0",
        "model_used": model_backend.model_name or "local-model",
        "active_adapter": None if not effective_use_adapter else "survey-cleaner-lora-v1",
        "adapter_note": "Original model — no adapter" if not effective_use_adapter else "Simulated LoRA preview"
    }

@router.post("/specialist/export-csv")
async def export_cleaned_csv(req: ExportCsvRequest):
    proj = await run_store.get_project(req.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    output = io.StringIO()
    added_columns = [
        "predicted_topics",
        "predicted_sentiment",
        "generated_summary",
        "needs_review",
        "review_reason"
    ]

    all_fieldnames = list(req.original_columns)
    for col in added_columns:
        if col not in all_fieldnames:
            all_fieldnames.append(col)

    writer = csv.DictWriter(
        output,
        fieldnames=all_fieldnames,
        quoting=csv.QUOTE_MINIMAL,
        extrasaction="ignore"
    )
    writer.writeheader()

    for row in req.processed_rows:
        writer.writerow(row)

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=cleaned_survey_project_{req.project_id}.csv"
        }
    )
