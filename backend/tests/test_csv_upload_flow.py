import io
import csv
import json
import pytest
import aiosqlite
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from pathlib import Path
from app.main import app
from app.config import settings
from app.services.run_store import run_store
from app.services.baseline_runner import baseline_batch_runner

@pytest.mark.asyncio
async def test_fresh_project_upload_comment_column_and_start_batch():
    """
    Test the two-stage flow:
    1. Inspect CSV with custom columns `id,comment` (no feedback_text).
    2. Map comment as response column and confirm.
    3. Start a baseline batch on the confirmed dataset.
    """
    proj = await run_store.create_project(
        name="Comment Col Project",
        job_id="survey-cleaner",
        description="Testing id,comment flow",
        survey_context="App reviews",
        taxonomy=[{"id": "ux", "name": "User Experience"}],
        coding_rules=["Rule 1"]
    )
    project_id = proj["id"]

    csv_data = (
        "id,comment\n"
        "101,\"The search bar is very intuitive.\"\n"
        "102,\"App crashed when tapping settings.\"\n"
    ).encode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Stage 1: Inspect
        files = {"file": ("user_feedback.csv", io.BytesIO(csv_data), "text/csv")}
        inspect_resp = await client.post("/api/datasets/inspect", files=files)
        assert inspect_resp.status_code == 200, inspect_resp.text
        inspect_data = inspect_resp.json()

        assert inspect_data["filename"] == "user_feedback.csv"
        assert inspect_data["columns"] == ["id", "comment"]
        assert inspect_data["row_count"] == 2
        assert len(inspect_data["preview_rows"]) == 2
        assert inspect_data["suggested_mappings"]["response_col"] == "comment"
        assert inspect_data["suggested_mappings"]["id_col"] == "id"
        temp_file_id = inspect_data["temp_file_id"]

        # Verify project has NOT yet adopted this dataset before confirmation
        proj_check = await run_store.get_project(project_id)
        assert proj_check.get("selected_dataset_id") is None

        # Stage 2: Confirm
        confirm_resp = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": temp_file_id,
                "filename": "user_feedback.csv",
                "response_col": "comment",
                "id_col": "id",
                "label_topics_col": "",
                "label_sentiment_col": "",
                "label_needs_review_col": ""
            }
        )
        assert confirm_resp.status_code == 200, confirm_resp.text
        confirmed = confirm_resp.json()
        dataset_id = confirmed["dataset"]["id"]
        assert confirmed["dataset"]["filename"] == "user_feedback.csv"
        assert confirmed["validation_summary"]["is_unlabeled"] is True
        assert confirmed["validation_summary"]["valid_response_rows"] == 2

        # Verify project mappings survived and were persisted
        proj_updated = await run_store.get_project(project_id)
        assert proj_updated["selected_dataset_id"] == dataset_id
        assert proj_updated["response_col"] == "comment"
        assert proj_updated["id_col"] == "id"

        # Verify baseline batch starts successfully on this dataset
        mock_infer = {
            "topics": ["ux"],
            "sentiment": "positive",
            "summary": "Feedback on search bar",
            "needs_review": False,
            "is_valid_schema": True
        }
        with patch("app.services.baseline_runner.LocalModelBackend.infer_single", return_value=mock_infer):
            start_resp = await client.post(
                "/api/baseline/start",
                json={
                    "project_id": project_id,
                    "dataset_id": dataset_id,
                    "response_col": "comment",
                    "id_col": "id"
                }
            )
            assert start_resp.status_code == 200, start_resp.text
            batch_data = start_resp.json()
            batch_id = batch_data["id"]

            task = baseline_batch_runner.active_tasks.get(batch_id)
            if task:
                await task

        batch_final = await baseline_batch_runner.get_batch(batch_id)
        assert batch_final["status"] == "completed"
        assert batch_final["total_rows"] == 2
        assert batch_final["processed_rows"] == 2

