import pytest
import io
import csv
import json
import aiosqlite
from unittest.mock import patch
from app.config import settings
from app.database import mark_interrupted_baseline_batches, get_now_iso
from app.services.run_store import run_store
from app.services.baseline_runner import baseline_batch_runner
from app.api.routes_baseline import export_baseline_csv

@pytest.mark.asyncio
async def test_startup_marks_interrupted_batches():
    # Insert a dummy batch with status 'running' and one with 'queued' and one with 'completed'
    now = get_now_iso()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
            INSERT INTO projects (id, name, job_id, taxonomy, coding_rules, created_at, updated_at)
            VALUES ('proj_1', 'Test', 'survey-cleaner', '[]', '[]', ?, ?)
        """, (now, now))
        await db.execute("""
            INSERT INTO baseline_batches (
                id, project_id, dataset_id, status, model_name, model_endpoint, job_version,
                snapshot, created_at, updated_at
            ) VALUES
            ('b_running', 'proj_1', 'ds_1', 'running', 'qwen2.5-coder:3b', 'http://127.0.0.1:11434', '1.0.0', '{}', ?, ?),
            ('b_queued', 'proj_1', 'ds_1', 'queued', 'qwen2.5-coder:3b', 'http://127.0.0.1:11434', '1.0.0', '{}', ?, ?),
            ('b_done', 'proj_1', 'ds_1', 'completed', 'qwen2.5-coder:3b', 'http://127.0.0.1:11434', '1.0.0', '{}', ?, ?)
        """, (now, now, now, now, now, now))
        await db.commit()

    # Call mark_interrupted_baseline_batches
    await mark_interrupted_baseline_batches()

    # Check status
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id, status, error_message FROM baseline_batches ORDER BY id")
        rows = {r["id"]: dict(r) for r in await cur.fetchall()}

    assert rows["b_running"]["status"] == "interrupted"
    assert "backend restarted while batch was running" in rows["b_running"]["error_message"].lower()
    assert rows["b_queued"]["status"] == "interrupted"
    assert rows["b_done"]["status"] == "completed"

@pytest.mark.asyncio
async def test_export_csv_preserves_original_columns_and_handles_collisions():
    proj = await run_store.create_project(
        name="Collision Project",
        job_id="survey-cleaner",
        description="Testing CSV export collision avoidance",
        survey_context="Cafe survey",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule"]
    )

    # Original CSV rows having names that collide with baseline columns!
    rows = [
        {
            "id": "101",
            "feedback": "Great latte, but noisy.\nSecond line of feedback with, comma.",
            "baseline_summary": "ORIGINAL_USER_SUMMARY_DO_NOT_OVERWRITE",
            "baseline_predicted_topics": "ORIGINAL_USER_TOPICS",
            "baseline_status": "ORIGINAL_USER_STATUS"
        }
    ]

    mock_responses = [
        {
            "topics": ["drink_quality"],
            "sentiment": "positive",
            "summary": "Model generated recap",
            "needs_review": False,
            "is_valid_schema": True
        }
    ]

    with patch("app.services.baseline_runner.LocalModelBackend.infer_single", side_effect=mock_responses):
        batch = await baseline_batch_runner.create_and_start_batch(
            project_id=proj["id"],
            dataset_id="collision_test",
            rows=rows,
            response_col="feedback",
            id_col="id"
        )
        task = baseline_batch_runner.active_tasks.get(batch["id"])
        if task:
            await task

    # Export CSV via endpoint logic
    response = await export_baseline_csv(batch["id"])
    assert response.status_code == 200
    csv_text = response.body.decode("utf-8")

    reader = csv.DictReader(io.StringIO(csv_text))
    exported_rows = list(reader)
    assert len(exported_rows) == 1
    row = exported_rows[0]

    # Check original columns are preserved verbatim
    assert row["id"] == "101"
    assert "Great latte, but noisy." in row["feedback"]
    assert "Second line of feedback with, comma." in row["feedback"]
    assert row["baseline_summary"] == "ORIGINAL_USER_SUMMARY_DO_NOT_OVERWRITE"
    assert row["baseline_predicted_topics"] == "ORIGINAL_USER_TOPICS"
    assert row["baseline_status"] == "ORIGINAL_USER_STATUS"

    # Check collision-free column was allocated for generated summary
    assert "eval_baseline_summary" in row
    assert row["eval_baseline_summary"] == "Model generated recap"
    assert "eval_baseline_predicted_topics" in row
    assert row["eval_baseline_predicted_topics"] == "drink_quality"

@pytest.mark.asyncio
async def test_retry_interrupted_batch_creates_linked_batch():
    proj = await run_store.create_project(
        name="Retry Project",
        job_id="survey-cleaner",
        description="Testing retry",
        survey_context="Cafe",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule"]
    )

    rows = [{"id": "1", "feedback": "Nice coffee."}]

    mock_responses = [
        {"topics": ["drink_quality"], "sentiment": "positive", "summary": "Nice", "needs_review": False, "is_valid_schema": True}
    ]

    with patch("app.services.baseline_runner.LocalModelBackend.infer_single", side_effect=mock_responses):
        batch = await baseline_batch_runner.create_and_start_batch(
            project_id=proj["id"],
            dataset_id="test_ds",
            rows=rows,
            response_col="feedback",
            id_col="id"
        )
        task = baseline_batch_runner.active_tasks.get(batch["id"])
        if task:
            await task

    # Manually mark batch interrupted
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("UPDATE baseline_batches SET status = 'interrupted' WHERE id = ?", (batch["id"],))
        await db.commit()

    # Retry batch
    with patch("app.services.baseline_runner.LocalModelBackend.infer_single", side_effect=mock_responses):
        new_batch = await baseline_batch_runner.retry_batch(batch["id"])
        new_task = baseline_batch_runner.active_tasks.get(new_batch["id"])
        if new_task:
            await new_task

    # Check previous batch is preserved with status 'interrupted'
    old_batch = await baseline_batch_runner.get_batch(batch["id"])
    assert old_batch["status"] == "interrupted"

    # Check new batch is linked
    assert new_batch["id"] != batch["id"]
    assert new_batch["retried_from_batch_id"] == batch["id"]
    completed_new = await baseline_batch_runner.get_batch(new_batch["id"])
    assert completed_new["status"] == "completed"
