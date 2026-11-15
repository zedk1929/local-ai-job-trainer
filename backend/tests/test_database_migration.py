import pytest
import aiosqlite
import json
import csv
import io
from pathlib import Path
from app.config import settings
from app.database import init_db
from app.api.routes_baseline import export_baseline_csv
from app.api.routes_analysis import compute_field_outcomes


@pytest.mark.asyncio
async def test_legacy_database_migration_backfills_field_validity_accurately(tmp_path, monkeypatch):
    """
    Test upgrading a database with the previous schema (no validity columns or DEFAULT 1),
    including valid, partially invalid, failed, and blank-skipped predictions.
    Verify field validity backfill, CSV export representation, failure analysis representation,
    and repeated migration safety.
    """
    db_file = tmp_path / "legacy_test.sqlite3"
    monkeypatch.setattr(settings, "db_path", db_file)

    # 1. Create a legacy database matching the previous schema WITHOUT field-validity columns
    async with aiosqlite.connect(db_file) as db:
        await db.execute("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                job_id TEXT NOT NULL,
                description TEXT DEFAULT '',
                survey_context TEXT DEFAULT '',
                taxonomy TEXT NOT NULL,
                coding_rules TEXT NOT NULL,
                active_adapter_id TEXT DEFAULT NULL,
                selected_dataset_id TEXT DEFAULT NULL,
                response_col TEXT DEFAULT 'comment',
                id_col TEXT DEFAULT 'id',
                label_topics_col TEXT DEFAULT 'human_topics',
                label_sentiment_col TEXT DEFAULT 'human_sentiment',
                label_needs_review_col TEXT DEFAULT 'human_review',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        await db.execute("""
            CREATE TABLE datasets (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                response_col TEXT NOT NULL,
                id_col TEXT DEFAULT '',
                label_topics_col TEXT DEFAULT '',
                label_sentiment_col TEXT DEFAULT '',
                label_needs_review_col TEXT DEFAULT '',
                origin TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        await db.execute("""
            CREATE TABLE baseline_batches (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                dataset_id TEXT,
                status TEXT NOT NULL,
                model_name TEXT NOT NULL,
                model_endpoint TEXT NOT NULL,
                job_version TEXT NOT NULL,
                app_mode TEXT NOT NULL DEFAULT 'connected',
                retried_from_batch_id TEXT DEFAULT NULL,
                concurrency INTEGER DEFAULT 1,
                total_rows INTEGER DEFAULT 4,
                processed_rows INTEGER DEFAULT 4,
                error_count INTEGER DEFAULT 1,
                blank_count INTEGER DEFAULT 1,
                elapsed_seconds REAL DEFAULT 1.0,
                throughput_items_per_sec REAL DEFAULT 4.0,
                snapshot TEXT NOT NULL,
                metrics TEXT DEFAULT NULL,
                error_message TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT DEFAULT NULL
            );
        """)
        # Legacy baseline_predictions table: NO topics_valid, sentiment_valid, needs_review_valid
        await db.execute("""
            CREATE TABLE baseline_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                response_id TEXT DEFAULT '',
                response_text TEXT NOT NULL,
                original_data TEXT NOT NULL,
                ground_truth_topics TEXT DEFAULT NULL,
                ground_truth_sentiment TEXT DEFAULT NULL,
                ground_truth_needs_review INTEGER DEFAULT NULL,
                ground_truth_label_errors TEXT DEFAULT '[]',
                raw_model_output TEXT DEFAULT NULL,
                raw_model_text TEXT DEFAULT NULL,
                predicted_topics TEXT DEFAULT '[]',
                predicted_sentiment TEXT DEFAULT '',
                generated_summary TEXT DEFAULT '',
                predicted_needs_review INTEGER DEFAULT 0,
                review_reason TEXT DEFAULT '',
                is_valid_schema INTEGER DEFAULT 1,
                schema_errors TEXT DEFAULT '[]',
                status TEXT NOT NULL,
                error_message TEXT DEFAULT NULL,
                latency_seconds REAL DEFAULT 0.0,
                is_simulated INTEGER DEFAULT 0,
                model_name TEXT DEFAULT ''
            );
        """)
        await db.execute("""
            CREATE TABLE system_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        # Insert a project and batch with taxonomy = ['service', 'pricing']
        taxonomy = [
            {"id": "service", "name": "Service", "description": "Customer service"},
            {"id": "pricing", "name": "Pricing", "description": "Price complaints"}
        ]
        snapshot = {
            "survey_context": "Cafe Feedback",
            "taxonomy": taxonomy,
            "coding_rules": ["Assign only listed topics."],
            "response_col": "comment",
            "id_col": "id",
            "label_topics_col": "human_topics",
            "label_sentiment_col": "human_sentiment",
            "label_needs_review_col": "human_review",
            "app_mode": "connected",
            "model_name": "qwen2.5-coder:3b"
        }
        await db.execute(
            "INSERT INTO baseline_batches (id, project_id, status, model_name, model_endpoint, job_version, snapshot, created_at, updated_at) "
            "VALUES ('batch_legacy', 'proj_1', 'completed', 'qwen2.5-coder:3b', 'http://127.0.0.1:11434', '1.0.0', ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (json.dumps(snapshot),)
        )

        # 1. Valid prediction: valid topics, valid sentiment, valid review
        raw_valid = {
            "topics": ["service"],
            "sentiment": "positive",
            "needs_review": False,
            "summary": "Great service"
        }
        await db.execute("""
            INSERT INTO baseline_predictions (
                batch_id, row_index, response_id, response_text, original_data,
                ground_truth_topics, ground_truth_sentiment, ground_truth_needs_review,
                raw_model_output, predicted_topics, predicted_sentiment, predicted_needs_review,
                is_valid_schema, schema_errors, status
            ) VALUES (
                'batch_legacy', 0, 'R0', 'Staff was wonderful!',
                '{"comment": "Staff was wonderful!", "human_topics": "service", "human_sentiment": "positive", "human_review": "false"}',
                '["service"]', 'positive', 0,
                ?, '["service"]', 'positive', 0,
                1, '[]', 'success'
            )
        """, (json.dumps(raw_valid),))

        # 2. Partially invalid prediction: unknown topic 'drink_quality' (not in taxonomy),
        # but sentiment 'positive' and review false are completely valid!
        raw_partially_invalid = {
            "topics": ["drink_quality"],
            "sentiment": "positive",
            "needs_review": False,
            "summary": "Good drink"
        }
        err_list = json.dumps(["Unknown topic ID(s) not in taxonomy: ['drink_quality']"])
        await db.execute("""
            INSERT INTO baseline_predictions (
                batch_id, row_index, response_id, response_text, original_data,
                ground_truth_topics, ground_truth_sentiment, ground_truth_needs_review,
                raw_model_output, predicted_topics, predicted_sentiment, predicted_needs_review,
                is_valid_schema, schema_errors, status
            ) VALUES (
                'batch_legacy', 1, 'R1', 'Coffee was delicious!',
                '{"comment": "Coffee was delicious!", "human_topics": "service", "human_sentiment": "positive", "human_review": "false"}',
                '["service"]', 'positive', 0,
                ?, '[]', 'positive', 0,
                0, ?, 'success'
            )
        """, (json.dumps(raw_partially_invalid), err_list))

        # 3. Failed prediction: model errored out
        await db.execute("""
            INSERT INTO baseline_predictions (
                batch_id, row_index, response_id, response_text, original_data,
                ground_truth_topics, ground_truth_sentiment, ground_truth_needs_review,
                raw_model_output, predicted_topics, predicted_sentiment, predicted_needs_review,
                is_valid_schema, schema_errors, status, error_message
            ) VALUES (
                'batch_legacy', 2, 'R2', 'Error row text',
                '{"comment": "Error row text", "human_topics": "service", "human_sentiment": "negative", "human_review": "true"}',
                '["service"]', 'negative', 1,
                NULL, '[]', '', 0,
                0, '["Connection timeout"]', 'error', 'Connection timeout'
            )
        """)

        # 4. Blank-skipped prediction
        await db.execute("""
            INSERT INTO baseline_predictions (
                batch_id, row_index, response_id, response_text, original_data,
                ground_truth_topics, ground_truth_sentiment, ground_truth_needs_review,
                raw_model_output, predicted_topics, predicted_sentiment, predicted_needs_review,
                is_valid_schema, schema_errors, status, error_message
            ) VALUES (
                'batch_legacy', 3, 'R3', '',
                '{"comment": "", "human_topics": "", "human_sentiment": "", "human_review": ""}',
                NULL, NULL, NULL,
                NULL, '[]', '', 0,
                0, '["Response text is blank"]', 'blank_skipped', 'Blank response'
            )
        """)
        await db.commit()

    # 2. Run the database initialization / migration
    await init_db()

    # 3. Verify columns and field-validity flags
    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute("""
            SELECT row_index, status, is_valid_schema, topics_valid, sentiment_valid, needs_review_valid
            FROM baseline_predictions
            ORDER BY row_index
        """)
        rows = await cur.fetchall()

    assert len(rows) == 4

    # Row 0: Valid prediction -> all valid (1, 1, 1)
    r0 = rows[0]
    assert r0[0] == 0
    assert r0[1] == 'success'
    assert r0[2] == 1  # is_valid_schema
    assert r0[3] == 1  # topics_valid
    assert r0[4] == 1  # sentiment_valid
    assert r0[5] == 1  # needs_review_valid

    # Row 1: Partially invalid prediction -> topics invalid (0), sentiment & review valid (1, 1)
    r1 = rows[1]
    assert r1[0] == 1
    assert r1[1] == 'success'
    assert r1[2] == 0  # is_valid_schema
    assert r1[3] == 0  # topics_valid is 0 because 'drink_quality' is not in taxonomy!
    assert r1[4] == 1  # sentiment_valid is 1 ('positive' is valid)
    assert r1[5] == 1  # needs_review_valid is 1 (False is boolean)

    # Row 2: Failed prediction -> all validity flags must be 0 (missing evidence treated conservatively)
    r2 = rows[2]
    assert r2[0] == 2
    assert r2[1] == 'error'
    assert r2[3] == 0  # topics_valid
    assert r2[4] == 0  # sentiment_valid
    assert r2[5] == 0  # needs_review_valid

    # Row 3: Blank-skipped prediction -> all validity flags must be 0
    r3 = rows[3]
    assert r3[0] == 3
    assert r3[1] == 'blank_skipped'
    assert r3[3] == 0  # topics_valid
    assert r3[4] == 0  # sentiment_valid
    assert r3[5] == 0  # needs_review_valid

    # 4. Verify CSV Export Representation
    export_resp = await export_baseline_csv('batch_legacy')
    csv_output = export_resp.body.decode('utf-8')
    reader = csv.DictReader(io.StringIO(csv_output))
    csv_rows = list(reader)
    assert len(csv_rows) == 4

    # Check Valid Row in Export:
    assert csv_rows[0]['baseline_topics_valid'] == 'YES'
    assert csv_rows[0]['baseline_predicted_topics'] == 'service'
    assert csv_rows[0]['baseline_sentiment_valid'] == 'YES'
    assert csv_rows[0]['baseline_predicted_sentiment'] == 'positive'
    assert csv_rows[0]['baseline_needs_review_valid'] == 'YES'
    assert csv_rows[0]['baseline_needs_review'] == 'NO'

    # Check Partially Invalid Row in Export:
    # Invalid topics shown as [unavailable] and NO, while valid sentiment & review preserved
    assert csv_rows[1]['baseline_topics_valid'] == 'NO'
    assert csv_rows[1]['baseline_predicted_topics'] == '[unavailable]'
    assert csv_rows[1]['baseline_sentiment_valid'] == 'YES'
    assert csv_rows[1]['baseline_predicted_sentiment'] == 'positive'
    assert csv_rows[1]['baseline_needs_review_valid'] == 'YES'
    assert csv_rows[1]['baseline_needs_review'] == 'NO'

    # Check Failed Row in Export:
    assert csv_rows[2]['baseline_topics_valid'] == 'NO'
    assert csv_rows[2]['baseline_predicted_topics'] == '[unavailable]'
    assert csv_rows[2]['baseline_sentiment_valid'] == 'NO'
    assert csv_rows[2]['baseline_predicted_sentiment'] == '[unavailable]'
    assert csv_rows[2]['baseline_needs_review_valid'] == 'NO'
    assert csv_rows[2]['baseline_needs_review'] == '[unavailable]'

    # Check Blank-Skipped Row in Export:
    assert csv_rows[3]['baseline_topics_valid'] == 'NO'
    assert csv_rows[3]['baseline_predicted_topics'] == '[unavailable]'
    assert csv_rows[3]['baseline_sentiment_valid'] == 'NO'
    assert csv_rows[3]['baseline_predicted_sentiment'] == '[unavailable]'
    assert csv_rows[3]['baseline_needs_review_valid'] == 'NO'
    assert csv_rows[3]['baseline_needs_review'] == '[unavailable]'

    # 5. Check Failure Analysis Outcomes Representation
    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM baseline_predictions ORDER BY row_index")
        pred_dicts = [dict(r) for r in await cur.fetchall()]
        for p in pred_dicts:
            p['original_data'] = json.loads(p['original_data'])
            p['predicted_topics'] = json.loads(p['predicted_topics'])
            p['schema_errors'] = json.loads(p['schema_errors'])

    taxonomy_ids = {'service', 'pricing'}

    # Row 0: Valid prediction matches ground truth
    outcomes_r0 = compute_field_outcomes(pred_dicts[0], snapshot, taxonomy_ids)
    assert outcomes_r0['topics']['prediction_status'] == 'match'
    assert outcomes_r0['sentiment']['prediction_status'] == 'match'
    assert outcomes_r0['review_flag']['prediction_status'] == 'match'

    # Row 1: Partially invalid prediction: topics is 'invalid_prediction', sentiment is 'match'!
    outcomes_r1 = compute_field_outcomes(pred_dicts[1], snapshot, taxonomy_ids)
    assert outcomes_r1['topics']['prediction_status'] == 'invalid_prediction'
    assert outcomes_r1['sentiment']['prediction_status'] == 'match'
    assert outcomes_r1['review_flag']['prediction_status'] == 'match'

    # Row 2: Failed row: all fields are invalid_prediction
    outcomes_r2 = compute_field_outcomes(pred_dicts[2], snapshot, taxonomy_ids)
    assert outcomes_r2['topics']['prediction_status'] == 'invalid_prediction'
    assert outcomes_r2['sentiment']['prediction_status'] == 'invalid_prediction'
    assert outcomes_r2['review_flag']['prediction_status'] == 'invalid_prediction'

    # 6. Verify Idempotence and Repeated Migration Safety
    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute("SELECT value FROM system_config WHERE key = 'field_validity_backfilled'")
        assert (await cur.fetchone())[0] == 'true'

    # Run init_db() again - must be a no-op that does not alter anything
    await init_db()

    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute("""
            SELECT row_index, topics_valid, sentiment_valid, needs_review_valid
            FROM baseline_predictions
            ORDER BY row_index
        """)
        repeated_rows = await cur.fetchall()

    assert repeated_rows == [
        (0, 1, 1, 1),
        (1, 0, 1, 1),
        (2, 0, 0, 0),
        (3, 0, 0, 0)
    ]