@pytest.mark.asyncio
async def test_quoted_commas_multiline_escaped_quotes_and_utf8_bom():
    """
    Test inspection and confirmation preserving:
    - UTF-8 BOM (\xef\xbb\xbf)
    - Quoted commas
    - Multiline responses across linebreaks
    - Escaped quotes ("")
    """
    proj = await run_store.create_project(
        name="Complex CSV Project",
        job_id="survey-cleaner",
        description="Testing complex formatting",
        survey_context="Cafe",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule"]
    )
    project_id = proj["id"]

    # CSV with UTF-8 BOM, multiline text, escaped quotes, and commas inside quotes
    raw_csv = (
        b"\xef\xbb\xbfid,feedback,human_topics\n"
        b"1,\"Latte was good, but crowded.\nSecond line of comment with \"\"double quotes\"\".\",drink_quality\n"
        b"2,\"Regular tea.\",[]\n"
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Inspect
        files = {"file": ("complex.csv", io.BytesIO(raw_csv), "text/csv")}
        resp = await client.post("/api/datasets/inspect", files=files)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Check BOM was stripped: first header must be 'id', NOT '\ufeffid'
        assert data["columns"] == ["id", "feedback", "human_topics"]
        assert data["row_count"] == 2
        preview = data["preview_rows"]
        assert len(preview) == 2
        assert "Second line of comment with \"double quotes\"." in preview[0]["feedback"]
        assert "Latte was good, but crowded." in preview[0]["feedback"]

        # Confirm
        confirm_resp = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": data["temp_file_id"],
                "filename": "complex.csv",
                "response_col": "feedback",
                "id_col": "id",
                "label_topics_col": "human_topics"
            }
        )
        assert confirm_resp.status_code == 200, confirm_resp.text
        summary = confirm_resp.json()["validation_summary"]
        assert summary["topics_labeled_rows"] == 2
        assert summary["topics_valid_empty_rows"] == 1 # row 2 is '[]'

@pytest.mark.asyncio
async def test_invalid_and_malformed_csv_errors():
    """Verify informative errors on empty, headerless, duplicate header, and malformed rows."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Empty file
        resp = await client.post("/api/datasets/inspect", files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")})
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

        # 2. Empty column header
        resp = await client.post(
            "/api/datasets/inspect",
            files={"file": ("empty_header.csv", io.BytesIO(b"id,,comment\n1,x,y"), "text/csv")}
        )
        assert resp.status_code == 400
        assert "empty column header" in resp.json()["detail"].lower()

        # 3. Duplicate headers
        resp = await client.post(
            "/api/datasets/inspect",
            files={"file": ("dup.csv", io.BytesIO(b"id,comment,comment\n1,x,y"), "text/csv")}
        )
        assert resp.status_code == 400
        assert "duplicate column headers" in resp.json()["detail"].lower()

        # 4. Malformed row (different column count)
        resp = await client.post(
            "/api/datasets/inspect",
            files={"file": ("malformed.csv", io.BytesIO(b"id,comment\n1,ok\n2,too,many,columns\n"), "text/csv")}
        )
        assert resp.status_code == 400
        assert "malformed row" in resp.json()["detail"].lower()

        # 5. Headers only (no data rows)
        resp = await client.post(
            "/api/datasets/inspect",
            files={"file": ("no_data.csv", io.BytesIO(b"id,comment\n"), "text/csv")}
        )
        assert resp.status_code == 400
        assert "no data rows" in resp.json()["detail"].lower()

@pytest.mark.asyncio
async def test_canceling_or_replacing_pending_upload_preserves_confirmed_dataset():
    """Verify that inspecting new files does not touch the project's confirmed dataset."""
    proj = await run_store.create_project(
        name="Preserve Dataset Proj",
        job_id="survey-cleaner",
        description="Preserve dataset on cancel",
        survey_context="Cafe",
        taxonomy=[{"id": "drink", "name": "Drink"}],
        coding_rules=["Rule"]
    )
    project_id = proj["id"]

    csv_a = b"id,text\n1,Initial dataset confirmed\n"
    csv_b = b"id,other_text\n2,Pending dataset that gets abandoned\n"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Confirm dataset A
        insp_a = await client.post("/api/datasets/inspect", files={"file": ("a.csv", io.BytesIO(csv_a), "text/csv")})
        assert insp_a.status_code == 200
        conf_a = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": insp_a.json()["temp_file_id"],
                "filename": "a.csv",
                "response_col": "text",
                "id_col": "id"
            }
        )
        assert conf_a.status_code == 200
        ds_a_id = conf_a.json()["dataset"]["id"]

        # Inspect dataset B (pending)
        insp_b = await client.post("/api/datasets/inspect", files={"file": ("b.csv", io.BytesIO(csv_b), "text/csv")})
        assert insp_b.status_code == 200

        # Check project still points to dataset A with response_col="text"
        proj_after = await run_store.get_project(project_id)
        assert proj_after["selected_dataset_id"] == ds_a_id
        assert proj_after["response_col"] == "text"

        # Check dataset A preview is completely preserved
        prev = await client.get(f"/api/datasets/{project_id}/{ds_a_id}/preview")
        assert prev.status_code == 200
        assert prev.json()["preview_rows"][0]["text"] == "Initial dataset confirmed"

