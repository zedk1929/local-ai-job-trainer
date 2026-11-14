import io
import csv
import json
from pathlib import Path
import pytest
import aiosqlite
import asyncio
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import settings
from app.services.run_store import run_store
from app.services.baseline_runner import baseline_batch_runner
from app.services.model_backend import ModelServiceError

@pytest.mark.asyncio
async def test_csv_upload_route_with_custom_mappings():
    # 1. Create a project
    proj = await run_store.create_project(
        name="Upload Mapping Test Proj",
        job_id="survey-cleaner",
        description="Testing CSV upload with custom mappings",
        survey_context="Cafe surveys",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule 1"]
    )
    project_id = proj["id"]

    # 2. Upload CSV via HTTP route
    csv_content = (
        "custom_id,user_comment,human_topics,human_sent,human_review\n"
        "C01,\"Loved the cold brew!\",drink_quality,positive,no\n"
        "C02,\"Wait was too long\",service,negative,yes\n"
    ).encode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {
            "file": ("custom_survey.csv", io.BytesIO(csv_content), "text/csv")
        }
        data = {
            "project_id": project_id,
            "response_col": "user_comment",
            "id_col": "custom_id",
            "label_topics_col": "human_topics",
            "label_sentiment_col": "human_sent",
            "label_needs_review_col": "human_review"
        }
        resp = await client.post("/api/datasets/upload", data=data, files=files)
        assert resp.status_code == 200, resp.text
        upload_resp = resp.json()
        assert upload_resp["dataset"]["filename"] == "custom_survey.csv"
        assert upload_resp["row_count"] == 2
        dataset_id = upload_resp["dataset"]["id"]

        # Verify dataset was saved under settings.uploads_dir with collision-free naming
        expected_file = Path(upload_resp["dataset"]["filepath"])
        assert expected_file.exists()

        # Verify project mappings were updated and persisted
        proj_resp = await client.get(f"/api/projects/{project_id}")
        assert proj_resp.status_code == 200
        pdata = proj_resp.json()
        assert pdata["selected_dataset_id"] == dataset_id
        assert pdata["response_col"] == "user_comment"
        assert pdata["id_col"] == "custom_id"
        assert pdata["label_topics_col"] == "human_topics"
        assert pdata["label_sentiment_col"] == "human_sent"
        assert pdata["label_needs_review_col"] == "human_review"

@pytest.mark.asyncio
async def test_sample_retry_route_creates_linked_batch():
    proj = await run_store.create_project(
        name="Sample Retry Project",
        job_id="survey-cleaner",
        description="Testing retry on bundled sample",
        survey_context="Cafe",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule"]
    )
    project_id = proj["id"]

    mock_resp = {
        "topics": ["drink_quality"],
        "sentiment": "positive",
        "summary": "Sample response recap",
        "needs_review": False,
        "is_valid_schema": True
    }

    # Start a batch on sample dataset
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.baseline_runner.LocalModelBackend.infer_single", return_value=mock_resp):
            start_resp = await client.post(
                "/api/baseline/start",
                json={
                    "project_id": project_id,
                    "dataset_id": "sample_cafe_labeled",
                    "response_col": "feedback_text",
                    "concurrency": 1
                }
            )
            assert start_resp.status_code == 200, start_resp.text
            batch1 = start_resp.json()
            batch1_id = batch1["id"]

            task = baseline_batch_runner.active_tasks.get(batch1_id)
            if task:
                await task

        # Mark batch interrupted to simulate server restart
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute(
                "UPDATE baseline_batches SET status = 'interrupted', error_message = 'Backend restarted' WHERE id = ?",
                (batch1_id,)
            )
            await db.commit()

        # Call retry endpoint
        with patch("app.services.baseline_runner.LocalModelBackend.infer_single", return_value=mock_resp):
            retry_resp = await client.post(f"/api/baseline/batch/{batch1_id}/retry")
            assert retry_resp.status_code == 200, retry_resp.text
            batch2 = retry_resp.json()
            batch2_id = batch2["id"]

            task2 = baseline_batch_runner.active_tasks.get(batch2_id)
            if task2:
                await task2

        # Verify old batch remains interrupted and unchanged
        resp_old = await client.get(f"/api/baseline/batch/{batch1_id}")
        assert resp_old.status_code == 200
        old_data = resp_old.json()["batch"]
        assert old_data["status"] == "interrupted"

        # Verify new batch is linked to the old batch
        resp_new = await client.get(f"/api/baseline/batch/{batch2_id}")
        assert resp_new.status_code == 200
        new_data = resp_new.json()["batch"]
        assert new_data["status"] == "completed"
        assert new_data["retried_from_batch_id"] == batch1_id

