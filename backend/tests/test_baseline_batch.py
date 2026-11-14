import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from app.database import init_db
from app.services.run_store import RunStore
from app.services.baseline_runner import BaselineBatchRunner

@pytest.mark.asyncio
async def test_baseline_batch_runner_lifecycle_and_persistence():
    await init_db()
    store = RunStore()

    # Create dummy test project
    proj = await store.create_project(
        name="Test Project Batch",
        job_id="survey-cleaner",
        description="Testing batch baseline evaluation",
        survey_context="Cafe survey context",
        taxonomy=[
            {"id": "drink_quality", "name": "Drink Quality"},
            {"id": "service", "name": "Service"}
        ],
        coding_rules=["Rule 1", "Rule 2"]
    )

    rows = [
        {"id": "1", "feedback": "Great latte!", "topics": "drink_quality", "sentiment": "positive", "flag": "no"},
        {"id": "2", "feedback": "Slow service.", "topics": "service", "sentiment": "negative", "flag": "no"},
        {"id": "3", "feedback": "", "topics": "", "sentiment": "", "flag": ""} # Blank row edge case
    ]

    mock_responses = [
        {"topics": ["drink_quality"], "sentiment": "positive", "summary": "Great latte", "needs_review": False, "is_valid_schema": True},
        {"topics": ["service"], "sentiment": "negative", "summary": "Slow service", "needs_review": False, "is_valid_schema": True}
    ]

    runner = BaselineBatchRunner()

    with patch("app.services.baseline_runner.LocalModelBackend.infer_single", side_effect=mock_responses):
        batch = await runner.create_and_start_batch(
            project_id=proj["id"],
            dataset_id="test_ds",
            rows=rows,
            response_col="feedback",
            id_col="id",
            label_topics_col="topics",
            label_sentiment_col="sentiment",
            label_needs_review_col="flag",
            concurrency=1
        )

        batch_id = batch["id"]
        assert batch["status"] in ["queued", "running"]

        # Wait for worker task to complete
        task = runner.active_tasks.get(batch_id)
        if task:
            await task

        # Check completed batch from database
        completed = await runner.get_batch(batch_id)
        assert completed["status"] == "completed"
        assert completed["total_rows"] == 3
        assert completed["processed_rows"] == 3
        assert completed["blank_count"] == 1
        assert completed["error_count"] == 0

        metrics = completed["metrics"]
        assert metrics is not None
        assert metrics["total_rows"] == 3
        assert metrics["attempted_rows"] == 2
        assert metrics["blank_rows"] == 1
        assert metrics["schema_validity_pct"] == 100.0
        assert metrics["sentiment_accuracy"] == 100.0
        assert metrics["topic_micro_f1"] == 100.0
        assert metrics["review_flag_accuracy"] == 100.0

        # Verify predictions in SQLite
        preds = await runner.list_batch_predictions(batch_id, filter_mode="all")
        assert len(preds) == 3
        assert preds[0]["status"] == "success"
        assert preds[0]["predicted_topics"] == ["drink_quality"]
        assert preds[2]["status"] == "blank_skipped"

@pytest.mark.asyncio
async def test_baseline_batch_runner_cancellation():
    await init_db()
    store = RunStore()

    proj = await store.create_project(
        name="Test Cancel Project",
        job_id="survey-cleaner",
        description="Testing cancel",
        survey_context="Cafe context",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule 1"]
    )

    rows = [{"id": str(i), "feedback": f"Review {i}"} for i in range(10)]

    runner = BaselineBatchRunner()

    async def slow_infer(*args, **kwargs):
        await asyncio.sleep(0.5)
        return {"topics": ["drink_quality"], "sentiment": "neutral", "summary": "test", "needs_review": False, "is_valid_schema": True}

    with patch("app.services.baseline_runner.LocalModelBackend.infer_single", side_effect=slow_infer):
        batch = await runner.create_and_start_batch(
            project_id=proj["id"],
            dataset_id="cancel_ds",
            rows=rows,
            response_col="feedback",
            id_col="id"
        )
        batch_id = batch["id"]

        await asyncio.sleep(0.2)
        # Cancel the batch
        cancelled = runner.cancel_batch(batch_id)
        assert cancelled is True

        task = runner.active_tasks.get(batch_id)
        if task:
            try:
                await task
            except asyncio.CancelledError:
                pass

        final_batch = await runner.get_batch(batch_id)
        assert final_batch["status"] == "canceled"
