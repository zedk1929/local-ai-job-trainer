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

        # Migration column checks for existing databases
        await _ensure_columns(db)

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
        ("is_simulated", "INTEGER DEFAULT 0"),
        ("model_name", "TEXT DEFAULT ''")
    ]
    for cname, ctype in new_pred_cols:
        if cname not in cols:
            try:
                await db.execute(f"ALTER TABLE baseline_predictions ADD COLUMN {cname} {ctype}")
            except Exception:
                pass

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