@pytest.mark.asyncio
async def test_freeze_batch_execution_mid_batch_configuration_change():
    """
    Ensure every row of a batch strictly uses the configuration captured at batch start.
    Changing global mode, model, and endpoint mid-batch does NOT alter the running batch.
    A subsequent batch uses the updated global settings.
    """
    proj = await run_store.create_project(
        name="Mid-Batch Change Proj",
        job_id="survey-cleaner",
        description="Testing config freezing",
        survey_context="Cafe",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule"]
    )
    project_id = proj["id"]

    # Global settings start in connected mode with initial model
    settings.app_mode = "connected"
    settings.local_model_name = "qwen2.5-coder:3b"
    settings.local_model_endpoint = "http://127.0.0.1:11434"

    rows = [
        {"id": "1", "feedback": "First row"},
        {"id": "2", "feedback": "Second row"}
    ]

    row_calls = []

    async def mock_infer_single(*args, **kwargs):
        # Record what parameters reached infer_single
        row_calls.append({
            "app_mode": kwargs.get("app_mode"),
            "model_name": kwargs.get("model_name"),
            "endpoint_url": kwargs.get("endpoint_url")
        })
        # If this is row 1, mutate global settings right now to simulate user toggle mid-batch!
        if len(row_calls) == 1:
            settings.app_mode = "preview"
            settings.local_model_name = "mutated_model"
            settings.local_model_endpoint = "http://mutated:11434"

        await asyncio.sleep(0.01)
        return {
            "topics": ["drink_quality"],
            "sentiment": "positive",
            "summary": "Recap",
            "needs_review": False,
            "is_valid_schema": True
        }

    with patch("app.services.baseline_runner.LocalModelBackend.infer_single", side_effect=mock_infer_single):
        batch1 = await baseline_batch_runner.create_and_start_batch(
            project_id=project_id,
            dataset_id="test_ds",
            rows=rows,
            response_col="feedback",
            id_col="id"
        )
        task1 = baseline_batch_runner.active_tasks.get(batch1["id"])
        if task1:
            await task1

    # Verify that BOTH rows of batch1 were executed with the FROZEN settings ('connected', 'qwen2.5-coder:3b')
    assert len(row_calls) == 2
    for call in row_calls:
        assert call["app_mode"] == "connected", f"Expected connected but got {call['app_mode']}"
        assert call["model_name"] == "qwen2.5-coder:3b"
        assert call["endpoint_url"] == "http://127.0.0.1:11434"

    # Verify batch1 stored predictions have is_simulated == False and model_name == 'qwen2.5-coder:3b'
    preds1 = await baseline_batch_runner.list_batch_predictions(batch1["id"])
    assert len(preds1) == 2
    for p in preds1:
        assert p["is_simulated"] is False
        assert p["model_name"] == "qwen2.5-coder:3b"

    b1_final = await baseline_batch_runner.get_batch(batch1["id"])
    assert b1_final["app_mode"] == "connected"
    assert b1_final["model_name"] == "qwen2.5-coder:3b"
    assert b1_final["metrics"]["is_simulated"] is False

    # Now start a second batch. Since global settings were mutated to 'preview', batch2 should use 'preview'!
    batch2 = await baseline_batch_runner.create_and_start_batch(
        project_id=project_id,
        dataset_id="test_ds",
        rows=[{"id": "3", "feedback": "Batch 2 row"}],
        response_col="feedback",
        id_col="id"
    )
    task2 = baseline_batch_runner.active_tasks.get(batch2["id"])
    if task2:
        await task2

    b2_final = await baseline_batch_runner.get_batch(batch2["id"])
    assert b2_final["app_mode"] == "preview"
    assert b2_final["model_name"] == "mutated_model"
    assert b2_final["metrics"]["is_simulated"] is True

    preds2 = await baseline_batch_runner.list_batch_predictions(batch2["id"])
    assert len(preds2) == 1
    assert preds2[0]["is_simulated"] is True
    assert preds2[0]["model_name"] == "mutated_model"

