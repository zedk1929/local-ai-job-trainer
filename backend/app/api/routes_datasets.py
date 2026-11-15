import csv
import io
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional, Set, Tuple
from app.config import settings
from app.services.run_store import run_store
from app.services.supervisor_client import SupervisorClient
from app.services.label_parser import (
    parse_ground_truth_topics,
    parse_ground_truth_sentiment,
    parse_ground_truth_needs_review,
    is_blank_response
)

router = APIRouter()

class SyntheticGenerateRequest(BaseModel):
    project_id: str
    count: int = 6
    explicit_consent_upload_real_data: bool = False

class ConfirmDatasetRequest(BaseModel):
    project_id: str
    temp_file_id: str
    filename: str
    response_col: str
    id_col: Optional[str] = ""
    label_topics_col: Optional[str] = ""
    label_sentiment_col: Optional[str] = ""
    label_needs_review_col: Optional[str] = ""
    is_sample: Optional[bool] = False

def parse_and_validate_csv_text(text: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Parse CSV text preserving quotes, commas, multiline responses, and IDs.
    Returns: (clean_headers, rows)
    Raises HTTPException(400) on empty files, missing/duplicate headers, or malformed rows.
    """
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")

    if text.startswith("\ufeff"):
        text = text[1:]

    reader = csv.reader(io.StringIO(text), strict=True)
    try:
        header_row = next(reader)
    except StopIteration:
        raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")
    except csv.Error as e:
        raise HTTPException(
            status_code=400,
            detail=f"Malformed CSV formatting in header: {e}."
        )

    if not header_row or all(c.strip() == "" for c in header_row):
        raise HTTPException(status_code=400, detail="CSV header row is missing or empty.")

    clean_headers = []
    seen = set()
    duplicates = []
    for idx, col in enumerate(header_row):
        c = col.strip()
        if not c:
            raise HTTPException(status_code=400, detail=f"CSV contains empty column header at column {idx + 1}.")
        if c in seen:
            duplicates.append(c)
        seen.add(c)
        clean_headers.append(c)

    if duplicates:
        raise HTTPException(
            status_code=400,
            detail=f"CSV contains duplicate column headers: {', '.join(duplicates)}."
        )

    num_cols = len(clean_headers)
    rows = []
    try:
        for r in reader:
            if not r or (len(r) == 1 and r[0].strip() == ""):
                # Skip empty trailing line
                continue
            if len(r) != num_cols:
                raise HTTPException(
                    status_code=400,
                    detail=f"Malformed row at line {reader.line_num}: expected {num_cols} columns but found {len(r)}."
                )
            rows.append(dict(zip(clean_headers, r)))
    except csv.Error as e:
        raise HTTPException(
            status_code=400,
            detail=f"Malformed CSV quoting or formatting at line {reader.line_num}: {e}."
        )

    if not rows:
        raise HTTPException(status_code=400, detail="CSV contains headers but no data rows.")

    return clean_headers, rows

def suggest_column_mappings(columns: List[str]) -> Dict[str, str]:
    """
    Suggest default column mappings without assuming café-specific column names.
    """
    lower_map = {c.lower(): c for c in columns}

    # 1. Response column:
    response_col = ""
    for candidate in ["response", "feedback", "comment", "feedback_text", "text", "review", "user_comment", "survey_response", "input", "body", "message"]:
        if candidate in lower_map:
            response_col = lower_map[candidate]
            break
    if not response_col:
        for c in columns:
            cl = c.lower()
            if any(k in cl for k in ["comment", "response", "feedback", "text", "review"]):
                response_col = c
                break
    if not response_col and columns:
        response_col = columns[0]

    # 2. ID column:
    id_col = ""
    for candidate in ["id", "response_id", "row_id", "uid", "item_id", "id_col"]:
        if candidate in lower_map:
            id_col = lower_map[candidate]
            break
    if not id_col:
        for c in columns:
            cl = c.lower()
            if cl in ["id", "key"] or cl.endswith("_id") or cl.startswith("id_"):
                id_col = c
                break

    # 3. Topics column:
    topics_col = ""
    for candidate in ["topics", "label_topics", "categories", "category", "labels", "topic", "tags"]:
        if candidate in lower_map:
            topics_col = lower_map[candidate]
            break

    # 4. Sentiment column:
    sentiment_col = ""
    for candidate in ["sentiment", "label_sentiment", "polarity", "mood"]:
        if candidate in lower_map:
            sentiment_col = lower_map[candidate]
            break

    # 5. Needs review column:
    review_col = ""
    for candidate in ["needs_review", "label_needs_review", "review", "flag", "flagged"]:
        if candidate in lower_map:
            review_col = lower_map[candidate]
            break

    return {
        "response_col": response_col,
        "id_col": id_col,
        "label_topics_col": topics_col,
        "label_sentiment_col": sentiment_col,
        "label_needs_review_col": review_col
    }

def compute_validation_summary(
    rows: List[Dict[str, Any]],
    fieldnames: List[str],
    response_col: str,
    id_col: Optional[str],
    label_topics_col: Optional[str],
    label_sentiment_col: Optional[str],
    label_needs_review_col: Optional[str],
    valid_taxonomy_ids: Set[str]
) -> Dict[str, Any]:
    blank_responses = 0
    valid_responses = 0

    topics_valid_labeled_count = 0
    topics_valid_empty_count = 0
    topics_invalid_count = 0
    topics_missing_count = 0
    topic_row_errors = []
    all_unrecognized_topics = set()

    sentiment_valid_count = 0
    sentiment_invalid_count = 0
    sentiment_missing_count = 0
    sentiment_row_errors = []

    review_flag_valid_count = 0
    review_flag_invalid_count = 0
    review_flag_missing_count = 0
    review_flag_row_errors = []

    for idx, r in enumerate(rows, start=1):
        resp_id = str(r.get(id_col, f"row_{idx}")) if id_col else f"row_{idx}"
        resp_text = r.get(response_col, "")
        if is_blank_response(resp_text):
            blank_responses += 1
        else:
            valid_responses += 1

        if label_topics_col and label_topics_col in r:
            raw_t = r.get(label_topics_col)
            res_t = parse_ground_truth_topics(raw_t, valid_taxonomy_ids)
            if not res_t.is_present:
                topics_missing_count += 1
            elif res_t.is_valid:
                if res_t.value == []:
                    topics_valid_empty_count += 1
                else:
                    topics_valid_labeled_count += 1
            else:
                topics_invalid_count += 1
                if res_t.error:
                    all_unrecognized_topics.add(res_t.error)
                    topic_row_errors.append({
                        "row_idx": idx,
                        "response_id": resp_id,
                        "raw_value": str(raw_t),
                        "error": res_t.error
                    })
        elif label_topics_col:
            topics_missing_count += 1

        if label_sentiment_col and label_sentiment_col in r:
            raw_s = r.get(label_sentiment_col)
            res_s = parse_ground_truth_sentiment(raw_s)
            if not res_s.is_present:
                sentiment_missing_count += 1
            elif res_s.is_valid:
                sentiment_valid_count += 1
            else:
                sentiment_invalid_count += 1
                if res_s.error:
                    sentiment_row_errors.append({
                        "row_idx": idx,
                        "response_id": resp_id,
                        "raw_value": str(raw_s),
                        "error": res_s.error
                    })
        elif label_sentiment_col:
            sentiment_missing_count += 1

        if label_needs_review_col and label_needs_review_col in r:
            raw_rf = r.get(label_needs_review_col)
            res_rf = parse_ground_truth_needs_review(raw_rf)
            if not res_rf.is_present:
                review_flag_missing_count += 1
            elif res_rf.is_valid:
                review_flag_valid_count += 1
            else:
                review_flag_invalid_count += 1
                if res_rf.error:
                    review_flag_row_errors.append({
                        "row_idx": idx,
                        "response_id": resp_id,
                        "raw_value": str(raw_rf),
                        "error": res_rf.error
                    })
        elif label_needs_review_col:
            review_flag_missing_count += 1

    return {
        "total_rows": len(rows),
        "valid_response_rows": valid_responses,
        "blank_response_rows": blank_responses,

        "has_topics_label": bool(label_topics_col and label_topics_col in fieldnames),
        "topics_labeled_rows": topics_valid_labeled_count + topics_valid_empty_count,
        "topics_valid_empty_rows": topics_valid_empty_count,
        "topics_invalid_rows": topics_invalid_count,
        "topics_missing_rows": topics_missing_count,
        "topic_errors": topic_row_errors[:10],
        "unrecognized_topic_tokens": list(all_unrecognized_topics),

        "has_sentiment_label": bool(label_sentiment_col and label_sentiment_col in fieldnames),
        "sentiment_labeled_rows": sentiment_valid_count,
        "sentiment_invalid_rows": sentiment_invalid_count,
        "sentiment_missing_rows": sentiment_missing_count,
        "sentiment_errors": sentiment_row_errors[:10],

        "has_needs_review_label": bool(label_needs_review_col and label_needs_review_col in fieldnames),
        "needs_review_labeled_rows": review_flag_valid_count,
        "needs_review_invalid_rows": review_flag_invalid_count,
        "needs_review_missing_rows": review_flag_missing_count,
        "needs_review_errors": review_flag_row_errors[:10],

        "is_unlabeled": not (
            (topics_valid_labeled_count + topics_valid_empty_count > 0) or
            (sentiment_valid_count > 0) or
            (review_flag_valid_count > 0)
        )
    }

@router.post("/datasets/inspect")
async def inspect_dataset_csv(
    file: Optional[UploadFile] = File(None),
    source: Optional[str] = Form(None)
):
    """
    Stage 1: Inspect the file without requiring column mappings or altering project state.
    Parses headers, validates CSV formatting, checks UTF-8 BOM, and returns a preview.
    """
    if source in ("sample", "sample_cafe_labeled", "dev_60", "sample_dev_60", "dev_survey_60"):
        is_dev_60 = source in ("dev_60", "sample_dev_60", "dev_survey_60")
        sample_path = settings.dev_sample_csv_path if is_dev_60 else settings.sample_csv_path
        default_filename = "dev_survey_60_labeled.csv" if is_dev_60 else "sample_survey_labeled.csv"
        temp_id = "sample_dev_60" if is_dev_60 else "sample_cafe_labeled"

        if not sample_path.exists():
            sample_path = Path(__file__).resolve().parent.parent.parent / "data" / default_filename
        try:
            with open(sample_path, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(sample_path, "r", encoding="latin-1") as f:
                text = f.read()

        clean_headers, rows = parse_and_validate_csv_text(text)
        suggested = suggest_column_mappings(clean_headers)
        return {
            "temp_file_id": temp_id,
            "filename": default_filename,
            "is_sample": True,
            "columns": clean_headers,
            "row_count": len(rows),
            "preview_rows": rows[:5],
            "suggested_mappings": suggested
        }

    if not file:
        raise HTTPException(status_code=400, detail="No CSV file or source provided.")

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    content_bytes = await file.read()
    try:
        text = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content_bytes.decode("latin-1")

    clean_headers, rows = parse_and_validate_csv_text(text)

    # Stage raw text without modifying project or existing datasets
    temp_file_id = f"stage_{uuid.uuid4().hex}"
    staging_dir = settings.uploads_dir / "_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_file = staging_dir / f"{temp_file_id}.csv"
    with open(staging_file, "w", encoding="utf-8") as f:
        f.write(text)

    suggested = suggest_column_mappings(clean_headers)
    return {
        "temp_file_id": temp_file_id,
        "filename": file.filename,
        "is_sample": False,
        "columns": clean_headers,
        "row_count": len(rows),
        "preview_rows": rows[:5],
        "suggested_mappings": suggested
    }

@router.post("/datasets/confirm")
async def confirm_dataset(req: ConfirmDatasetRequest):
    """
    Stage 2: Map and confirm the dataset.
    Validates column mappings, saves dataset with unique internal filename,
    persists selections to the project, and computes validation metrics.
    Preserves staged upload and project state if validation or persistence fails.
    """
    proj = await run_store.get_project(req.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    is_sample = bool(req.is_sample or (req.temp_file_id in ("sample_cafe_labeled", "sample_dev_60")))
    staging_file = None
    if is_sample:
        is_dev_60 = req.temp_file_id == "sample_dev_60"
        sample_path = settings.dev_sample_csv_path if is_dev_60 else settings.sample_csv_path
        default_filename = "dev_survey_60_labeled.csv" if is_dev_60 else "sample_survey_labeled.csv"
        if not sample_path.exists():
            sample_path = Path(__file__).resolve().parent.parent.parent / "data" / default_filename
        try:
            with open(sample_path, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(sample_path, "r", encoding="latin-1") as f:
                text = f.read()

        clean_headers, rows = parse_and_validate_csv_text(text)
        dest_filepath = str(sample_path)
        origin = "bundled-dev-sample" if is_dev_60 else "bundled-sample"
    else:
        staging_dir = settings.uploads_dir / "_staging"
        staging_file = staging_dir / f"{req.temp_file_id}.csv"
        if not staging_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Staged upload expired or not found. Please re-upload the CSV file."
            )
        try:
            with open(staging_file, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(staging_file, "r", encoding="latin-1") as f:
                text = f.read()

        clean_headers, rows = parse_and_validate_csv_text(text)
        origin = "human-uploaded"

    # Validate column mappings against actual headers BEFORE consuming staged upload
    if not req.response_col or req.response_col.strip() == "":
        raise HTTPException(status_code=400, detail="Response column is required.")
    if req.response_col not in clean_headers:
        raise HTTPException(
            status_code=400,
            detail=f"Selected response column '{req.response_col}' not found in CSV. Available columns: {clean_headers}"
        )
    if req.id_col and req.id_col not in clean_headers:
        raise HTTPException(status_code=400, detail=f"Selected ID column '{req.id_col}' not found in CSV.")
    if req.label_topics_col and req.label_topics_col not in clean_headers:
        raise HTTPException(status_code=400, detail=f"Selected topics label column '{req.label_topics_col}' not found in CSV.")
    if req.label_sentiment_col and req.label_sentiment_col not in clean_headers:
        raise HTTPException(status_code=400, detail=f"Selected sentiment label column '{req.label_sentiment_col}' not found in CSV.")
    if req.label_needs_review_col and req.label_needs_review_col not in clean_headers:
        raise HTTPException(status_code=400, detail=f"Selected needs-review label column '{req.label_needs_review_col}' not found in CSV.")

    # Validation against project taxonomy
    valid_taxonomy_ids = {t["id"] for t in proj.get("taxonomy", [])}

    validation_summary = compute_validation_summary(
        rows=rows,
        fieldnames=clean_headers,
        response_col=req.response_col,
        id_col=req.id_col,
        label_topics_col=req.label_topics_col,
        label_sentiment_col=req.label_sentiment_col,
        label_needs_review_col=req.label_needs_review_col,
        valid_taxonomy_ids=valid_taxonomy_ids
    )

    dest_path = None
    if not is_sample:
        # Store with collision-free unique internal filename
        safe_name = Path(req.filename).name.replace(" ", "_")
        unique_prefix = uuid.uuid4().hex[:8]
        unique_filename = f"{unique_prefix}_{safe_name}"
        proj_dir = settings.uploads_dir / req.project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        dest_path = proj_dir / unique_filename
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(text)
        dest_filepath = str(dest_path)

    saved_dataset_id = None
    try:
        dataset_record = await run_store.save_dataset(
            project_id=req.project_id,
            filename=req.filename,
            filepath=dest_filepath,
            row_count=len(rows),
            response_col=req.response_col,
            id_col=req.id_col or "",
            label_topics_col=req.label_topics_col or "",
            label_sentiment_col=req.label_sentiment_col or "",
            label_needs_review_col=req.label_needs_review_col or "",
            origin=origin
        )
        saved_dataset_id = dataset_record["id"]

        # Update project with confirmed dataset and column mappings
        await run_store.update_project(
            project_id=req.project_id,
            selected_dataset_id=dataset_record["id"],
            response_col=req.response_col,
            id_col=req.id_col or "",
            label_topics_col=req.label_topics_col or "",
            label_sentiment_col=req.label_sentiment_col or "",
            label_needs_review_col=req.label_needs_review_col or ""
        )
    except Exception as exc:
        if dest_path and dest_path.exists():
            try:
                dest_path.unlink()
            except Exception:
                pass
        if saved_dataset_id:
            try:
                await run_store.delete_dataset(saved_dataset_id)
            except Exception:
                pass
        raise HTTPException(
            status_code=500,
            detail=f"Failed to persist dataset confirmation: {str(exc)}"
        )

    # Consume (unlink) staged file only after validation and persistence have succeeded
    if staging_file and staging_file.exists():
        try:
            staging_file.unlink()
        except Exception:
            pass

    return {
        "dataset": dataset_record,
        "columns": clean_headers,
        "row_count": len(rows),
        "preview_rows": rows[:5],
        "validation_summary": validation_summary
    }

@router.post("/datasets/upload")
async def upload_dataset_csv(
    project_id: str = Form(...),
    response_col: str = Form(...),
    id_col: Optional[str] = Form(""),
    label_topics_col: Optional[str] = Form(""),
    label_sentiment_col: Optional[str] = Form(""),
    label_needs_review_col: Optional[str] = Form(""),
    file: UploadFile = File(...)
):
    """
    Direct single-step upload endpoint for backwards compatibility and automated scripts.
    Saves with unique internal filename to prevent name collisions.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    proj = await run_store.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    content_bytes = await file.read()
    try:
        text = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content_bytes.decode("latin-1")

    clean_headers, rows = parse_and_validate_csv_text(text)

    if response_col not in clean_headers:
        raise HTTPException(
            status_code=400,
            detail=f"Selected response column '{response_col}' not found in CSV. Available columns: {clean_headers}"
        )
    if id_col and id_col not in clean_headers:
        raise HTTPException(status_code=400, detail=f"Selected ID column '{id_col}' not found in CSV.")
    if label_topics_col and label_topics_col not in clean_headers:
        raise HTTPException(status_code=400, detail=f"Selected topics label column '{label_topics_col}' not found in CSV.")
    if label_sentiment_col and label_sentiment_col not in clean_headers:
        raise HTTPException(status_code=400, detail=f"Selected sentiment label column '{label_sentiment_col}' not found in CSV.")
    if label_needs_review_col and label_needs_review_col not in clean_headers:
        raise HTTPException(status_code=400, detail=f"Selected needs-review label column '{label_needs_review_col}' not found in CSV.")

    # Unique collision-free internal filename
    safe_name = Path(file.filename).name.replace(" ", "_")
    unique_prefix = uuid.uuid4().hex[:8]
    unique_filename = f"{unique_prefix}_{safe_name}"
    proj_dir = settings.uploads_dir / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    dest_path = proj_dir / unique_filename
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(text)

    valid_taxonomy_ids = {t["id"] for t in proj.get("taxonomy", [])}
    validation_summary = compute_validation_summary(
        rows=rows,
        fieldnames=clean_headers,
        response_col=response_col,
        id_col=id_col,
        label_topics_col=label_topics_col,
        label_sentiment_col=label_sentiment_col,
        label_needs_review_col=label_needs_review_col,
        valid_taxonomy_ids=valid_taxonomy_ids
    )

    saved_dataset_id = None
    try:
        dataset_record = await run_store.save_dataset(
            project_id=project_id,
            filename=file.filename,
            filepath=str(dest_path),
            row_count=len(rows),
            response_col=response_col,
            id_col=id_col or "",
            label_topics_col=label_topics_col or "",
            label_sentiment_col=label_sentiment_col or "",
            label_needs_review_col=label_needs_review_col or "",
            origin="human-uploaded"
        )
        saved_dataset_id = dataset_record["id"]

        await run_store.update_project(
            project_id=project_id,
            selected_dataset_id=dataset_record["id"],
            response_col=response_col,
            id_col=id_col or "",
            label_topics_col=label_topics_col or "",
            label_sentiment_col=label_sentiment_col or "",
            label_needs_review_col=label_needs_review_col or ""
        )
    except Exception as exc:
        if dest_path.exists():
            try:
                dest_path.unlink()
            except Exception:
                pass
        if saved_dataset_id:
            try:
                await run_store.delete_dataset(saved_dataset_id)
            except Exception:
                pass
        raise HTTPException(
            status_code=500,
            detail=f"Failed to persist dataset upload: {str(exc)}"
        )

    return {
        "dataset": dataset_record,
        "columns": clean_headers,
        "row_count": len(rows),
        "preview_rows": rows[:5],
        "validation_summary": validation_summary
    }

@router.get("/datasets/{project_id}")
async def get_datasets_for_project(project_id: str):
    datasets = await run_store.list_datasets(project_id)
    return {"datasets": datasets}

@router.get("/datasets/{project_id}/{dataset_id}/preview")
async def preview_dataset(project_id: str, dataset_id: str, limit: int = 5):
    if dataset_id in ("sample_cafe_labeled", "sample_dev_60"):
        is_dev_60 = dataset_id == "sample_dev_60"
        sample_path = settings.dev_sample_csv_path if is_dev_60 else settings.sample_csv_path
        default_filename = "dev_survey_60_labeled.csv" if is_dev_60 else "sample_survey_labeled.csv"
        if not sample_path.exists():
            sample_path = Path(__file__).resolve().parent.parent.parent / "data" / default_filename
        rows = []
        with open(sample_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for r in reader:
                rows.append(r)
        return {
            "columns": fieldnames,
            "row_count": len(rows),
            "preview_rows": rows[:limit]
        }

    ds = await run_store.get_dataset(dataset_id)
    if not ds or ds["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Dataset not found")

    filepath = ds["filepath"]
    rows = []
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for r in reader:
                rows.append(r)
    except UnicodeDecodeError:
        with open(filepath, "r", encoding="latin-1") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for r in reader:
                rows.append(r)

    return {
        "columns": fieldnames,
        "row_count": len(rows),
        "preview_rows": rows[:limit]
    }

@router.post("/datasets/synthetic-generate")
async def generate_synthetic_examples(req: SyntheticGenerateRequest):
    proj = await run_store.get_project(req.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    client = SupervisorClient()
    examples = await client.generate_synthetic_examples(
        context=proj["survey_context"],
        taxonomy=proj["taxonomy"],
        rules=proj["coding_rules"],
        count=req.count
    )

    return {
        "project_id": req.project_id,
        "count": len(examples),
        "examples": examples,
        "is_simulated_fixture": any(e.get("is_simulated_fixture", False) for e in examples)
    }