@pytest.mark.asyncio
async def test_two_uploads_same_display_filename_preserve_separate_contents():
    """Verify that uploading two files with the same filename produces unique internal files."""
    proj = await run_store.create_project(
        name="Filename Collision Proj",
        job_id="survey-cleaner",
        description="Test unique internal storage",
        survey_context="Cafe",
        taxonomy=[{"id": "drink", "name": "Drink"}],
        coding_rules=["Rule"]
    )
    project_id = proj["id"]

    csv_v1 = b"id,comment\n1,First upload content\n"
    csv_v2 = b"id,comment\n2,Second upload different content\n"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Upload 1: survey.csv
        insp1 = await client.post("/api/datasets/inspect", files={"file": ("survey.csv", io.BytesIO(csv_v1), "text/csv")})
        conf1 = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": insp1.json()["temp_file_id"],
                "filename": "survey.csv",
                "response_col": "comment",
                "id_col": "id"
            }
        )
        ds1 = conf1.json()["dataset"]

        # Upload 2: also named survey.csv
        insp2 = await client.post("/api/datasets/inspect", files={"file": ("survey.csv", io.BytesIO(csv_v2), "text/csv")})
        conf2 = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": insp2.json()["temp_file_id"],
                "filename": "survey.csv",
                "response_col": "comment",
                "id_col": "id"
            }
        )
        ds2 = conf2.json()["dataset"]

        # Check different dataset IDs and different disk filepaths
        assert ds1["id"] != ds2["id"]
        assert ds1["filepath"] != ds2["filepath"]
        assert Path(ds1["filepath"]).exists()
        assert Path(ds2["filepath"]).exists()

        # Check content is distinct
        prev1 = await client.get(f"/api/datasets/{project_id}/{ds1['id']}/preview")
        prev2 = await client.get(f"/api/datasets/{project_id}/{ds2['id']}/preview")
        assert prev1.json()["preview_rows"][0]["comment"] == "First upload content"
        assert prev2.json()["preview_rows"][0]["comment"] == "Second upload different content"