@pytest.mark.asyncio
async def test_connected_mode_failure_produces_errors_never_fixtures():
    """
    In connected mode, when Ollama inference fails, the runner must record an honest
    error status and failure count. It must NEVER substitute preview fixtures.
    """
    proj = await run_store.create_project(
        name="Failure Honesty Proj",
        job_id="survey-cleaner",
        description="Testing honest failure in connected mode",
        survey_context="Cafe",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule"]
    )
    project_id = proj["id"]

    settings.app_mode = "connected"

    rows = [{"id": "1", "feedback": "Real customer feedback"}]

    with patch("app.services.baseline_runner.LocalModelBackend.infer_single", side_effect=ModelServiceError("Connection refused at http://127.0.0.1:11434")):
        batch = await baseline_batch_runner.create_and_start_batch(
            project_id=project_id,
            dataset_id="test_ds",
            rows=rows,
            response_col="feedback",
            id_col="id"
        )
        task = baseline_batch_runner.active_tasks.get(batch["id"])
        if task:
            await task

    b_final = await baseline_batch_runner.get_batch(batch["id"])
    assert b_final["status"] == "failed"
    assert b_final["error_count"] == 1

    preds = await baseline_batch_runner.list_batch_predictions(batch["id"])
    assert len(preds) == 1
    p = preds[0]
    assert p["status"] == "error"
    assert "Connection refused" in p["error_message"]
    # Provenance: never labeled as preview fixture
    assert p["is_simulated"] is False

@pytest.mark.asyncio
async def test_export_preserves_provenance_and_handles_collisions():
    """
    Test that CSV export contains provenance columns:
    - baseline_is_simulated ('YES' / 'NO')
    - baseline_execution_mode ('preview' / 'connected')
    - baseline_model_identity
    and preserves original columns untouched even on collision.
    """
    proj = await run_store.create_project(
        name="Export Provenance Proj",
        job_id="survey-cleaner",
        description="Testing export provenance",
        survey_context="Cafe",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule"]
    )
    project_id = proj["id"]

    settings.app_mode = "connected"
    settings.local_model_name = "qwen2.5-coder:3b"

    rows = [
        {
            "id": "1",
            "feedback": "Cold brew was great!",
            "baseline_is_simulated": "SOURCE_USER_VALUE_DO_NOT_TOUCH",
            "baseline_summary": "SOURCE_USER_SUMMARY"
        }
    ]

    mock_resp = {
        "topics": ["drink_quality"],
        "sentiment": "positive",
        "summary": "Model summary recap",
        "needs_review": False,
        "is_valid_schema": True
    }

    with patch("app.services.baseline_runner.LocalModelBackend.infer_single", return_value=mock_resp):
        batch = await baseline_batch_runner.create_and_start_batch(
            project_id=project_id,
            dataset_id="test_ds",
            rows=rows,
            response_col="feedback",
            id_col="id"
        )
        task = baseline_batch_runner.active_tasks.get(batch["id"])
        if task:
            await task

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/api/baseline/batch/{batch['id']}/export")
        assert resp.status_code == 200, resp.text
        csv_text = resp.text

    reader = csv.DictReader(io.StringIO(csv_text))
    out_rows = list(reader)
    assert len(out_rows) == 1
    row = out_rows[0]

    # Source column preservation
    assert row["id"] == "1"
    assert row["feedback"] == "Cold brew was great!"
    assert row["baseline_is_simulated"] == "SOURCE_USER_VALUE_DO_NOT_TOUCH"
    assert row["baseline_summary"] == "SOURCE_USER_SUMMARY"

    # Collision-free provenance columns
    assert "eval_baseline_is_simulated" in row
    assert row["eval_baseline_is_simulated"] == "NO"
    assert "baseline_execution_mode" in row
    assert row["baseline_execution_mode"] == "connected"
    assert "baseline_model_identity" in row
    assert row["baseline_model_identity"] == "qwen2.5-coder:3b"

