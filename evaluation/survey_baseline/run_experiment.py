#!/usr/bin/env python3
"""
Reproducible Experiment Runner for Survey Cleaner Baseline Evaluation.

Executes baseline evaluation on evaluation/survey_baseline/dataset.csv using
the local Ollama model (qwen2.5-coder:3b) via the application's actual batch pipeline.
Preserves user data by isolating SQLite and file storage to temporary directories.
"""

import asyncio
import csv
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

# Setup import path for backend modules
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import settings
from app.database import init_db, get_now_iso
from app.services.run_store import run_store
from app.services.baseline_runner import baseline_batch_runner
from app.services.evaluator import (
    evaluate_baseline_batch,
    calculate_topic_micro_f1,
    BaselineEvaluationReport
)
from app.jobs.survey_cleaner import survey_cleaner_job
from app.api.routes_baseline import _make_unique_col


async def run_baseline_experiment():
    print("=" * 70)
    print("SURVEY CLEANER BASELINE EXPERIMENT RUNNER")
    print("Model: qwen2.5-coder:3b | Endpoint: http://127.0.0.1:11434")
    print("Concurrency: 1 | Mode: Connected (Real Local Inference)")
    print("=" * 70)

    # 1. Isolate environment to temporary directory
    temp_dir = Path("/tmp/survey_baseline_eval")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    settings.db_path = temp_dir / "eval_apprentice.sqlite3"
    settings.uploads_dir = temp_dir / "uploads"
    settings.runs_dir = temp_dir / "runs"
    settings.data_dir = temp_dir / "data"
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.runs_dir.mkdir(parents=True, exist_ok=True)

    settings.app_mode = "connected"
    settings.local_model_name = "qwen2.5-coder:3b"
    settings.local_model_endpoint = "http://127.0.0.1:11434"

    print(f"Isolated SQLite database: {settings.db_path}")
    print(f"Isolated uploads dir:    {settings.uploads_dir}")
    await init_db()

    # 2. Create isolated project with Survey Cleaner configuration
    project = await run_store.create_project(
        name="Survey Cleaner Baseline Experiment",
        job_id="survey-cleaner",
        description="Empirical baseline evaluation of qwen2.5-coder:3b on 60 development responses.",
        survey_context="A campus café gathering student and faculty feedback on drink quality, pricing, speed, and seating atmosphere.",
        taxonomy=survey_cleaner_job.config_schema.default_taxonomy,
        coding_rules=survey_cleaner_job.config_schema.default_rules
    )
    project_id = project["id"]
    print(f"Initialized isolated project: {project_id}")

    # 3. Read dataset
    dataset_path = REPO_ROOT / "evaluation" / "survey_baseline" / "dataset.csv"
    with open(dataset_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} rows from {dataset_path.name}")

    # 4. Execute batch pipeline via baseline_batch_runner
    print("\nStarting execution through application batch pipeline...")
    t_start = time.perf_counter()

    batch = await baseline_batch_runner.create_and_start_batch(
        project_id=project_id,
        dataset_id="dev_survey_60_baseline",
        rows=rows,
        response_col="feedback_text",
        id_col="response_id",
        label_topics_col="label_topics",
        label_sentiment_col="label_sentiment",
        label_needs_review_col="label_needs_review",
        concurrency=1
    )
    batch_id = batch["id"]
    print(f"Batch created with ID: {batch_id}")

    # Monitor batch progress with periodic console updates and progressive saving
    out_dir = REPO_ROOT / "evaluation" / "survey_baseline"
    jsonl_path = out_dir / "predictions.jsonl"
    if jsonl_path.exists():
        jsonl_path.unlink()

    last_processed = 0
    while True:
        await asyncio.sleep(2.0)
        curr_batch = await baseline_batch_runner.get_batch(batch_id)
        if not curr_batch:
            break

        processed = curr_batch.get("processed_rows", 0)
        errors = curr_batch.get("error_count", 0)
        blanks = curr_batch.get("blank_count", 0)
        elapsed = curr_batch.get("elapsed_seconds", 0.0)
        status = curr_batch.get("status")

        if processed != last_processed:
            print(f"Progress: {processed}/{len(rows)} rows processed ({errors} errors, {blanks} blank) in {elapsed:.1f}s")
            # Fetch latest predictions and write progressively
            preds = await baseline_batch_runner.list_batch_predictions(batch_id, filter_mode="all", limit=1000)
            with open(jsonl_path, "w", encoding="utf-8") as jf:
                for p in preds:
                    jf.write(json.dumps(p) + "\n")
            last_processed = processed

        if status in ["completed", "failed", "canceled", "interrupted"]:
            print(f"\nBatch reached terminal state: {status.upper()}")
            break

    total_time = time.perf_counter() - t_start
    print(f"Batch completed in {total_time:.2f} seconds ({len(rows)/total_time:.2f} rows/sec)")

    # 5. Fetch all predictions from SQLite
    all_predictions = await baseline_batch_runner.list_batch_predictions(batch_id, filter_mode="all", limit=1000)
    print(f"Retrieved {len(all_predictions)} prediction records from database.")

    # 6. Save final predictions.jsonl
    with open(jsonl_path, "w", encoding="utf-8") as jf:
        for p in all_predictions:
            jf.write(json.dumps(p) + "\n")
    print(f"Saved: {jsonl_path}")

    # 7. Generate results.csv using application export logic
    first_orig = all_predictions[0].get("original_data", {})
    original_cols = list(first_orig.keys())
    allocated_names = set(original_cols)

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
    results_csv_path = out_dir / "results.csv"
    with open(results_csv_path, "w", encoding="utf-8", newline="") as cf:
        writer = csv.DictWriter(cf, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()

        for p in all_predictions:
            row = dict(p.get("original_data", {}))
            topics = p.get("predicted_topics", [])
            row[added_cols["topics"]] = "; ".join(topics) if isinstance(topics, list) else str(topics)
            row[added_cols["sentiment"]] = p.get("predicted_sentiment", "")
            row[added_cols["summary"]] = p.get("generated_summary", "")
            row[added_cols["needs_review"]] = "YES" if p.get("predicted_needs_review") else "NO"
            row[added_cols["review_reason"]] = p.get("review_reason", "") or ""
            row[added_cols["schema_valid"]] = "YES" if p.get("is_valid_schema") else "NO"
            row[added_cols["status"]] = p.get("status", "")
            row[added_cols["error"]] = p.get("error_message") or ""

            is_sim = p.get("is_simulated")
            row[added_cols["is_simulated"]] = "YES" if is_sim else "NO"
            row[added_cols["execution_mode"]] = p.get("execution_mode") or "connected"
            row[added_cols["model_identity"]] = p.get("model_name") or "qwen2.5-coder:3b"

            writer.writerow(row)

    print(f"Saved: {results_csv_path}")

    # 8. Save metrics.json
    final_batch = await baseline_batch_runner.get_batch(batch_id)
    metrics_report = final_batch.get("metrics")
    metrics_json_path = out_dir / "metrics.json"
    with open(metrics_json_path, "w", encoding="utf-8") as mf:
        json.dump(metrics_report, mf, indent=2)
    print(f"Saved: {metrics_json_path}")

    # 9. Independent verification & recalculation
    print("\n" + "=" * 70)
    print("INDEPENDENT METRIC RECALCULATION & VALIDATION")
    print("=" * 70)

    # Verify ID counts
    seen_ids = set()
    duplicate_ids = []
    simulated_count = 0
    for p in all_predictions:
        rid = p["response_id"]
        if rid in seen_ids:
            duplicate_ids.append(rid)
        seen_ids.add(rid)
        if p.get("is_simulated"):
            simulated_count += 1

    assert len(duplicate_ids) == 0, f"Found duplicate response IDs: {duplicate_ids}"
    assert len(seen_ids) == len(rows), f"Expected {len(rows)} unique IDs, found {len(seen_ids)}"
    assert simulated_count == 0, f"Error: found {simulated_count} simulated predictions in connected mode!"

    # Recalculate metrics directly from all_predictions
    attempted = [p for p in all_predictions if p["status"] != "blank_skipped"]
    blanks = [p for p in all_predictions if p["status"] == "blank_skipped"]
    failed = [p for p in all_predictions if p["status"] == "error"]

    schema_valid = [p for p in attempted if p["is_valid_schema"] and p["status"] == "success"]
    schema_valid_pct = round((len(schema_valid) / len(attempted)) * 100, 1)

    # Topics
    labeled_topics = [p for p in attempted if p["ground_truth_topics"] is not None]
    pred_topics_list = [p["predicted_topics"] for p in labeled_topics]
    true_topics_list = [p["ground_truth_topics"] for p in labeled_topics]
    micro_f1 = calculate_topic_micro_f1(pred_topics_list, true_topics_list)

    # Sentiment
    labeled_sent = [p for p in attempted if p["ground_truth_sentiment"] is not None]
    correct_sent = sum(1 for p in labeled_sent if str(p["predicted_sentiment"]).lower() == str(p["ground_truth_sentiment"]).lower())
    sent_acc = round((correct_sent / len(labeled_sent)) * 100, 1)

    # Review flag
    labeled_rev = [p for p in attempted if p["ground_truth_needs_review"] is not None]
    correct_rev = sum(1 for p in labeled_rev if bool(p["predicted_needs_review"]) == bool(p["ground_truth_needs_review"]))
    rev_acc = round((correct_rev / len(labeled_rev)) * 100, 1)

    print(f"Total Rows:             {len(all_predictions)} (Attempted: {len(attempted)}, Blanks: {len(blanks)}, Failed: {len(failed)})")
    print(f"Schema Validity:        {len(schema_valid)}/{len(attempted)} ({schema_valid_pct}%)")
    print(f"Topic Micro-F1:         {micro_f1}% across {len(labeled_topics)} labeled rows")
    print(f"Sentiment Accuracy:     {correct_sent}/{len(labeled_sent)} ({sent_acc}%)")
    print(f"Review Flag Accuracy:   {correct_rev}/{len(labeled_rev)} ({rev_acc}%)")
    print(f"Simulated Fixtures:     0 (100% Real Ollama Inference)")
    print(f"Elapsed Time:           {total_time:.1f}s")
    print(f"Throughput:             {len(attempted)/total_time:.2f} items/s")

    # Assert match with report (0.15% tolerance accounts for rounding difference in evaluate_baseline_batch)
    assert abs(metrics_report["topic_micro_f1"] - micro_f1) <= 0.15, f"Topic Micro-F1 mismatch: report={metrics_report['topic_micro_f1']}, direct={micro_f1}"
    assert abs(metrics_report["sentiment_accuracy"] - sent_acc) < 0.01, "Sentiment Accuracy mismatch"
    assert abs(metrics_report["review_flag_accuracy"] - rev_acc) < 0.01, "Review Flag Accuracy mismatch"
    assert abs(metrics_report["schema_validity_pct"] - schema_valid_pct) < 0.01, "Schema Validity mismatch"

    print("\nALL INDEPENDENT CHECKS PASSED!")
    return batch_id


if __name__ == "__main__":
    asyncio.run(run_baseline_experiment())
