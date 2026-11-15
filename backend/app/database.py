import aiosqlite
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from app.config import settings

def get_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def init_db():
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                job_id TEXT NOT NULL,
                description TEXT DEFAULT '',
                survey_context TEXT DEFAULT '',
                taxonomy TEXT NOT NULL,
                coding_rules TEXT NOT NULL,
                active_adapter_id TEXT DEFAULT NULL,
                selected_dataset_id TEXT DEFAULT NULL,
                response_col TEXT DEFAULT 'feedback_text',
                id_col TEXT DEFAULT 'response_id',
                label_topics_col TEXT DEFAULT '',
                label_sentiment_col TEXT DEFAULT '',
                label_needs_review_col TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
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
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                status TEXT NOT NULL,
                current_stage TEXT NOT NULL,
                config TEXT NOT NULL,
                results TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT DEFAULT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS baseline_batches (
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
                total_rows INTEGER DEFAULT 0,
                processed_rows INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                blank_count INTEGER DEFAULT 0,
                elapsed_seconds REAL DEFAULT 0.0,
                throughput_items_per_sec REAL DEFAULT 0.0,
                snapshot TEXT NOT NULL,
                metrics TEXT DEFAULT NULL,
                error_message TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT DEFAULT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS baseline_predictions (
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
                topics_valid INTEGER DEFAULT NULL,
                predicted_sentiment TEXT DEFAULT '',
                sentiment_valid INTEGER DEFAULT NULL,
                generated_summary TEXT DEFAULT '',
                predicted_needs_review INTEGER DEFAULT 0,
                needs_review_valid INTEGER DEFAULT NULL,
                review_reason TEXT DEFAULT '',
                is_valid_schema INTEGER DEFAULT 1,
                schema_errors TEXT DEFAULT '[]',
                status TEXT NOT NULL,
                error_message TEXT DEFAULT NULL,
                latency_seconds REAL DEFAULT 0.0,
                is_simulated INTEGER DEFAULT 0,
                model_name TEXT DEFAULT '',
                FOREIGN KEY (batch_id) REFERENCES baseline_batches(id) ON DELETE CASCADE
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS failure_analyses (
                id TEXT PRIMARY KEY,
                source_batch_id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL,
                status TEXT NOT NULL,
                report TEXT NOT NULL DEFAULT '{}',
                error_message TEXT,
                comparison_batch_id TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Migration column checks for existing databases
        await _ensure_columns(db)

        # Backfill field validity for historical predictions
        await _backfill_field_validity(db)

        await db.commit()

async def _ensure_columns(db: aiosqlite.Connection):
    """Safely add any new columns to existing tables."""
    # Check projects table
    cursor = await db.execute("PRAGMA table_info(projects)")
    cols = [r[1] for r in await cursor.fetchall()]
    new_project_cols = [
        ("selected_dataset_id", "TEXT DEFAULT NULL"),
        ("response_col", "TEXT DEFAULT 'feedback_text'"),
        ("id_col", "TEXT DEFAULT 'response_id'"),
        ("label_topics_col", "TEXT DEFAULT ''"),
        ("label_sentiment_col", "TEXT DEFAULT ''"),
        ("label_needs_review_col", "TEXT DEFAULT ''")
    ]
    for cname, ctype in new_project_cols:
        if cname not in cols:
            try:
                await db.execute(f"ALTER TABLE projects ADD COLUMN {cname} {ctype}")
            except Exception:
                pass

    # Check datasets table
    cursor = await db.execute("PRAGMA table_info(datasets)")
    cols = [r[1] for r in await cursor.fetchall()]
    new_dataset_cols = [
        ("id_col", "TEXT DEFAULT ''"),
        ("label_topics_col", "TEXT DEFAULT ''"),
        ("label_sentiment_col", "TEXT DEFAULT ''"),
        ("label_needs_review_col", "TEXT DEFAULT ''")
    ]
    for cname, ctype in new_dataset_cols:
        if cname not in cols:
            try:
                await db.execute(f"ALTER TABLE datasets ADD COLUMN {cname} {ctype}")
            except Exception:
                pass

    # Check baseline_batches table
    cursor = await db.execute("PRAGMA table_info(baseline_batches)")
    cols = [r[1] for r in await cursor.fetchall()]
    new_batch_cols = [
        ("app_mode", "TEXT NOT NULL DEFAULT 'connected'"),
        ("retried_from_batch_id", "TEXT DEFAULT NULL")
    ]
    for cname, ctype in new_batch_cols:
        if cname not in cols:
            try:
                await db.execute(f"ALTER TABLE baseline_batches ADD COLUMN {cname} {ctype}")
            except Exception:
                pass

    # Check baseline_predictions table
    cursor = await db.execute("PRAGMA table_info(baseline_predictions)")
    cols = [r[1] for r in await cursor.fetchall()]
    new_pred_cols = [
        ("ground_truth_label_errors", "TEXT DEFAULT '[]'"),
        ("raw_model_output", "TEXT DEFAULT NULL"),
        ("raw_model_text", "TEXT DEFAULT NULL"),
        ("topics_valid", "INTEGER DEFAULT NULL"),
        ("sentiment_valid", "INTEGER DEFAULT NULL"),
        ("needs_review_valid", "INTEGER DEFAULT NULL"),
        ("is_simulated", "INTEGER DEFAULT 0"),
        ("model_name", "TEXT DEFAULT ''")
    ]
    for cname, ctype in new_pred_cols:
        if cname not in cols:
            try:
                await db.execute(f"ALTER TABLE baseline_predictions ADD COLUMN {cname} {ctype}")
            except Exception:
                pass

async def _backfill_field_validity(db: aiosqlite.Connection):
    """
    Backfill field validity (topics_valid, sentiment_valid, needs_review_valid)
    for historical predictions using available recorded raw output and the existing validation contract.
    Treats missing evidence conservatively and preserves valid fields independently.
    Safe to run repeatedly and does not overwrite validity flags recorded by current code.
    """
    # Check if migration has already been applied
    cursor = await db.execute("SELECT value FROM system_config WHERE key = 'field_validity_backfilled'")
    migrated_row = await cursor.fetchone()
    if migrated_row and migrated_row[0] == 'true':
        return

    # Check if baseline_predictions table exists
    cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='baseline_predictions'")
    if not await cursor.fetchone():
        return

    # Cache taxonomy for each batch from baseline_batches snapshots
    batch_taxonomy_list: dict[str, list] = {}
    batch_taxonomy_ids: dict[str, set[str]] = {}
    try:
        cur = await db.execute("SELECT id, snapshot FROM baseline_batches")
        for b_row in await cur.fetchall():
            b_id, snap_str = b_row[0], b_row[1]
            try:
                snap = json.loads(snap_str) if snap_str else {}
                tax = snap.get("taxonomy", [])
                if isinstance(tax, list):
                    batch_taxonomy_list[b_id] = tax
                    batch_taxonomy_ids[b_id] = {t["id"] for t in tax if isinstance(t, dict) and "id" in t}
                else:
                    batch_taxonomy_list[b_id] = []
                    batch_taxonomy_ids[b_id] = set()
            except Exception:
                batch_taxonomy_list[b_id] = []
                batch_taxonomy_ids[b_id] = set()
    except Exception:
        pass

    from app.jobs.survey_cleaner import survey_cleaner_job

    VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed", "unclear"}

    cur = await db.execute("""
        SELECT id, batch_id, status, is_valid_schema, schema_errors,
               raw_model_output, raw_model_text, predicted_topics, predicted_sentiment,
               predicted_needs_review, topics_valid, sentiment_valid, needs_review_valid
        FROM baseline_predictions
    """)
    predictions = await cur.fetchall()

    updates = []
    for p in predictions:
        pid = p[0]
        batch_id = p[1]
        status = p[2]
        is_valid_schema = p[3]
        raw_output_str = p[5]
        raw_text_str = p[6]
        pred_topics_str = p[7]
        pred_sentiment_str = p[8]
        pred_needs_review_val = p[9]
        curr_top_valid = p[10]
        curr_sent_valid = p[11]
        curr_rev_valid = p[12]

        tax_list = batch_taxonomy_list.get(batch_id, [])
        tax_ids = batch_taxonomy_ids.get(batch_id, set())

        if status == 'blank_skipped' or status in ('error', 'failed'):
            new_top_valid = 0
            new_sent_valid = 0
            new_rev_valid = 0
        elif status == 'success':
            raw_obj = None
            if raw_output_str:
                try:
                    raw_obj = json.loads(raw_output_str)
                except Exception:
                    raw_obj = None
            if raw_obj is None and raw_text_str:
                try:
                    raw_obj = json.loads(raw_text_str)
                except Exception:
                    raw_obj = None

            if isinstance(raw_obj, dict):
                validated = survey_cleaner_job.validate_output(raw_obj, tax_list, raw_text=raw_text_str)
                new_top_valid = 1 if validated.get("topics_valid") else 0
                new_sent_valid = 1 if validated.get("sentiment_valid") else 0
                new_rev_valid = 1 if validated.get("needs_review_valid") else 0
            else:
                # Missing raw output evidence: treat missing evidence conservatively
                if is_valid_schema == 1:
                    # Schema was marked valid. Verify recorded fields independently against domain rules:
                    try:
                        pt = json.loads(pred_topics_str) if pred_topics_str else []
                        if isinstance(pt, list) and all(isinstance(t, str) and (not tax_ids or t in tax_ids) for t in pt):
                            new_top_valid = 1
                        else:
                            new_top_valid = 0
                    except Exception:
                        new_top_valid = 0

                    clean_s = (pred_sentiment_str or "").strip().lower()
                    new_sent_valid = 1 if clean_s in VALID_SENTIMENTS else 0

                    new_rev_valid = 1 if pred_needs_review_val in (0, 1) else 0
                else:
                    new_top_valid = 0
                    new_sent_valid = 0
                    new_rev_valid = 0
        else:
            new_top_valid = 0
            new_sent_valid = 0
            new_rev_valid = 0

        if (curr_top_valid != new_top_valid or
            curr_sent_valid != new_sent_valid or
            curr_rev_valid != new_rev_valid):
            updates.append((new_top_valid, new_sent_valid, new_rev_valid, pid))

    if updates:
        await db.executemany(
            "UPDATE baseline_predictions SET topics_valid = ?, sentiment_valid = ?, needs_review_valid = ? WHERE id = ?",
            updates
        )

    await db.execute(
        "INSERT OR REPLACE INTO system_config (key, value) VALUES ('field_validity_backfilled', 'true')"
    )

async def mark_interrupted_baseline_batches():
    """Mark any baseline batches left in running or queued state as interrupted upon server restart."""
    now = get_now_iso()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
            UPDATE baseline_batches
            SET status = 'interrupted',
                error_message = 'Backend restarted while batch was running. Rows processed before interruption are preserved.',
                updated_at = ?
            WHERE status IN ('running', 'queued')
        """, (now,))
        await db.commit()