@pytest.mark.asyncio
async def test_inspect_and_confirm_sample_flow():
    """Verify that sample CSV uses the same inspect/map/confirm flow."""
    proj = await run_store.create_project(
        name="Sample Flow Proj",
        job_id="survey-cleaner",
        description="Testing sample inspect/confirm",
        survey_context="Cafe",
        taxonomy=[{"id": "drink_quality", "name": "Drink Quality"}],
        coding_rules=["Rule"]
    )
    project_id = proj["id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Inspect sample
        resp = await client.post("/api/datasets/inspect", data={"source": "sample"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["is_sample"] is True
        assert data["row_count"] == 12
        assert "feedback_text" in data["columns"]

        # Confirm sample
        conf = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": data["temp_file_id"],
                "filename": data["filename"],
                "response_col": "feedback_text",
                "id_col": "response_id",
                "label_topics_col": "label_topics",
                "label_sentiment_col": "label_sentiment",
                "label_needs_review_col": "label_needs_review",
                "is_sample": True
            }
        )
        assert conf.status_code == 200, conf.text
        cdata = conf.json()
        assert cdata["dataset"]["row_count"] == 12
        assert cdata["validation_summary"]["valid_response_rows"] == 11
        assert cdata["validation_summary"]["blank_response_rows"] == 1

@pytest.mark.asyncio
async def test_invalid_mapping_preserves_staged_upload_for_retry():
    """
    Regression Test for Issue 1:
    - Inspect a valid CSV with columns `id,comment`.
    - Confirm with a nonexistent response column: HTTP 400.
    - Staged file must be preserved; project and datasets must not be modified.
    - Correct the mapping to `comment` and confirm using the SAME staged upload: HTTP 200.
    """
    proj = await run_store.create_project(
        name="Retry Staged Project",
        job_id="survey-cleaner",
        description="Testing retry after invalid mapping",
        survey_context="Cafe",
        taxonomy=[{"id": "service", "name": "Service"}],
        coding_rules=["Rule"]
    )
    project_id = proj["id"]

    csv_data = b"id,comment\n1,Friendly baristas\n2,Quick checkout\n"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Inspect valid CSV
        files = {"file": ("cafe_comments.csv", io.BytesIO(csv_data), "text/csv")}
        insp = await client.post("/api/datasets/inspect", files=files)
        assert insp.status_code == 200, insp.text
        insp_data = insp.json()
        temp_file_id = insp_data["temp_file_id"]

        staging_file = settings.uploads_dir / "_staging" / f"{temp_file_id}.csv"
        assert staging_file.exists(), "Staged file should exist after inspect"

        # Step 2: Confirm with invalid response column (nonexistent)
        bad_confirm = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": temp_file_id,
                "filename": "cafe_comments.csv",
                "response_col": "nonexistent_column",
                "id_col": "id"
            }
        )
        assert bad_confirm.status_code == 400
        assert "not found in CSV" in bad_confirm.json()["detail"]

        # Verify staged file was NOT deleted / consumed on failure
        assert staging_file.exists(), "Staged file must be preserved after invalid mapping confirmation failure"

        # Verify project state was NOT altered
        proj_state = await run_store.get_project(project_id)
        assert proj_state.get("selected_dataset_id") is None
        datasets = await run_store.list_datasets(project_id)
        assert len(datasets) == 0, "No dataset should be created on failed confirmation"

        # Step 3: Correct the mapping to `comment` and confirm using the SAME staged upload
        good_confirm = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": temp_file_id,
                "filename": "cafe_comments.csv",
                "response_col": "comment",
                "id_col": "id"
            }
        )
        assert good_confirm.status_code == 200, good_confirm.text
        conf_data = good_confirm.json()
        dataset_id = conf_data["dataset"]["id"]

        # Staged file should now be consumed
        assert not staging_file.exists(), "Staged file should be deleted after successful confirmation"

        # Project and dataset state should be properly updated
        proj_after = await run_store.get_project(project_id)
        assert proj_after["selected_dataset_id"] == dataset_id
        assert proj_after["response_col"] == "comment"
        assert proj_after["id_col"] == "id"

@pytest.mark.asyncio
async def test_persistence_failure_rolls_back_without_leaving_confirmed_dataset():
    """
    Verify that if database persistence fails during confirmation:
    - Staged file is preserved
    - Destination file on disk is removed
    - Dataset record is deleted
    - Project state is not corrupted
    """
    proj = await run_store.create_project(
        name="Persistence Failure Test",
        job_id="survey-cleaner",
        description="Testing DB failure rollback",
        survey_context="Cafe",
        taxonomy=[{"id": "service", "name": "Service"}],
        coding_rules=["Rule"]
    )
    project_id = proj["id"]

    csv_data = b"id,comment\n1,Good food\n"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        insp = await client.post("/api/datasets/inspect", files={"file": ("feedback.csv", io.BytesIO(csv_data), "text/csv")})
        assert insp.status_code == 200
        temp_file_id = insp.json()["temp_file_id"]
        staging_file = settings.uploads_dir / "_staging" / f"{temp_file_id}.csv"

        # Patch run_store.update_project to simulate an unhandled DB failure
        with patch.object(run_store, "update_project", side_effect=RuntimeError("Simulated DB disk failure")):
            fail_confirm = await client.post(
                "/api/datasets/confirm",
                json={
                    "project_id": project_id,
                    "temp_file_id": temp_file_id,
                    "filename": "feedback.csv",
                    "response_col": "comment",
                    "id_col": "id"
                }
            )
            assert fail_confirm.status_code == 500
            assert "Failed to persist dataset confirmation" in fail_confirm.json()["detail"]

        # Staged file must still exist
        assert staging_file.exists(), "Staging file must remain intact after persistence error"

        # No confirmed dataset should be recorded
        datasets = await run_store.list_datasets(project_id)
        assert len(datasets) == 0, "Failed confirmation must not leave orphaned dataset record"

        # Project must still have no selected dataset
        proj_current = await run_store.get_project(project_id)
        assert proj_current.get("selected_dataset_id") is None