@pytest.mark.asyncio
async def test_full_custom_column_user_journey_refresh_and_export():
    """
    End-to-end user journey test:
    1. Inspect custom-column CSV: uid,customer_comment,human_topics,human_sentiment,human_needs_review.
    2. Confirm with custom mappings.
    3. Simulate refresh: GET /api/projects/{id} and GET /api/datasets/.../preview restores dataset and mappings.
    4. Start baseline batch.
    5. Evaluate predictions vs human labels (scoring accuracy, F1, review flag).
    6. Export results: verifies provenance and verbatim preservation of custom source columns.
    """
    proj = await run_store.create_project(
        name="Full Journey Proj",
        job_id="survey-cleaner",
        description="End-to-end journey verification",
        survey_context="Cafe surveys",
        taxonomy=[
            {"id": "drink_quality", "name": "Drink Quality"},
            {"id": "price", "name": "Price"},
            {"id": "service", "name": "Service"}
        ],
        coding_rules=["Assign relevant topics", "Flag severe issues"]
    )
    project_id = proj["id"]

    settings.app_mode = "connected"
    settings.local_model_name = "qwen2.5-coder:3b"

    csv_bytes = (
        "uid,customer_comment,human_topics,human_sentiment,human_needs_review\n"
        "U101,\"Cappuccino was great but expensive.\",drink_quality; price,mixed,false\n"
        "U102,\"Found broken glass in my drink!\",drink_quality; service,negative,true\n"
        "U103,\"\",,, \n"
    ).encode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Inspect
        insp_resp = await client.post(
            "/api/datasets/inspect",
            files={"file": ("custom_feedback.csv", io.BytesIO(csv_bytes), "text/csv")}
        )
        assert insp_resp.status_code == 200, insp_resp.text
        insp_data = insp_resp.json()
        temp_file_id = insp_data["temp_file_id"]
        assert insp_data["row_count"] == 3

        # 2. Confirm
        conf_resp = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": temp_file_id,
                "filename": "custom_feedback.csv",
                "response_col": "customer_comment",
                "id_col": "uid",
                "label_topics_col": "human_topics",
                "label_sentiment_col": "human_sentiment",
                "label_needs_review_col": "human_needs_review"
            }
        )
        assert conf_resp.status_code == 200, conf_resp.text
        conf_data = conf_resp.json()
        dataset_id = conf_data["dataset"]["id"]
        assert conf_data["validation_summary"]["valid_response_rows"] == 2
        assert conf_data["validation_summary"]["blank_response_rows"] == 1

        # 3. Simulate browser refresh / re-fetch
        refresh_proj = await client.get(f"/api/projects/{project_id}")
        assert refresh_proj.status_code == 200
        p_data = refresh_proj.json()
        assert p_data["selected_dataset_id"] == dataset_id
        assert p_data["response_col"] == "customer_comment"
        assert p_data["id_col"] == "uid"
        assert p_data["label_topics_col"] == "human_topics"
        assert p_data["label_sentiment_col"] == "human_sentiment"
        assert p_data["label_needs_review_col"] == "human_needs_review"

        refresh_preview = await client.get(f"/api/datasets/{project_id}/{dataset_id}/preview")
        assert refresh_preview.status_code == 200
        prev_data = refresh_preview.json()
        assert prev_data["row_count"] == 3
        assert prev_data["columns"] == ["uid", "customer_comment", "human_topics", "human_sentiment", "human_needs_review"]
        assert prev_data["preview_rows"][0]["customer_comment"] == "Cappuccino was great but expensive."

        # 4. Start baseline batch
        mock_predictions = [
            # For U101: matches ground truth topics and sentiment
            {
                "topics": ["drink_quality", "price"],
                "sentiment": "mixed",
                "summary": "Great cappuccino, expensive price",
                "needs_review": False,
                "is_valid_schema": True
            },
            # For U102: matches ground truth topics, sentiment, and needs_review
            {
                "topics": ["drink_quality", "service"],
                "sentiment": "negative",
                "summary": "Severe glass hazard in drink",
                "needs_review": True,
                "is_valid_schema": True
            }
        ]
        call_idx = 0
        async def mock_infer(*args, **kwargs):
            nonlocal call_idx
            res = mock_predictions[call_idx % len(mock_predictions)]
            call_idx += 1
            return res

        with patch("app.services.baseline_runner.LocalModelBackend.infer_single", side_effect=mock_infer):
            start_resp = await client.post(
                "/api/baseline/start",
                json={
                    "project_id": project_id,
                    "dataset_id": dataset_id,
                    "response_col": "customer_comment",
                    "id_col": "uid",
                    "label_topics_col": "human_topics",
                    "label_sentiment_col": "human_sentiment",
                    "label_needs_review_col": "human_needs_review"
                }
            )
            assert start_resp.status_code == 200, start_resp.text
            batch_id = start_resp.json()["id"]

            task = baseline_batch_runner.active_tasks.get(batch_id)
            if task:
                await task

        # 5. Check batch results and evaluation metrics
        batch_resp = await client.get(f"/api/baseline/batch/{batch_id}")
        assert batch_resp.status_code == 200
        batch_data = batch_resp.json()["batch"]
        assert batch_data["status"] == "completed"
        assert batch_data["total_rows"] == 3
        assert batch_data["processed_rows"] == 3
        metrics = batch_data["metrics"]
        assert metrics["blank_rows"] == 1
        assert metrics["schema_validity_pct"] == 100.0
        assert metrics["sentiment_accuracy"] == 100.0
        assert metrics["topic_micro_f1"] == 100.0
        assert metrics["review_flag_accuracy"] == 100.0

        # 6. Export results and verify preservation & provenance
        export_resp = await client.post(f"/api/baseline/batch/{batch_id}/export")
        assert export_resp.status_code == 200, export_resp.text
        csv_reader = csv.DictReader(io.StringIO(export_resp.text))
        export_rows = list(csv_reader)
        assert len(export_rows) == 3

        # Row 1 check
        r1 = export_rows[0]
        assert r1["uid"] == "U101"
        assert r1["customer_comment"] == "Cappuccino was great but expensive."
        assert r1["human_topics"] == "drink_quality; price"
        assert r1["human_sentiment"] == "mixed"
        assert r1["human_needs_review"] == "false"
        assert r1["baseline_predicted_topics"] == "drink_quality; price"
        assert r1["baseline_predicted_sentiment"] == "mixed"
        assert r1["baseline_status"] == "success"
        assert r1["baseline_is_simulated"] == "NO"

        # Row 3 (blank comment) check
        r3 = export_rows[2]
        assert r3["uid"] == "U103"
        assert r3["baseline_status"] == "blank_skipped"
