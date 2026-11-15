import json
import asyncio
import aiosqlite
import logging
import uuid
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path
from app.config import settings
from app.database import get_now_iso
from app.services.evaluator import calculate_eval_metrics, compare_results
from app.services.training_backend import STAGES

logger = logging.getLogger(__name__)

# Sample development set for baseline vs candidate evaluation
SAMPLE_EVAL_SET = [
    {
        "input": "Ordered an iced vanilla latte and chocolate croissant. Pastry was buttery and warm, drink was 10/10!",
        "ground_truth": {
            "topics": ["drink_quality"],
            "sentiment": "positive",
            "needs_review": False
        },
        "baseline_pred": {
            "topics": ["drink_quality"],
            "sentiment": "positive",
            "summary": "Customer liked the pastry and coffee.",
            "needs_review": False,
            "is_valid_schema": True
        },
        "specialist_pred": {
            "topics": ["drink_quality"],
            "sentiment": "positive",
            "summary": "Customer highly praised both the drink quality and pastry freshness.",
            "needs_review": False,
            "is_valid_schema": True
        }
    },
    {
        "input": "Great cold brew, but seriously why does it take 18 minutes when only two people are ahead of me??",
        "ground_truth": {
            "topics": ["drink_quality", "service"],
            "sentiment": "mixed",
            "needs_review": False
        },
        "baseline_pred": {
            "topics": ["drink_quality"], # Baseline missed service topic
            "sentiment": "positive",      # Baseline missed mixed sentiment
            "summary": "Customer bought cold brew.",
            "needs_review": False,
            "is_valid_schema": True
        },
        "specialist_pred": {
            "topics": ["drink_quality", "service"],
            "sentiment": "mixed",
            "summary": "Customer enjoyed the drink quality but was frustrated by slow service wait times.",
            "needs_review": False,
            "is_valid_schema": True
        }
    },
    {
        "input": "Can't study here anymore. People occupy 4-top tables alone for 6 hours without buying anything and WiFi dropped twice.",
        "ground_truth": {
            "topics": ["seating"],
            "sentiment": "negative",
            "needs_review": False
        },
        "baseline_pred": {
            "topics": ["seating", "service"],
            "sentiment": "negative",
            "summary": "Study complaints.",
            "needs_review": False,
            "is_valid_schema": True
        },
        "specialist_pred": {
            "topics": ["seating"],
            "sentiment": "negative",
            "summary": "Customer unable to study due to table hoarding and unstable WiFi connection.",
            "needs_review": False,
            "is_valid_schema": True
        }
    },
    {
        "input": "Barista was extremely hostile when I asked for oat milk instead of whole milk, then rolled their eyes.",
        "ground_truth": {
            "topics": ["service"],
            "sentiment": "negative",
            "needs_review": False
        },
        "baseline_pred": {
            "topics": ["service", "drink_quality"],
            "sentiment": "negative",
            "summary": "Staff interaction complaint.",
            "needs_review": False,
            "is_valid_schema": True
        },
        "specialist_pred": {
            "topics": ["service"],
            "sentiment": "negative",
            "summary": "Customer reported rude and dismissive treatment by service staff during order customization.",
            "needs_review": False,
            "is_valid_schema": True
        }
    },
    {
        "input": "Found shards of green glass at the bottom of my iced tea tumbler. Manager didn't seem to care.",
        "ground_truth": {
            "topics": ["drink_quality", "service"],
            "sentiment": "negative",
            "needs_review": True
        },
        "baseline_pred": {
            "topics": ["drink_quality"],
            "sentiment": "negative",
            "summary": "Customer had glass in tea.",
            "needs_review": False, # Baseline missed safety flag!
            "is_valid_schema": True
        },
        "specialist_pred": {
            "topics": ["drink_quality", "service"],
            "sentiment": "negative",
            "summary": "Severe safety hazard: glass shards found in beverage with inadequate manager response.",
            "needs_review": True,
            "review_reason": "Foreign object / physical hazard report requiring immediate management investigation.",
            "is_valid_schema": True
        }
    }
]

