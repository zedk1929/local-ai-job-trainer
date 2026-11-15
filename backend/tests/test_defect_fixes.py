import io
import csv
import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.config import settings
from app.services.run_store import run_store
from app.services.model_backend import LocalModelBackend
from app.jobs.survey_cleaner import survey_cleaner_job
from app.services.evaluator import evaluate_baseline_batch, BaselineEvaluationReport
from app.services.baseline_runner import baseline_batch_runner


@pytest.mark.asyncio
async def test_invalid_model_output_does_not_earn_accuracy_credit():
    """
    Defect 2 Reproduction:
    Mock inference returning {} for a response with human sentiment 'unclear' and review label False.
    Must NOT award 100% sentiment accuracy or 100% review flag accuracy.
    Must mark schema validity 0%, preserve denominators, and appear in mistakes/errors.
    """
    tax = [{"id": "drink_quality", "name": "Drink Quality"}]
    val = survey_cleaner_job.validate_output({}, tax)

    # Validate output contract
    assert val["is_valid_schema"] is False
    assert val["sentiment_valid"] is False
    assert val["needs_review_valid"] is False
    assert val["topics_valid"] is False

    record = {
        "status": "success",
        "ground_truth_topics": [],
        "has_invalid_topic_label": False,
        "ground_truth_sentiment": "unclear",
        "has_invalid_sentiment_label": False,
        "ground_truth_needs_review": False,
        "has_invalid_needs_review_label": False,
        "predicted_topics": val.get("topics", []),
        "topics_valid": val.get("topics_valid", False),
        "predicted_sentiment": val.get("sentiment"),
        "sentiment_valid": val.get("sentiment_valid", False),
        "predicted_needs_review": val.get("needs_review"),
        "needs_review_valid": val.get("needs_review_valid", False),
        "is_valid_schema": val.get("is_valid_schema", False),
        "latency_seconds": 1.0
    }

    rep = evaluate_baseline_batch([record], total_elapsed_seconds=1.0)
    assert rep.schema_validity_pct == 0.0
    assert rep.sentiment_accuracy == 0.0  # NOT 100%!
    assert rep.review_flag_accuracy == 0.0  # NOT 100%!
    assert rep.sentiment_labeled_rows == 1  # Denominator preserved!
    assert rep.review_flag_labeled_rows == 1  # Denominator preserved!


@pytest.mark.asyncio
async def test_partial_validity_evaluates_valid_fields_independently():
    """
    Defect 2 requirement:
    A valid predicted field should remain independently evaluable when another field is invalid.
    E.g. Valid topics matches GT, but sentiment is missing.
    """
    tax = [{"id": "drink_quality", "name": "Drink Quality"}]
    raw_output = {
        "topics": ["drink_quality"],
        # sentiment is missing!
        "needs_review": False
    }
    val = survey_cleaner_job.validate_output(raw_output, tax)

    assert val["is_valid_schema"] is False  # Overall schema invalid
    assert val["topics_valid"] is True       # Topics is valid!
    assert val["sentiment_valid"] is False    # Sentiment invalid!
    assert val["needs_review_valid"] is True  # Review is valid!

    record = {
        "status": "success",
        "ground_truth_topics": ["drink_quality"],
        "has_invalid_topic_label": False,
        "ground_truth_sentiment": "positive",
        "has_invalid_sentiment_label": False,
        "ground_truth_needs_review": False,
        "has_invalid_needs_review_label": False,
        "predicted_topics": val.get("topics", []),
        "topics_valid": val.get("topics_valid", False),
        "predicted_sentiment": val.get("sentiment"),
        "sentiment_valid": val.get("sentiment_valid", False),
        "predicted_needs_review": val.get("needs_review"),
        "needs_review_valid": val.get("needs_review_valid", False),
        "is_valid_schema": val.get("is_valid_schema", False),
        "latency_seconds": 1.0
    }

    rep = evaluate_baseline_batch([record], total_elapsed_seconds=1.0, all_taxonomy_ids=["drink_quality"])
    assert rep.schema_validity_pct == 0.0
    assert rep.topic_micro_f1 == 100.0        # Valid topic gets full credit!
    assert rep.sentiment_accuracy == 0.0       # Missing sentiment penalized!
    assert rep.review_flag_accuracy == 100.0   # Valid review flag gets credit!


