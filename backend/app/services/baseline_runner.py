import asyncio
import time
import json
import csv
import logging
import uuid
import aiosqlite
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.config import settings
from app.database import get_now_iso
from app.services.model_backend import LocalModelBackend, ModelServiceError, ModelNotFoundError
from app.services.label_parser import (
    parse_ground_truth_topics,
    parse_ground_truth_sentiment,
    parse_ground_truth_needs_review,
    is_blank_response
)
from app.services.evaluator import evaluate_baseline_batch
from app.jobs.survey_cleaner import survey_cleaner_job

logger = logging.getLogger(__name__)

class BaselineBatchRunner:
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.cancel_flags: Dict[str, bool] = {}

    def is_running(self, batch_id: str) -> bool:
        return batch_id in self.active_tasks and not self.active_tasks[batch_id].done()

    def cancel_batch(self, batch_id: str) -> bool:
        if batch_id in self.active_tasks:
            self.cancel_flags[batch_id] = True
            self.active_tasks[batch_id].cancel()
            logger.info(f"Cancellation requested for baseline batch {batch_id}")
            return True
        return False

    async def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM baseline_batches WHERE id = ?", (batch_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            data["snapshot"] = json.loads(data["snapshot"]) if data["snapshot"] else {}
            data["metrics"] = json.loads(data["metrics"]) if data["metrics"] else None
            return data

    async def get_latest_batch_for_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM baseline_batches WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            data["snapshot"] = json.loads(data["snapshot"]) if data["snapshot"] else {}
            data["metrics"] = json.loads(data["metrics"]) if data["metrics"] else None
            return data

    async def list_batch_predictions(
        self,
        batch_id: str,
        filter_mode: str = "all",
        limit: int = 500,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM baseline_predictions WHERE batch_id = ? ORDER BY row_index ASC"
            cursor = await db.execute(query, (batch_id,))
            rows = await cursor.fetchall()

            results = []
            for r in rows:
                item = dict(r)
                item["original_data"] = json.loads(item["original_data"])
                item["ground_truth_topics"] = json.loads(item["ground_truth_topics"]) if item["ground_truth_topics"] else None
                item["ground_truth_label_errors"] = json.loads(item["ground_truth_label_errors"]) if item.get("ground_truth_label_errors") else []
                item["raw_model_output"] = json.loads(item["raw_model_output"]) if item.get("raw_model_output") else None
                item["predicted_topics"] = json.loads(item["predicted_topics"]) if item["predicted_topics"] else []
                item["schema_errors"] = json.loads(item["schema_errors"]) if item["schema_errors"] else []
                item["is_valid_schema"] = bool(item["is_valid_schema"])
                item["topics_valid"] = bool(item.get("topics_valid", 0))
                item["sentiment_valid"] = bool(item.get("sentiment_valid", 0))
                item["needs_review_valid"] = bool(item.get("needs_review_valid", 0))
                item["predicted_needs_review"] = bool(item["predicted_needs_review"])
                item["ground_truth_needs_review"] = (
                    bool(item["ground_truth_needs_review"])
                    if item["ground_truth_needs_review"] is not None
                    else None
                )
                item["raw_model_text"] = item.get("raw_model_text")
                item["is_simulated"] = bool(item.get("is_simulated", 0))
                item["model_name"] = item.get("model_name", "")

                # Filter matching
                if filter_mode == "errors":
                    if item["status"] != "error" and item["is_valid_schema"]:
                        continue
                elif filter_mode == "flagged" and not item["predicted_needs_review"]:
                    continue
                elif filter_mode == "mistakes":
                    # Mismatch on any available label or invalid prediction on labeled field
                    has_mismatch = False
                    if item["status"] == "error" or not item["is_valid_schema"]:
                        has_mismatch = True
                    if item["ground_truth_topics"] is not None:
                        if item.get("topics_valid") == 0 or set(item["predicted_topics"]) != set(item["ground_truth_topics"]):
                            has_mismatch = True
                    if item["ground_truth_sentiment"] is not None:
                        if item.get("sentiment_valid") == 0 or str(item["predicted_sentiment"]).lower() != str(item["ground_truth_sentiment"]).lower():
                            has_mismatch = True
                    if item["ground_truth_needs_review"] is not None:
                        if item.get("needs_review_valid") == 0 or bool(item["predicted_needs_review"]) != bool(item["ground_truth_needs_review"]):
                            has_mismatch = True
                    if not has_mismatch:
                        continue

                results.append(item)

            return results[offset : offset + limit]

    async def create_and_start_batch(
        self,
        project_id: str,
        dataset_id: str,
        rows: List[Dict[str, Any]],
        response_col: str,
        id_col: Optional[str] = None,
        label_topics_col: Optional[str] = None,
        label_sentiment_col: Optional[str] = None,
        label_needs_review_col: Optional[str] = None,
        concurrency: int = 1,
        retried_from_batch_id: Optional[str] = None,
        execution_snapshot: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Initialize batch in SQLite and trigger background asynchronous runner."""
        batch_id = f"batch_{uuid.uuid4().hex}"
        now = get_now_iso()

        # Fetch project for snapshotting
        from app.services.run_store import run_store
        proj = await run_store.get_project(project_id)
        if not proj:
            raise ValueError(f"Project '{project_id}' not found.")

        if execution_snapshot is not None:
            # Internal comparison runs use source configuration, never mutate the project.
            proj = {**proj, **{k: execution_snapshot[k] for k in
                    ('survey_context', 'taxonomy', 'coding_rules') if k in execution_snapshot}}

        frozen_app_mode = settings.app_mode
        frozen_model_name = settings.local_model_name or "qwen2.5-coder:3b"
        frozen_endpoint = settings.local_model_endpoint or "http://127.0.0.1:11434"
        if execution_snapshot is not None:
            frozen_app_mode = execution_snapshot['app_mode']
            frozen_model_name = execution_snapshot['model_name']
            frozen_endpoint = execution_snapshot['model_endpoint']

        model_backend = LocalModelBackend(
            endpoint_url=frozen_endpoint,
            model_name=frozen_model_name,
            app_mode=frozen_app_mode
        )

        snapshot = {
            "project_id": project_id,
            "project_name": proj["name"],
            "job_id": proj["job_id"],
            "job_version": survey_cleaner_job.version,
            "survey_context": proj["survey_context"],
            "taxonomy": proj["taxonomy"],
            "coding_rules": proj["coding_rules"],
            "model_name": frozen_model_name,
            "model_endpoint": frozen_endpoint,
            "app_mode": frozen_app_mode,
            "retried_from_batch_id": retried_from_batch_id,
            "concurrency": concurrency,
            "response_col": response_col,
            "id_col": id_col or "",
            "label_topics_col": label_topics_col or "",
            "label_sentiment_col": label_sentiment_col or "",
            "label_needs_review_col": label_needs_review_col or "",
            "prompt_template": model_backend.build_strong_baseline_prompt(
                "<SURVEY_TEXT>",
                proj["survey_context"],
                proj["taxonomy"],
                proj["coding_rules"]
            )
        }

        if execution_snapshot is not None:
            for key in ('source_batch_id', 'analysis_id', 'evaluation_role', 'source_row_indices', 'rule_revision'):
                if key in execution_snapshot:
                    snapshot[key] = execution_snapshot[key]

        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                INSERT INTO baseline_batches (
                    id, project_id, dataset_id, status, model_name, model_endpoint,
                    job_version, app_mode, retried_from_batch_id, concurrency, total_rows, processed_rows, error_count,
                    blank_count, elapsed_seconds, throughput_items_per_sec, snapshot,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0.0, 0.0, ?, ?, ?)
            """, (
                batch_id, project_id, dataset_id, "queued", frozen_model_name,
                frozen_endpoint, survey_cleaner_job.version, frozen_app_mode,
                retried_from_batch_id, concurrency, len(rows), json.dumps(snapshot), now, now
            ))
            await db.commit()

        # Launch background worker
        task = asyncio.create_task(
            self._execute_batch_worker(
                batch_id=batch_id,
                project=proj,
                rows=rows,
                response_col=response_col,
                id_col=id_col,
                label_topics_col=label_topics_col,
                label_sentiment_col=label_sentiment_col,
                label_needs_review_col=label_needs_review_col,
                concurrency=concurrency,
                snapshot=snapshot
            )
        )
        self.active_tasks[batch_id] = task
        self.cancel_flags[batch_id] = False

        return await self.get_batch(batch_id)

    async def _execute_batch_worker(
        self,
        batch_id: str,
        project: Dict[str, Any],
        rows: List[Dict[str, Any]],
        response_col: str,
        id_col: Optional[str],
        label_topics_col: Optional[str],
        label_sentiment_col: Optional[str],
        label_needs_review_col: Optional[str],
        concurrency: int = 1,
        snapshot: Optional[Dict[str, Any]] = None
    ):
        """Worker task executing batch inference with bounded concurrency and honest logging."""
        t_start = time.perf_counter()

        frozen_app_mode = (snapshot or {}).get("app_mode") or settings.app_mode
        frozen_model_name = (snapshot or {}).get("model_name") or settings.local_model_name or "qwen2.5-coder:3b"
        frozen_endpoint = (snapshot or {}).get("model_endpoint") or settings.local_model_endpoint or "http://127.0.0.1:11434"

        model_backend = LocalModelBackend(
            endpoint_url=frozen_endpoint,
            model_name=frozen_model_name,
            app_mode=frozen_app_mode
        )
        taxonomy = (snapshot or {}).get("taxonomy") or project["taxonomy"]
        valid_taxonomy_ids = {t["id"] for t in taxonomy}
        rules = (snapshot or {}).get("coding_rules") or project["coding_rules"]
        context = (snapshot or {}).get("survey_context") or project["survey_context"]

        logger.info(f"Starting baseline batch {batch_id} for {len(rows)} rows (concurrency={concurrency})")

        # Update status to running
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute(
                "UPDATE baseline_batches SET status = 'running', updated_at = ? WHERE id = ?",
                (get_now_iso(), batch_id)
            )
            await db.commit()

        # Bounded concurrency semaphore (default 1, max 2) for M2 MacBook Air memory safety
        sem = asyncio.Semaphore(max(1, min(concurrency, 2)))
        processed_count = 0
        error_count = 0
        blank_count = 0
        records_for_eval = []

        # Helper for column lookup tolerant to leading/trailing whitespace
        def get_row_val(row: Dict[str, Any], col: Optional[str]) -> Any:
            if not col:
                return None
            if col in row:
                return row[col]
            col_s = col.strip()
            for k, v in row.items():
                if k and k.strip() == col_s:
                    return v
            return None

        def has_row_col(row: Dict[str, Any], col: Optional[str]) -> bool:
            if not col:
                return False
            if col in row:
                return True
            col_s = col.strip()
            return any(k and k.strip() == col_s for k in row.keys())

        async def process_row(idx: int, row_data: Dict[str, Any]):
            nonlocal processed_count, error_count, blank_count

            if self.cancel_flags.get(batch_id, False):
                return

            raw_text = get_row_val(row_data, response_col) or ""
            resp_id = str(get_row_val(row_data, id_col)) if id_col and has_row_col(row_data, id_col) else f"row_{idx+1}"

            # Ground truth parsing
            gt_topics = None
            has_invalid_topic_label = False
            gt_sentiment = None
            has_invalid_sentiment_label = False
            gt_needs_review = None
            has_invalid_needs_review_label = False
            row_label_errors: List[str] = []

            if label_topics_col and has_row_col(row_data, label_topics_col):
                res_topics = parse_ground_truth_topics(get_row_val(row_data, label_topics_col), valid_taxonomy_ids)
                if res_topics.is_present:
                    if res_topics.is_valid:
                        gt_topics = res_topics.value
                    else:
                        has_invalid_topic_label = True
                        if res_topics.error:
                            row_label_errors.append(res_topics.error)

            if label_sentiment_col and has_row_col(row_data, label_sentiment_col):
                res_sent = parse_ground_truth_sentiment(get_row_val(row_data, label_sentiment_col))
                if res_sent.is_present:
                    if res_sent.is_valid:
                        gt_sentiment = res_sent.value
                    else:
                        has_invalid_sentiment_label = True
                        if res_sent.error:
                            row_label_errors.append(res_sent.error)

            if label_needs_review_col and has_row_col(row_data, label_needs_review_col):
                res_rf = parse_ground_truth_needs_review(get_row_val(row_data, label_needs_review_col))
                if res_rf.is_present:
                    if res_rf.is_valid:
                        gt_needs_review = res_rf.value
                    else:
                        has_invalid_needs_review_label = True
                        if res_rf.error:
                            row_label_errors.append(res_rf.error)

            # Handle blank response
            if is_blank_response(raw_text):
                blank_count += 1
                record = {
                    "batch_id": batch_id,
                    "row_index": idx,
                    "response_id": resp_id,
                    "response_text": "",
                    "original_data": json.dumps(row_data),
                    "ground_truth_topics": json.dumps(gt_topics) if gt_topics is not None else None,
                    "ground_truth_sentiment": gt_sentiment,
                    "ground_truth_needs_review": int(gt_needs_review) if gt_needs_review is not None else None,
                    "ground_truth_label_errors": json.dumps(row_label_errors),
                    "raw_model_output": None,
                    "raw_model_text": None,
                    "predicted_topics": json.dumps([]),
                    "topics_valid": 0,
                    "predicted_sentiment": "",
                    "sentiment_valid": 0,
                    "generated_summary": "[Skipped: Blank or whitespace response]",
                    "predicted_needs_review": 0,
                    "needs_review_valid": 0,
                    "review_reason": "Blank response row",
                    "is_valid_schema": 0,
                    "schema_errors": json.dumps(["Response text is blank"]),
                    "status": "blank_skipped",
                    "error_message": "Response text is blank or whitespace",
                    "latency_seconds": 0.0,
                    "is_simulated": 1 if frozen_app_mode == "preview" else 0,
                    "model_name": frozen_model_name
                }
                async with aiosqlite.connect(settings.db_path) as db:
                    await db.execute("""
                        INSERT INTO baseline_predictions (
                            batch_id, row_index, response_id, response_text, original_data,
                            ground_truth_topics, ground_truth_sentiment, ground_truth_needs_review,
                            ground_truth_label_errors, raw_model_output, raw_model_text,
                            predicted_topics, topics_valid, predicted_sentiment, sentiment_valid,
                            generated_summary, predicted_needs_review, needs_review_valid,
                            review_reason, is_valid_schema, schema_errors,
                            status, error_message, latency_seconds, is_simulated, model_name
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, tuple(record.values()))
                    await db.commit()

                records_for_eval.append({
                    "status": "blank_skipped",
                    "ground_truth_topics": gt_topics,
                    "has_invalid_topic_label": has_invalid_topic_label,
                    "ground_truth_sentiment": gt_sentiment,
                    "has_invalid_sentiment_label": has_invalid_sentiment_label,
                    "ground_truth_needs_review": gt_needs_review,
                    "has_invalid_needs_review_label": has_invalid_needs_review_label,
                    "predicted_topics": [],
                    "topics_valid": False,
                    "predicted_sentiment": None,
                    "sentiment_valid": False,
                    "predicted_needs_review": None,
                    "needs_review_valid": False,
                    "is_valid_schema": False
                })
                processed_count += 1
                elapsed = time.perf_counter() - t_start
                throughput = round(processed_count / elapsed, 2) if elapsed > 0 else 0.0
                async with aiosqlite.connect(settings.db_path) as db:
                    await db.execute("""
                        UPDATE baseline_batches
                        SET processed_rows = ?, error_count = ?, blank_count = ?,
                            elapsed_seconds = ?, throughput_items_per_sec = ?, updated_at = ?
                        WHERE id = ?
                    """, (processed_count, error_count, blank_count, round(elapsed, 1), throughput, get_now_iso(), batch_id))
                    await db.commit()
                return

            # Perform bounded inference
            async with sem:
                if self.cancel_flags.get(batch_id, False):
                    return

                t0 = time.perf_counter()
                try:
                    pred_raw = await model_backend.infer_single(
                        response_text=str(raw_text),
                        context=context,
                        taxonomy=taxonomy,
                        rules=rules,
                        use_adapter=False,
                        app_mode=frozen_app_mode,
                        endpoint_url=frozen_endpoint,
                        model_name=frozen_model_name
                    )
                    latency = round(time.perf_counter() - t0, 3)

                    # Validate raw model output strictly against job schema
                    validated = survey_cleaner_job.validate_output(
                        pred_raw,
                        taxonomy,
                        raw_text=pred_raw.get("raw_model_text")
                    )

                    is_sim = 1 if (frozen_app_mode == "preview" or pred_raw.get("is_simulated_fixture", False)) else 0
                    record = {
                        "batch_id": batch_id,
                        "row_index": idx,
                        "response_id": resp_id,
                        "response_text": str(raw_text),
                        "original_data": json.dumps(row_data),
                        "ground_truth_topics": json.dumps(gt_topics) if gt_topics is not None else None,
                        "ground_truth_sentiment": gt_sentiment,
                        "ground_truth_needs_review": int(gt_needs_review) if gt_needs_review is not None else None,
                        "ground_truth_label_errors": json.dumps(row_label_errors),
                        "raw_model_output": json.dumps(pred_raw),
                        "raw_model_text": pred_raw.get("raw_model_text"),
                        "predicted_topics": json.dumps(validated.get("topics", []) if validated.get("topics_valid") else []),
                        "topics_valid": 1 if validated.get("topics_valid") else 0,
                        "predicted_sentiment": validated.get("sentiment", "") if validated.get("sentiment_valid") else "",
                        "sentiment_valid": 1 if validated.get("sentiment_valid") else 0,
                        "generated_summary": validated.get("summary") or "",
                        "predicted_needs_review": 1 if (validated.get("needs_review_valid") and validated.get("needs_review")) else 0,
                        "needs_review_valid": 1 if validated.get("needs_review_valid") else 0,
                        "review_reason": validated.get("review_reason") or "",
                        "is_valid_schema": 1 if validated.get("is_valid_schema") else 0,
                        "schema_errors": json.dumps(validated.get("validation_errors", [])),
                        "status": "success",
                        "error_message": None,
                        "latency_seconds": latency,
                        "is_simulated": is_sim,
                        "model_name": frozen_model_name
                    }

                    records_for_eval.append({
                        "status": "success",
                        "ground_truth_topics": gt_topics,
                        "has_invalid_topic_label": has_invalid_topic_label,
                        "ground_truth_sentiment": gt_sentiment,
                        "has_invalid_sentiment_label": has_invalid_sentiment_label,
                        "ground_truth_needs_review": gt_needs_review,
                        "has_invalid_needs_review_label": has_invalid_needs_review_label,
                        "predicted_topics": validated.get("topics", []),
                        "topics_valid": validated.get("topics_valid", False),
                        "predicted_sentiment": validated.get("sentiment"),
                        "sentiment_valid": validated.get("sentiment_valid", False),
                        "predicted_needs_review": validated.get("needs_review"),
                        "needs_review_valid": validated.get("needs_review_valid", False),
                        "is_valid_schema": validated.get("is_valid_schema", False),
                        "latency_seconds": latency
                    })

                except Exception as err:
                    latency = round(time.perf_counter() - t0, 3)
                    error_count += 1
                    err_str = str(err)
                    logger.warning(f"Error on row {idx} in batch {batch_id}: {err_str}")

                    record = {
                        "batch_id": batch_id,
                        "row_index": idx,
                        "response_id": resp_id,
                        "response_text": str(raw_text),
                        "original_data": json.dumps(row_data),
                        "ground_truth_topics": json.dumps(gt_topics) if gt_topics is not None else None,
                        "ground_truth_sentiment": gt_sentiment,
                        "ground_truth_needs_review": int(gt_needs_review) if gt_needs_review is not None else None,
                        "ground_truth_label_errors": json.dumps(row_label_errors),
                        "raw_model_output": None,
                        "raw_model_text": None,
                        "predicted_topics": json.dumps([]),
                        "topics_valid": 0,
                        "predicted_sentiment": "",
                        "sentiment_valid": 0,
                        "generated_summary": "",
                        "predicted_needs_review": 0,
                        "needs_review_valid": 0,
                        "review_reason": "",
                        "is_valid_schema": 0,
                        "schema_errors": json.dumps([err_str]),
                        "status": "error",
                        "error_message": err_str,
                        "latency_seconds": latency,
                        "is_simulated": 1 if frozen_app_mode == "preview" else 0,
                        "model_name": frozen_model_name
                    }

                    records_for_eval.append({
                        "status": "error",
                        "ground_truth_topics": gt_topics,
                        "has_invalid_topic_label": has_invalid_topic_label,
                        "ground_truth_sentiment": gt_sentiment,
                        "has_invalid_sentiment_label": has_invalid_sentiment_label,
                        "ground_truth_needs_review": gt_needs_review,
                        "has_invalid_needs_review_label": has_invalid_needs_review_label,
                        "predicted_topics": [],
                        "topics_valid": False,
                        "predicted_sentiment": None,
                        "sentiment_valid": False,
                        "predicted_needs_review": None,
                        "needs_review_valid": False,
                        "is_valid_schema": False,
                        "latency_seconds": latency
                    })

                # Insert into DB
                async with aiosqlite.connect(settings.db_path) as db:
                    await db.execute("""
                        INSERT INTO baseline_predictions (
                            batch_id, row_index, response_id, response_text, original_data,
                            ground_truth_topics, ground_truth_sentiment, ground_truth_needs_review,
                            ground_truth_label_errors, raw_model_output, raw_model_text,
                            predicted_topics, topics_valid, predicted_sentiment, sentiment_valid,
                            generated_summary, predicted_needs_review, needs_review_valid,
                            review_reason, is_valid_schema, schema_errors,
                            status, error_message, latency_seconds, is_simulated, model_name
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, tuple(record.values()))
                    await db.commit()
                    await db.commit()

                processed_count += 1

                # Update batch progress periodically
                elapsed = time.perf_counter() - t_start
                throughput = round(processed_count / elapsed, 2) if elapsed > 0 else 0.0
                async with aiosqlite.connect(settings.db_path) as db:
                    await db.execute("""
                        UPDATE baseline_batches
                        SET processed_rows = ?, error_count = ?, blank_count = ?,
                            elapsed_seconds = ?, throughput_items_per_sec = ?, updated_at = ?
                        WHERE id = ?
                    """, (processed_count, error_count, blank_count, round(elapsed, 1), throughput, get_now_iso(), batch_id))
                    await db.commit()

        try:
            # Run sequential or bounded concurrent processing
            for i, r in enumerate(rows):
                if self.cancel_flags.get(batch_id, False):
                    break
                await process_row(i, r)

            total_elapsed = time.perf_counter() - t_start

            if self.cancel_flags.get(batch_id, False):
                logger.info(f"Batch {batch_id} marked canceled.")
                async with aiosqlite.connect(settings.db_path) as db:
                    await db.execute("""
                        UPDATE baseline_batches
                        SET status = 'canceled', elapsed_seconds = ?, updated_at = ?, completed_at = ?
                        WHERE id = ?
                    """, (round(total_elapsed, 1), get_now_iso(), get_now_iso(), batch_id))
                    await db.commit()
                return

            # Compute rigorous baseline evaluation metrics
            tax_ids = [t["id"] for t in taxonomy]
            report = evaluate_baseline_batch(
                records=records_for_eval,
                total_elapsed_seconds=total_elapsed,
                all_taxonomy_ids=tax_ids,
                is_simulated=(frozen_app_mode == "preview"),
                execution_mode=frozen_app_mode,
                model_name=frozen_model_name
            )

            final_status = "completed" if error_count < len(rows) else "failed"

            async with aiosqlite.connect(settings.db_path) as db:
                await db.execute("""
                    UPDATE baseline_batches
                    SET status = ?, processed_rows = ?, error_count = ?, blank_count = ?,
                        metrics = ?, elapsed_seconds = ?, throughput_items_per_sec = ?,
                        updated_at = ?, completed_at = ?
                    WHERE id = ?
                """, (
                    final_status,
                    processed_count,
                    error_count,
                    blank_count,
                    json.dumps(report.model_dump()),
                    round(total_elapsed, 1),
                    report.throughput_items_per_sec,
                    get_now_iso(),
                    get_now_iso(),
                    batch_id
                ))
                await db.commit()

            logger.info(f"Batch {batch_id} completed successfully in {round(total_elapsed, 1)}s. Errors: {error_count}")

        except asyncio.CancelledError:
            logger.info(f"Batch {batch_id} task was canceled.")
            total_elapsed = time.perf_counter() - t_start
            async with aiosqlite.connect(settings.db_path) as db:
                await db.execute("""
                    UPDATE baseline_batches
                    SET status = 'canceled', elapsed_seconds = ?, updated_at = ?, completed_at = ?
                    WHERE id = ?
                """, (round(total_elapsed, 1), get_now_iso(), get_now_iso(), batch_id))
                await db.commit()
        except Exception as e:
            logger.error(f"Batch {batch_id} failed fatally: {e}", exc_info=True)
            total_elapsed = time.perf_counter() - t_start
            async with aiosqlite.connect(settings.db_path) as db:
                await db.execute("""
                    UPDATE baseline_batches
                    SET status = 'failed', error_message = ?, elapsed_seconds = ?, updated_at = ?, completed_at = ?
                    WHERE id = ?
                """, (str(e), round(total_elapsed, 1), get_now_iso(), get_now_iso(), batch_id))
                await db.commit()
        finally:
            self.active_tasks.pop(batch_id, None)
            self.cancel_flags.pop(batch_id, None)

    async def retry_batch(self, batch_id: str) -> Dict[str, Any]:
        """
        Retry a previously interrupted, failed, or canceled batch by creating a linked new batch.
        Preserves the previous batch unchanged.
        """
        old_batch = await self.get_batch(batch_id)
        if not old_batch:
            raise ValueError(f"Batch '{batch_id}' not found.")

        project_id = old_batch["project_id"]
        dataset_id = old_batch["dataset_id"]
        snapshot = old_batch.get("snapshot", {})
        concurrency = old_batch.get("concurrency", 1)

        response_col = snapshot.get("response_col", "feedback_text")
        id_col = snapshot.get("id_col") or None
        label_topics_col = snapshot.get("label_topics_col") or None
        label_sentiment_col = snapshot.get("label_sentiment_col") or None
        label_needs_review_col = snapshot.get("label_needs_review_col") or None

        rows = []
        if snapshot.get('analysis_id') and snapshot.get('source_batch_id'):
            source = await self.get_batch(snapshot['source_batch_id'])
            if not source or source['project_id'] != project_id:
                raise ValueError('Comparison source no longer belongs to this project.')
            originals = await self.list_batch_predictions(source['id'], limit=201)
            by_index = {p['row_index']: p['original_data'] for p in originals}
            try:
                rows = [by_index[i] for i in snapshot['source_row_indices']]
            except KeyError:
                raise ValueError('Comparison source rows are no longer available.')
        elif dataset_id in ("sample_cafe_labeled", "sample_dev_60"):
            is_dev_60 = dataset_id == "sample_dev_60"
            sample_path = settings.dev_sample_csv_path if is_dev_60 else settings.sample_csv_path
            default_filename = "dev_survey_60_labeled.csv" if is_dev_60 else "sample_survey_labeled.csv"
            if not sample_path.exists():
                sample_path = Path(__file__).resolve().parent.parent.parent / "data" / default_filename
            with open(sample_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        else:
            from app.services.run_store import run_store
            ds = await run_store.get_dataset(dataset_id)
            if ds and ds.get("project_id") != project_id:
                raise ValueError(f"Dataset '{dataset_id}' does not belong to project '{project_id}'.")
            if ds and Path(ds["filepath"]).exists():
                filepath = ds["filepath"]
                try:
                    with open(filepath, "r", encoding="utf-8-sig") as f:
                        reader = csv.DictReader(f)
                        rows = list(reader)
                except UnicodeDecodeError:
                    with open(filepath, "r", encoding="latin-1") as f:
                        reader = csv.DictReader(f)
                        rows = list(reader)
            else:
                # Fallback: recover original rows from recorded predictions of the old batch
                old_preds = await self.list_batch_predictions(batch_id, filter_mode="all", limit=50000)
                if old_preds:
                    rows = [p["original_data"] for p in old_preds]
                else:
                    raise ValueError(f"Cannot retry batch {batch_id}: dataset {dataset_id} no longer exists on disk.")

        if rows:
            available_cols = list(rows[0].keys())
            col_map = {c.strip(): c for c in available_cols}
            def resolve_c(c: Optional[str]) -> Optional[str]:
                if not c:
                    return c
                if c in available_cols:
                    return c
                if c.strip() in col_map:
                    return col_map[c.strip()]
                return c
            response_col = resolve_c(response_col)
            id_col = resolve_c(id_col)
            label_topics_col = resolve_c(label_topics_col)
            label_sentiment_col = resolve_c(label_sentiment_col)
            label_needs_review_col = resolve_c(label_needs_review_col)

        retried = await self.create_and_start_batch(
            project_id=project_id,
            dataset_id=dataset_id,
            rows=rows,
            response_col=response_col,
            id_col=id_col,
            label_topics_col=label_topics_col,
            label_sentiment_col=label_sentiment_col,
            label_needs_review_col=label_needs_review_col,
            concurrency=concurrency,
            retried_from_batch_id=batch_id,
            execution_snapshot=snapshot if snapshot.get('analysis_id') else None
        )
        if snapshot.get('analysis_id'):
            async with aiosqlite.connect(settings.db_path) as db:
                await db.execute('UPDATE failure_analyses SET comparison_batch_id = ? WHERE id = ?',
                                 (retried['id'], snapshot['analysis_id']))
                await db.commit()
        return retried

baseline_batch_runner = BaselineBatchRunner()