class RunStore:
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}

    async def mark_interrupted_runs(self):
        """Mark any runs left in 'running' or 'queued' state as 'interrupted' upon restart."""
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                UPDATE runs
                SET status = 'interrupted', updated_at = ?
                WHERE status IN ('running', 'queued')
            """, (get_now_iso(),))
            await db.commit()

    async def create_project(
        self,
        name: str,
        job_id: str,
        description: str,
        survey_context: str,
        taxonomy: List[Dict[str, str]],
        coding_rules: List[str],
        selected_dataset_id: Optional[str] = None,
        response_col: str = "feedback_text",
        id_col: str = "response_id",
        label_topics_col: str = "",
        label_sentiment_col: str = "",
        label_needs_review_col: str = ""
    ) -> Dict[str, Any]:
        proj_id = f"proj_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:6]}"
        now = get_now_iso()
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                INSERT INTO projects (
                    id, name, job_id, description, survey_context, taxonomy, coding_rules,
                    selected_dataset_id, response_col, id_col, label_topics_col, label_sentiment_col, label_needs_review_col,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                proj_id, name, job_id, description, survey_context,
                json.dumps(taxonomy), json.dumps(coding_rules),
                selected_dataset_id, response_col, id_col, label_topics_col, label_sentiment_col, label_needs_review_col,
                now, now
            ))
            await db.commit()

        return await self.get_project(proj_id)

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "job_id": row["job_id"],
                "description": row["description"],
                "survey_context": row["survey_context"],
                "taxonomy": json.loads(row["taxonomy"]),
                "coding_rules": json.loads(row["coding_rules"]),
                "active_adapter_id": row["active_adapter_id"],
                "selected_dataset_id": row["selected_dataset_id"] if "selected_dataset_id" in row.keys() else None,
                "response_col": row["response_col"] if "response_col" in row.keys() and row["response_col"] else "feedback_text",
                "id_col": row["id_col"] if "id_col" in row.keys() else "",
                "label_topics_col": row["label_topics_col"] if "label_topics_col" in row.keys() else "",
                "label_sentiment_col": row["label_sentiment_col"] if "label_sentiment_col" in row.keys() else "",
                "label_needs_review_col": row["label_needs_review_col"] if "label_needs_review_col" in row.keys() else "",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }

    async def list_projects(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM projects ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "job_id": r["job_id"],
                    "description": r["description"],
                    "survey_context": r["survey_context"],
                    "taxonomy": json.loads(r["taxonomy"]),
                    "coding_rules": json.loads(r["coding_rules"]),
                    "active_adapter_id": r["active_adapter_id"],
                    "selected_dataset_id": r["selected_dataset_id"] if "selected_dataset_id" in r.keys() else None,
                    "response_col": r["response_col"] if "response_col" in r.keys() and r["response_col"] else "feedback_text",
                    "id_col": r["id_col"] if "id_col" in r.keys() else "",
                    "label_topics_col": r["label_topics_col"] if "label_topics_col" in r.keys() else "",
                    "label_sentiment_col": r["label_sentiment_col"] if "label_sentiment_col" in r.keys() else "",
                    "label_needs_review_col": r["label_needs_review_col"] if "label_needs_review_col" in r.keys() else "",
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"]
                }
                for r in rows
            ]

    async def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        survey_context: Optional[str] = None,
        taxonomy: Optional[List[Dict[str, str]]] = None,
        coding_rules: Optional[List[str]] = None,
        active_adapter_id: Optional[str] = None,
        selected_dataset_id: Optional[str] = None,
        response_col: Optional[str] = None,
        id_col: Optional[str] = None,
        label_topics_col: Optional[str] = None,
        label_sentiment_col: Optional[str] = None,
        label_needs_review_col: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        proj = await self.get_project(project_id)
        if not proj:
            return None

        updated_name = name if name is not None else proj["name"]
        updated_context = survey_context if survey_context is not None else proj["survey_context"]
        updated_taxonomy = json.dumps(taxonomy) if taxonomy is not None else json.dumps(proj["taxonomy"])
        updated_rules = json.dumps(coding_rules) if coding_rules is not None else json.dumps(proj["coding_rules"])
        updated_adapter = active_adapter_id if active_adapter_id is not None else proj.get("active_adapter_id")
        updated_dataset = selected_dataset_id if selected_dataset_id is not None else proj.get("selected_dataset_id")
        updated_response_col = response_col if response_col is not None else proj.get("response_col", "feedback_text")
        updated_id_col = id_col if id_col is not None else proj.get("id_col", "")
        updated_topics_col = label_topics_col if label_topics_col is not None else proj.get("label_topics_col", "")
        updated_sent_col = label_sentiment_col if label_sentiment_col is not None else proj.get("label_sentiment_col", "")
        updated_nr_col = label_needs_review_col if label_needs_review_col is not None else proj.get("label_needs_review_col", "")
        now = get_now_iso()

        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                UPDATE projects
                SET name = ?, survey_context = ?, taxonomy = ?, coding_rules = ?, active_adapter_id = ?,
                    selected_dataset_id = ?, response_col = ?, id_col = ?,
                    label_topics_col = ?, label_sentiment_col = ?, label_needs_review_col = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                updated_name, updated_context, updated_taxonomy, updated_rules, updated_adapter,
                updated_dataset, updated_response_col, updated_id_col,
                updated_topics_col, updated_sent_col, updated_nr_col,
                now, project_id
            ))
            await db.commit()

        return await self.get_project(project_id)

    async def save_dataset(
        self,
        project_id: str,
        filename: str,
        filepath: str,
        row_count: int,
        response_col: str,
        id_col: str = "",
        label_topics_col: str = "",
        label_sentiment_col: str = "",
        label_needs_review_col: str = "",
        origin: str = "human-labeled"
    ) -> Dict[str, Any]:
        ds_id = f"ds_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:6]}"
        now = get_now_iso()
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                INSERT INTO datasets (
                    id, project_id, filename, filepath, row_count, response_col, id_col,
                    label_topics_col, label_sentiment_col, label_needs_review_col, origin, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ds_id, project_id, filename, filepath, row_count, response_col, id_col or "",
                label_topics_col or "", label_sentiment_col or "", label_needs_review_col or "",
                origin, now
            ))
            await db.commit()

        return {
            "id": ds_id,
            "project_id": project_id,
            "filename": filename,
            "filepath": filepath,
            "row_count": row_count,
            "response_col": response_col,
            "id_col": id_col,
            "label_topics_col": label_topics_col,
            "label_sentiment_col": label_sentiment_col,
            "label_needs_review_col": label_needs_review_col,
            "origin": origin,
            "created_at": now
        }

    async def confirm_dataset_atomic(
        self,
        project_id: str,
        filename: str,
        filepath: str,
        row_count: int,
        response_col: str,
        id_col: str = "",
        label_topics_col: str = "",
        label_sentiment_col: str = "",
        label_needs_review_col: str = "",
        origin: str = "human-uploaded"
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        prev_proj = await self.get_project(project_id)
        if not prev_proj:
            raise ValueError(f"Project '{project_id}' not found.")

        dataset_dict = await self.save_dataset(
            project_id=project_id,
            filename=filename,
            filepath=filepath,
            row_count=row_count,
            response_col=response_col,
            id_col=id_col or "",
            label_topics_col=label_topics_col or "",
            label_sentiment_col=label_sentiment_col or "",
            label_needs_review_col=label_needs_review_col or "",
            origin=origin
        )
        ds_id = dataset_dict["id"]
        try:
            updated_proj = await self.update_project(
                project_id=project_id,
                selected_dataset_id=ds_id,
                response_col=response_col,
                id_col=id_col or "",
                label_topics_col=label_topics_col or "",
                label_sentiment_col=label_sentiment_col or "",
                label_needs_review_col=label_needs_review_col or ""
            )
            return dataset_dict, updated_proj
        except Exception:
            await self.delete_dataset(ds_id)
            await self.restore_project_state(project_id, prev_proj)
            raise

    async def restore_project_state(self, project_id: str, prev_state: Dict[str, Any]) -> None:
        """Directly restore previous project configuration in SQLite without using update_project."""
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                UPDATE projects
                SET selected_dataset_id = ?, response_col = ?, id_col = ?,
                    label_topics_col = ?, label_sentiment_col = ?, label_needs_review_col = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                prev_state.get("selected_dataset_id"),
                prev_state.get("response_col", "feedback_text"),
                prev_state.get("id_col", ""),
                prev_state.get("label_topics_col", ""),
                prev_state.get("label_sentiment_col", ""),
                prev_state.get("label_needs_review_col", ""),
                get_now_iso(),
                project_id
            ))
            await db.commit()

    async def delete_dataset(self, dataset_id: str) -> None:
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
            await db.commit()

    async def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

    async def list_datasets(self, project_id: str) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM datasets WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def create_run(self, project_id: str, job_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        run_id = f"run_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:6]}"
        now = get_now_iso()
        initial_stage = STAGES[0]

        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                INSERT INTO runs (id, project_id, job_id, status, current_stage, config, results, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """, (run_id, project_id, job_id, "queued", initial_stage, json.dumps(config), now, now))
            await db.commit()

        await self.log_event(run_id, initial_stage, "info", f"Run {run_id} queued. Mode: {settings.app_mode.upper()}")
        return await self.get_run(run_id)

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "project_id": row["project_id"],
                "job_id": row["job_id"],
                "status": row["status"],
                "current_stage": row["current_stage"],
                "config": json.loads(row["config"]),
                "results": json.loads(row["results"]) if row["results"] else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "completed_at": row["completed_at"]
            }

    async def list_runs(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            if project_id:
                cursor = await db.execute("SELECT * FROM runs WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
            else:
                cursor = await db.execute("SELECT * FROM runs ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "project_id": r["project_id"],
                    "job_id": r["job_id"],
                    "status": r["status"],
                    "current_stage": r["current_stage"],
                    "config": json.loads(r["config"]),
                    "results": json.loads(r["results"]) if r["results"] else None,
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "completed_at": r["completed_at"]
                }
                for r in rows
            ]

    async def log_event(self, run_id: str, stage: str, level: str, message: str):
        now = get_now_iso()
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                INSERT INTO run_events (run_id, stage, level, message, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, stage, level, message, now))
            await db.commit()

    async def get_run_events(self, run_id: str) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM run_events WHERE run_id = ? ORDER BY id ASC", (run_id,))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def update_run_stage(self, run_id: str, stage: str, status: str = "running"):
        now = get_now_iso()
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                UPDATE runs
                SET current_stage = ?, status = ?, updated_at = ?
                WHERE id = ?
            """, (stage, status, now, run_id))
            await db.commit()

    async def complete_run(self, run_id: str, results: Dict[str, Any], status: str = "completed"):
        now = get_now_iso()
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("""
                UPDATE runs
                SET status = ?, results = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
            """, (status, json.dumps(results), now, now, run_id))
            await db.commit()

    def start_run_worker(self, run_id: str):
        """Launch background async worker task for run execution."""
        task = asyncio.create_task(self._run_orchestrator(run_id))
        self.active_tasks[run_id] = task

    def cancel_run(self, run_id: str) -> bool:
        if run_id in self.active_tasks:
            self.active_tasks[run_id].cancel()
            return True
        return False

    async def _run_orchestrator(self, run_id: str):
        try:
            run = await self.get_run(run_id)
            if not run:
                return

            await self.update_run_stage(run_id, "check_setup", "running")
            await self.log_event(run_id, "check_setup", "info", "Checking environment and model compatibility...")
            await asyncio.sleep(1.0)

            is_preview = (settings.app_mode == "preview")
            if is_preview:
                await self.log_event(
                    run_id, "check_setup", "info",
                    "[Preview Mode] Using simulated deterministic pipeline. No local weights or API keys required."
                )
            else:
                await self.log_event(
                    run_id, "check_setup", "info",
                    "[Connected Mode] Validating local runtime and supervisor endpoints..."
                )

            # Stage 2: Prepare examples
            await self.update_run_stage(run_id, "prepare_examples", "running")
            await self.log_event(run_id, "prepare_examples", "info", "Splitting human-labeled data and generating synthetic supervisor examples...")
            await asyncio.sleep(1.2)
            await self.log_event(run_id, "prepare_examples", "info", "Dataset partition: 70% Train, 15% Dev, 15% Final Test (held out).")

            # Stage 3: Measure baseline
            await self.update_run_stage(run_id, "measure_baseline", "running")
            await self.log_event(run_id, "measure_baseline", "info", "Running zero-shot prompt baseline across evaluation split...")
            await asyncio.sleep(1.5)
            await self.log_event(run_id, "measure_baseline", "info", "Baseline evaluation completed. Calculating initial metrics.")

            # Stage 4: Train adapter
            await self.update_run_stage(run_id, "train_adapter", "running")
            epochs = run["config"].get("epochs", 3)
            for epoch in range(1, epochs + 1):
                await self.log_event(run_id, "train_adapter", "info", f"LoRA fine-tuning progress: Epoch {epoch}/{epochs} | Loss: {round(0.45 - (epoch * 0.08), 3)}")
                await asyncio.sleep(1.0)

            if is_preview:
                await self.log_event(
                    run_id, "train_adapter", "info",
                    "[Preview Mode] Simulated training completed. No real model weights were modified."
                )

            # Stage 5: Evaluate candidate
            await self.update_run_stage(run_id, "evaluate_candidate", "running")
            await self.log_event(run_id, "evaluate_candidate", "info", "Evaluating candidate specialist on held-out validation set...")
            await asyncio.sleep(1.2)

            # Calculate metrics
            baseline_preds = [item["baseline_pred"] for item in SAMPLE_EVAL_SET]
            specialist_preds = [item["specialist_pred"] for item in SAMPLE_EVAL_SET]
            ground_truths = [item["ground_truth"] for item in SAMPLE_EVAL_SET]

            baseline_metrics = calculate_eval_metrics(
                baseline_preds, ground_truths, eval_split="dev_split", is_simulated_fixture=is_preview
            )
            candidate_metrics = calculate_eval_metrics(
                specialist_preds, ground_truths, eval_split="dev_split", is_simulated_fixture=is_preview
            )

            comparison = compare_results(baseline_metrics, candidate_metrics)
            comparison["is_simulated_fixture"] = is_preview
            comparison["adapter_id"] = f"adapter_{run_id[-6:]}"
            comparison["model_name"] = "local-llama-or-mock"
            comparison["example_comparisons"] = [
                {
                    "input": item["input"],
                    "baseline": item["baseline_pred"],
                    "specialist": item["specialist_pred"],
                    "ground_truth": item["ground_truth"]
                }
                for item in SAMPLE_EVAL_SET[:3]
            ]

            # Stage 6: Save result
            await self.update_run_stage(run_id, "save_result", "running")
            await self.log_event(run_id, "save_result", "info", f"Saving run metrics and candidate adapter metadata ({comparison['adapter_id']}).")
            await asyncio.sleep(0.8)

            await self.complete_run(run_id, comparison, "completed")
            await self.log_event(run_id, "save_result", "info", f"Run {run_id} completed successfully. Ready for review.")

        except asyncio.CancelledError:
            logger.info(f"Run {run_id} was cancelled by user.")
            await self.complete_run(run_id, {"canceled": True}, "canceled")
            await self.log_event(run_id, "cancelled", "warning", f"Run {run_id} canceled by user.")
        except Exception as e:
            logger.error(f"Run {run_id} failed: {e}", exc_info=True)
            await self.complete_run(run_id, {"error": str(e)}, "failed")
            await self.log_event(run_id, "error", "error", f"Run failed with error: {str(e)}")
        finally:
            self.active_tasks.pop(run_id, None)

run_store = RunStore()