@pytest.mark.asyncio
async def test_malformed_csv_quotes_rejected_with_useful_error():
    """
    Regression Test for Issue 2:
    - Input with unclosed/malformed quotes like:
        id,comment
        1,"unfinished comment
        2,another response
    - Must be rejected with HTTP 400 rather than silently merging rows.
    - Staging file must NOT be created, and no confirmed dataset created.
    """
    malformed_csv = (
        "id,comment\n"
        "1,\"unfinished comment\n"
        "2,another response\n"
    ).encode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Inspect must reject with HTTP 400
        files = {"file": ("malformed_quotes.csv", io.BytesIO(malformed_csv), "text/csv")}
        resp = await client.post("/api/datasets/inspect", files=files)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        detail = resp.json()["detail"]
        assert "malformed csv" in detail.lower() or "unexpected end of data" in detail.lower()

        # Check no staged files exist in _staging directory
        staging_dir = settings.uploads_dir / "_staging"
        if staging_dir.exists():
            staged = list(staging_dir.glob("*.csv"))
            assert len(staged) == 0, f"No staged file should be created on rejected CSV, found {staged}"

        # 2. Direct upload must also reject with HTTP 400
        proj = await run_store.create_project(
            name="Malformed Upload Proj",
            job_id="survey-cleaner",
            description="Testing upload rejection",
            survey_context="Cafe",
            taxonomy=[{"id": "service", "name": "Service"}],
            coding_rules=["Rule"]
        )
        up_files = {"file": ("malformed_quotes.csv", io.BytesIO(malformed_csv), "text/csv")}
        up_resp = await client.post(
            "/api/datasets/upload",
            data={"project_id": proj["id"], "response_col": "comment"},
            files=up_files
        )
        assert up_resp.status_code == 400
        assert "malformed csv" in up_resp.json()["detail"].lower() or "unexpected end of data" in up_resp.json()["detail"].lower()

        # Verify no dataset was saved for project
        datasets = await run_store.list_datasets(proj["id"])
        assert len(datasets) == 0

@pytest.mark.asyncio
async def test_valid_multiline_quotes_and_escaped_quotes_succeed():
    """
    Verify that strict CSV parsing still properly accepts:
    - Multiline responses with closed quotes
    - Escaped quotes ("")
    - Quoted commas
    """
    valid_csv = (
        "id,comment\n"
        "1,\"Line 1\nLine 2\nLine 3\"\n"
        "2,\"Customer said, \"\"Awesome service!\"\", would return\"\n"
        "3,\"Latte, mocha, and tea\"\n"
    ).encode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("valid_quotes.csv", io.BytesIO(valid_csv), "text/csv")}
        resp = await client.post("/api/datasets/inspect", files=files)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["row_count"] == 3
        assert data["preview_rows"][0]["id"] == "1"
        assert data["preview_rows"][0]["comment"] == "Line 1\nLine 2\nLine 3"
        assert data["preview_rows"][1]["comment"] == 'Customer said, "Awesome service!", would return'
        assert data["preview_rows"][2]["comment"] == "Latte, mocha, and tea"