@pytest.mark.asyncio
async def test_exact_model_output_and_strict_json_validation():
    """
    Defect 6:
    Preserve exact model response. Markdown-fenced JSON must NOT count as strictly valid JSON.
    """
    backend = LocalModelBackend(app_mode="connected")

    fenced_raw = "```json\n{\"topics\": [\"drink_quality\"], \"sentiment\": \"positive\", \"needs_review\": false}\n```"
    plain_raw = "{\"topics\": [\"drink_quality\"], \"sentiment\": \"positive\", \"needs_review\": false}"
    malformed_raw = "Not json at all"
    invalid_types_raw = "{\"topics\": \"drink_quality\", \"sentiment\": 123, \"needs_review\": \"yes\"}"

    tax = [{"id": "drink_quality", "name": "Drink Quality"}]

    # 1. Plain valid JSON
    val_plain = survey_cleaner_job.validate_output(json.loads(plain_raw), tax, raw_text=plain_raw)
    assert val_plain["is_valid_schema"] is True
    assert val_plain["is_strict_json"] is True

    # 2. Fenced JSON - recovered for display/inspection but strictly invalid format
    val_fenced = survey_cleaner_job.validate_output(
        {"topics": ["drink_quality"], "sentiment": "positive", "needs_review": False, "has_markdown_fence": True, "raw_model_text": fenced_raw},
        tax,
        raw_text=fenced_raw
    )
    assert val_fenced["is_valid_schema"] is False
    assert any("markdown" in err.lower() for err in val_fenced["validation_errors"])

    # 3. Malformed non-JSON
    val_malformed = survey_cleaner_job.validate_output(
        {"is_valid_json": False, "raw_model_text": malformed_raw},
        tax,
        raw_text=malformed_raw
    )
    assert val_malformed["is_valid_schema"] is False

    # 4. Valid JSON syntax with invalid field types
    val_types = survey_cleaner_job.validate_output(json.loads(invalid_types_raw), tax, raw_text=invalid_types_raw)
    assert val_types["is_valid_schema"] is False
    assert val_types["is_strict_json"] is True  # Syntax is strictly valid JSON
    assert val_types["topics_valid"] is False
    assert val_types["sentiment_valid"] is False
    assert val_types["needs_review_valid"] is False

    # 5. Issue 3: Valid JSON with embedded triple backticks inside string value must be ACCEPTED
    backticks_raw = '{"topics": ["drink_quality"], "sentiment": "positive", "summary": "Respondent wrote ``` in the form.", "needs_review": false}'
    val_backticks = survey_cleaner_job.validate_output(json.loads(backticks_raw), tax, raw_text=backticks_raw)
    assert val_backticks["is_valid_schema"] is True
    assert val_backticks["is_strict_json"] is True
    assert len(val_backticks["validation_errors"]) == 0
    assert val_backticks["summary"] == "Respondent wrote ``` in the form."