@pytest.mark.asyncio
async def test_dev_benchmark_60_dataset_inspect_confirm_and_validate():
    """
    Verify that the ~60 row development benchmark dataset (dev_survey_60_labeled.csv):
    1. Can be inspected directly via preset source="dev_60"
    2. Has correct suggested column mappings and 61 rows (60 labeled + 1 blank)
    3. Confirms cleanly against Survey Cleaner taxonomy
    4. Produces 0 invalid topic labels, 0 invalid sentiment labels, 0 invalid review flags
    5. Correctly accounts for explicit empty topics (6 rows) and blank response (1 row)
    """
    proj = await run_store.create_project(
        name="Dev Benchmark 60 Project",
        job_id="survey-cleaner",
        description="Testing dev benchmark dataset",
        survey_context="A campus café gathering feedback",
        taxonomy=[
            {"id": "drink_quality", "name": "Drink Quality"},
            {"id": "price", "name": "Price & Value"},
            {"id": "service", "name": "Staff & Service"},
            {"id": "seating", "name": "Atmosphere & Seating"},
        ],
        coding_rules=["Assign all relevant topics", "Mixed sentiment for positive+negative"]
    )
    project_id = proj["id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Inspect dev benchmark source
        inspect_resp = await client.post("/api/datasets/inspect", data={"source": "dev_60"})
        assert inspect_resp.status_code == 200, inspect_resp.text
        inspect_data = inspect_resp.json()
        assert inspect_data["filename"] == "dev_survey_60_labeled.csv"
        assert inspect_data["row_count"] == 61
        assert inspect_data["columns"] == [
            "response_id", "customer_name", "feedback_text",
            "label_topics", "label_sentiment", "label_needs_review"
        ]
        assert inspect_data["suggested_mappings"]["response_col"] == "feedback_text"
        assert inspect_data["suggested_mappings"]["id_col"] == "response_id"
        assert inspect_data["suggested_mappings"]["label_topics_col"] == "label_topics"
        assert inspect_data["suggested_mappings"]["label_sentiment_col"] == "label_sentiment"
        assert inspect_data["suggested_mappings"]["label_needs_review_col"] == "label_needs_review"

        # 2. Confirm dataset
        confirm_resp = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": inspect_data["temp_file_id"],
                "filename": inspect_data["filename"],
                "is_sample": True,
                "response_col": "feedback_text",
                "id_col": "response_id",
                "label_topics_col": "label_topics",
                "label_sentiment_col": "label_sentiment",
                "label_needs_review_col": "label_needs_review"
            }
        )
        assert confirm_resp.status_code == 200, confirm_resp.text
        confirm_data = confirm_resp.json()
        summary = confirm_data["validation_summary"]

        assert summary["total_rows"] == 61
        assert summary["valid_response_rows"] == 60
        assert summary["blank_response_rows"] == 1
        assert summary["topics_invalid_rows"] == 0
        assert summary["topics_valid_empty_rows"] == 6
        assert summary["topics_labeled_rows"] == 60
        assert summary["sentiment_invalid_rows"] == 0
        assert summary["sentiment_labeled_rows"] == 60
        assert summary["needs_review_invalid_rows"] == 0
        assert summary["needs_review_labeled_rows"] == 60
        assert summary["is_unlabeled"] is False

        # 3. Preview endpoint check
        preview_resp = await client.get(f"/api/datasets/{project_id}/sample_dev_60/preview")
        assert preview_resp.status_code == 200
        preview_data = preview_resp.json()
        assert preview_data["row_count"] == 61
        assert len(preview_data["preview_rows"]) == 5

        # 4. Direct file upload of dev_survey_60_labeled.csv
        dev_file_path = Path(__file__).resolve().parent.parent / "data" / "dev_survey_60_labeled.csv"
        with open(dev_file_path, "rb") as f:
            file_bytes = f.read()

        upload_inspect = await client.post(
            "/api/datasets/inspect",
            files={"file": ("custom_dev_survey.csv", io.BytesIO(file_bytes), "text/csv")}
        )
        assert upload_inspect.status_code == 200
        up_data = upload_inspect.json()
        assert up_data["row_count"] == 61

        confirm_up = await client.post(
            "/api/datasets/confirm",
            json={
                "project_id": project_id,
                "temp_file_id": up_data["temp_file_id"],
                "filename": "custom_dev_survey.csv",
                "is_sample": False,
                "response_col": "feedback_text",
                "id_col": "response_id",
                "label_topics_col": "label_topics",
                "label_sentiment_col": "label_sentiment",
                "label_needs_review_col": "label_needs_review"
            }
        )
        assert confirm_up.status_code == 200
        up_summary = confirm_up.json()["validation_summary"]
        assert up_summary["total_rows"] == 61
        assert up_summary["topics_invalid_rows"] == 0
        assert up_summary["sentiment_invalid_rows"] == 0
        assert up_summary["needs_review_invalid_rows"] == 0