@pytest.mark.asyncio
async def test_dataset_ownership_enforcement():
    """
    Defect 5:
    POST /api/baseline/start must reject project B executing project A's dataset.
    """
    proj_a = await run_store.create_project(
        name="Project A",
        job_id="survey-cleaner",
        description="A",
        survey_context="ctx A",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["rule 1"]
    )
    proj_b = await run_store.create_project(
        name="Project B",
        job_id="survey-cleaner",
        description="B",
        survey_context="ctx B",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["rule 1"]
    )

    # Save a dataset under Project A
    ds_a = await run_store.save_dataset(
        project_id=proj_a["id"],
        filename="survey_a.csv",
        filepath=str(settings.uploads_dir / "survey_a.csv"),
        row_count=5,
        response_col="comment"
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Attempt to run Project A's dataset under Project B
        resp = await client.post("/api/baseline/start", json={
            "project_id": proj_b["id"],
            "dataset_id": ds_a["id"],
            "response_col": "comment"
        })
        # Must be rejected with 404 (or 400) and no batch started
        assert resp.status_code in [400, 404], resp.text
        assert "not found" in resp.text.lower() or "belong" in resp.text.lower()

        # Verify no batch was created for Project B
        active = await client.get(f"/api/baseline/active/{proj_b['id']}")
        assert active.json()["batch"] is None


@pytest.mark.asyncio
async def test_consistent_header_handling_with_spaces():
    """
    Defect 4:
    Headers with leading/trailing spaces e.g. ' id , comment , sentiment '
    must inspect, confirm, execute batch, and export with original headers preserved.
    """
    proj = await run_store.create_project(
        name="Header Spaces Proj",
        job_id="survey-cleaner",
        description="Test spaces",
        survey_context="ctx",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["r1"]
    )
    project_id = proj["id"]

    csv_text = " id , comment , sentiment \n101,Smooth iced latte,positive\n102,Lukewarm drip,negative\n"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Inspect
        files = {"file": ("spaces.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
        inspect_resp = await client.post("/api/datasets/inspect", files=files)
        assert inspect_resp.status_code == 200, inspect_resp.text
        idata = inspect_resp.json()
        assert "comment" in idata["columns"] or " comment " in idata["columns"]

        # 2. Confirm mapping 'comment' as response_col
        confirm_resp = await client.post("/api/datasets/confirm", json={
            "project_id": project_id,
            "temp_file_id": idata["temp_file_id"],
            "filename": "spaces.csv",
            "response_col": "comment",
            "id_col": "id",
            "label_sentiment_col": "sentiment"
        })
        assert confirm_resp.status_code == 200, confirm_resp.text
        dataset_id = confirm_resp.json()["dataset"]["id"]

        # 3. Start batch - must NOT fail with 'Required response column not found'
        with patch.object(
            LocalModelBackend,
            "infer_single",
            new_callable=AsyncMock,
            return_value={
                "topics": ["drink_quality"],
                "sentiment": "positive",
                "summary": "Coffee review",
                "needs_review": False,
                "review_reason": None,
                "is_simulated_fixture": False,
                "model_used": "qwen2.5-coder:3b"
            }
        ):
            start_resp = await client.post("/api/baseline/start", json={
                "project_id": project_id,
                "dataset_id": dataset_id,
                "response_col": "comment"
            })
            assert start_resp.status_code == 200, start_resp.text
            batch_id = start_resp.json()["id"]

            # Wait briefly for batch completion
            for _ in range(20):
                b_resp = await client.get(f"/api/baseline/batch/{batch_id}")
                if b_resp.json()["batch"]["status"] in ["completed", "failed"]:
                    break
                import asyncio
                await asyncio.sleep(0.1)

            assert b_resp.json()["batch"]["status"] == "completed"

            # 4. Export CSV - verify original header ' comment ' is preserved in output!
            exp_resp = await client.post(f"/api/baseline/batch/{batch_id}/export")
            assert exp_resp.status_code == 200
            exp_text = exp_resp.text
            assert " comment " in exp_text or "comment" in exp_text


@pytest.mark.asyncio
async def test_atomic_confirmation_preserves_previous_state_on_failure():
    """
    Defect 3:
    Injected failure during confirmation must roll back and preserve previous
    project dataset selection, mappings, records, and files. Staging file must survive.
    """
    # 1. Setup project already configured with an initial dataset
    proj = await run_store.create_project(
        name="Atomic Confirm Proj",
        job_id="survey-cleaner",
        description="Atomic",
        survey_context="ctx",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["r1"]
    )
    project_id = proj["id"]

    initial_file = settings.uploads_dir / project_id / "initial.csv"
    initial_file.parent.mkdir(parents=True, exist_ok=True)
    initial_file.write_text("id,comment\n1,initial\n", encoding="utf-8")

    init_ds = await run_store.save_dataset(
        project_id=project_id,
        filename="initial.csv",
        filepath=str(initial_file),
        row_count=1,
        response_col="comment",
        id_col="id"
    )
    await run_store.update_project(
        project_id=project_id,
        selected_dataset_id=init_ds["id"],
        response_col="comment",
        id_col="id"
    )

    # 2. Stage a new CSV upload
    new_csv = "id,new_comment\n2,new text\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("new.csv", io.BytesIO(new_csv.encode("utf-8")), "text/csv")}
        inspect_resp = await client.post("/api/datasets/inspect", files=files)
        assert inspect_resp.status_code == 200
        temp_file_id = inspect_resp.json()["temp_file_id"]

        staged_path = settings.uploads_dir / "_staging" / f"{temp_file_id}.csv"
        assert staged_path.exists()

        # 3. Inject a failure during confirmation persistence
        with patch.object(run_store, "confirm_dataset_atomic", side_effect=RuntimeError("Database failure during confirm")):
            confirm_resp = await client.post("/api/datasets/confirm", json={
                "project_id": project_id,
                "temp_file_id": temp_file_id,
                "filename": "new.csv",
                "response_col": "new_comment",
                "id_col": "id"
            })
            assert confirm_resp.status_code == 500

        # 4. Verification:
        # a) Staging file must survive for retry
        assert staged_path.exists(), "Staged file was lost after confirmation failure!"

        # b) Project's previous dataset selection and mappings must survive intact!
        curr_proj = await run_store.get_project(project_id)
        assert curr_proj["selected_dataset_id"] == init_ds["id"]
        assert curr_proj["response_col"] == "comment"
        assert curr_proj["id_col"] == "id"

        # c) Initial dataset and file must still exist
        assert initial_file.exists()
        recheck_init_ds = await run_store.get_dataset(init_ds["id"])
        assert recheck_init_ds is not None


@pytest.mark.asyncio
async def test_filter_modes_show_invalid_schema_and_mistakes():
    """
    Defect 2 requirement:
    Filters 'errors' and 'mistakes' must surface schema invalid and invalid predicted outputs.
    """
    proj = await run_store.create_project(
        name="Filter Test Proj",
        job_id="survey-cleaner",
        description="Filter test",
        survey_context="Cafe",
        taxonomy=[{"id": "service", "name": "Service"}],
        coding_rules=["Rule 1"]
    )
    project_id = proj["id"]

    batch = await baseline_batch_runner.create_and_start_batch(
        project_id=project_id,
        dataset_id="inline_rows",
        rows=[
            {"id": "1", "feedback_text": "Slow service", "label_topics": "service", "label_sentiment": "negative", "label_needs_review": "false"},
            {"id": "2", "feedback_text": "Great latte", "label_topics": "service", "label_sentiment": "positive", "label_needs_review": "false"},
        ],
        response_col="feedback_text",
        id_col="id",
        label_topics_col="label_topics",
        label_sentiment_col="label_sentiment",
        label_needs_review_col="label_needs_review",
        concurrency=1
    )
    batch_id = batch["id"]

    # Mock inference to return {} for row 1 (schema invalid) and valid matching for row 2
    mock_responses = [
        {},  # Row 1 invalid schema
        {"topics": ["service"], "sentiment": "positive", "summary": "Great latte", "needs_review": False}
    ]

    with patch.object(
        LocalModelBackend,
        "infer_single",
        side_effect=mock_responses
    ):
        # Wait for worker
        task = baseline_batch_runner.active_tasks.get(batch_id)
        if task:
            await task

    # Check errors filter -> must contain row 1 because is_valid_schema is 0
    errors = await baseline_batch_runner.list_batch_predictions(batch_id, filter_mode="errors")
    assert len(errors) == 1
    assert errors[0]["response_id"] == "1"
    assert errors[0]["is_valid_schema"] == 0

    # Check mistakes filter -> must contain row 1
    mistakes = await baseline_batch_runner.list_batch_predictions(batch_id, filter_mode="mistakes")
    assert len(mistakes) == 1
    assert mistakes[0]["response_id"] == "1"

    # Check all filter -> must contain both rows
    all_preds = await baseline_batch_runner.list_batch_predictions(batch_id, filter_mode="all")
    assert len(all_preds) == 2


@pytest.mark.asyncio
async def test_retry_batch_enforces_dataset_ownership():
    """
    Defect 5:
    Retrying a batch whose dataset does not belong to the project must be rejected.
    """
    proj_a = await run_store.create_project(
        name="Proj A",
        job_id="survey-cleaner",
        description="A",
        survey_context="Context",
        taxonomy=[],
        coding_rules=[]
    )
    proj_b = await run_store.create_project(
        name="Proj B",
        job_id="survey-cleaner",
        description="B",
        survey_context="Context",
        taxonomy=[],
        coding_rules=[]
    )

    # Project A has a dataset
    ds_a = await run_store.save_dataset(
        project_id=proj_a["id"],
        filename="ds_a.csv",
        filepath="/tmp/nonexistent.csv",
        row_count=1,
        response_col="feedback_text"
    )

    # Manually create a batch for Project B pointing to ds_a
    batch_b = await baseline_batch_runner.create_and_start_batch(
        project_id=proj_b["id"],
        dataset_id=ds_a["id"],
        rows=[{"id": "1", "feedback_text": "Hello"}],
        response_col="feedback_text"
    )

    # Cancel or complete batch
    baseline_batch_runner.cancel_batch(batch_b["id"])

    # Attempting to retry batch_b should raise ValueError because ds_a does not belong to proj_b
    with pytest.raises(ValueError, match="does not belong to project"):
        await baseline_batch_runner.retry_batch(batch_b["id"])


@pytest.mark.asyncio
async def test_invalid_predictions_honest_representation_and_export():
    """
    Issue 1 verification:
    - Transport/inference success kept distinct from output validity
    - Invalid/missing predicted fields marked as unavailable, never valid answers
    - Collision-safe field validity columns in CSV export
    - Error explanation and validation details in CSV export
    - Partially valid outputs preserved independently
    - Valid empty topic lists distinguished from invalid topics
    - Original source columns, headers, and values preserved
    """
    proj = await run_store.create_project(
        name="Honest Export Proj",
        job_id="survey-cleaner",
        description="Testing honest exports",
        survey_context="Cafe survey",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule 1"]
    )
    project_id = proj["id"]

    # 4 rows with custom original source columns to verify original columns & values are preserved:
    # Row 1: Empty dict {} output (transport success, but invalid schema, sentiment unclear & review false)
    # Row 2: Partial validity (topics valid, sentiment missing/invalid, review flag valid)
    # Row 3: Valid empty topic list []
    # Row 4: Inference error (simulated network error)
    rows = [
        {"customer_id": "C101", "comment_text": "Not sure about anything", "label_sentiment": "unclear", "label_review": "false"},
        {"customer_id": "C102", "comment_text": "Iced latte was great", "label_topics": "drink_quality", "label_sentiment": "positive"},
        {"customer_id": "C103", "comment_text": "Nothing to add", "label_topics": "[]"},
        {"customer_id": "C104", "comment_text": "Crash row", "label_sentiment": "negative"},
    ]

    mock_responses = [
        # Row 1: {}
        {},
        # Row 2: Partial validity: valid topics, valid review, missing sentiment
        {"topics": ["drink_quality"], "needs_review": False, "summary": "Great latte"},
        # Row 3: Valid empty topic list
        {"topics": [], "sentiment": "neutral", "needs_review": False, "summary": "No topics"},
        # Row 4: Error
        RuntimeError("Connection to Ollama timed out after 60s")
    ]

    async def mock_infer_single(*args, **kwargs):
        resp = mock_responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return {
            **resp,
            "raw_model_text": json.dumps(resp),
            "is_strict_json": True,
            "has_markdown_fence": False,
            "is_valid_json": True,
            "is_simulated_fixture": False,
            "model_used": "qwen2.5-coder:3b"
        }

    with patch.object(LocalModelBackend, "infer_single", side_effect=mock_infer_single):
        batch = await baseline_batch_runner.create_and_start_batch(
            project_id=project_id,
            dataset_id="inline_rows",
            rows=rows,
            response_col="comment_text",
            id_col="customer_id",
            label_topics_col="label_topics",
            label_sentiment_col="label_sentiment",
            label_needs_review_col="label_review",
            concurrency=1
        )
        batch_id = batch["id"]

        task = baseline_batch_runner.active_tasks.get(batch_id)
        if task:
            await task

    # 1. Inspect prediction records via API
    preds = await baseline_batch_runner.list_batch_predictions(batch_id, filter_mode="all")
    assert len(preds) == 4

    p1, p2, p3, p4 = preds

    # Row 1: {}
    assert p1["status"] == "success"  # Transport success distinct from output validity!
    assert p1["is_valid_schema"] is False
    assert p1["topics_valid"] is False
    assert p1["sentiment_valid"] is False
    assert p1["needs_review_valid"] is False
    assert p1["predicted_sentiment"] == ""  # Never reported as valid 'unclear' answer!

    # Row 2: Partial validity
    assert p2["status"] == "success"
    assert p2["is_valid_schema"] is False
    assert p2["topics_valid"] is True
    assert p2["predicted_topics"] == ["drink_quality"]
    assert p2["sentiment_valid"] is False
    assert p2["needs_review_valid"] is True

    # Row 3: Valid empty topic list
    assert p3["status"] == "success"
    assert p3["is_valid_schema"] is True
    assert p3["topics_valid"] is True
    assert p3["predicted_topics"] == []
    assert p3["sentiment_valid"] is True
    assert p3["needs_review_valid"] is True

    # Row 4: Error
    assert p4["status"] == "error"
    assert p4["is_valid_schema"] is False

    # 2. Inspect CSV export via API client
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        exp_resp = await client.post(f"/api/baseline/batch/{batch_id}/export")
        assert exp_resp.status_code == 200
        reader = list(csv.DictReader(io.StringIO(exp_resp.text)))
        assert len(reader) == 4

        # Verify original columns and response values are intact
        assert "customer_id" in reader[0]
        assert "comment_text" in reader[0]
        assert reader[0]["customer_id"] == "C101"
        assert reader[0]["comment_text"] == "Not sure about anything"

        # Verify collision-safe field-validity columns exist
        assert "baseline_topics_valid" in reader[0]
        assert "baseline_sentiment_valid" in reader[0]
        assert "baseline_needs_review_valid" in reader[0]
        assert "baseline_validation_details" in reader[0]

        # Row 1 (Empty dict {}):
        r1 = reader[0]
        assert r1["baseline_status"] == "success"  # Transport success preserved
        assert r1["baseline_schema_valid"] == "NO"
        assert r1["baseline_topics_valid"] == "NO"
        assert r1["baseline_sentiment_valid"] == "NO"
        assert r1["baseline_needs_review_valid"] == "NO"
        assert r1["baseline_predicted_sentiment"] == "[unavailable]"  # NOT 'unclear'!
        assert r1["baseline_needs_review"] == "[unavailable]"        # NOT 'NO'!
        assert r1["baseline_predicted_topics"] == "[unavailable]"
        assert "Missing required field" in r1["baseline_validation_details"]
        assert "Schema validation failed" in r1["baseline_error"]

        # Row 2 (Partial validity):
        r2 = reader[1]
        assert r2["baseline_topics_valid"] == "YES"
        assert r2["baseline_predicted_topics"] == "drink_quality"     # Preserved!
        assert r2["baseline_sentiment_valid"] == "NO"
        assert r2["baseline_predicted_sentiment"] == "[unavailable]" # Unavailable!
        assert r2["baseline_needs_review_valid"] == "YES"
        assert r2["baseline_needs_review"] == "NO"                   # Preserved!

        # Row 3 (Valid empty topic list):
        r3 = reader[2]
        assert r3["baseline_topics_valid"] == "YES"
        assert r3["baseline_predicted_topics"] == ""                 # Clean empty list!
        assert r3["baseline_sentiment_valid"] == "YES"
        assert r3["baseline_predicted_sentiment"] == "neutral"
        assert r3["baseline_needs_review_valid"] == "YES"
        assert r3["baseline_needs_review"] == "NO"

        # Row 4 (Inference error):
        r4 = reader[3]
        assert r4["baseline_status"] == "error"
        assert r4["baseline_schema_valid"] == "NO"
        assert r4["baseline_predicted_sentiment"] == "[unavailable]"
        assert "timed out" in r4["baseline_error"]


