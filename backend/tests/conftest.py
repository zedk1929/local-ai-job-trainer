import pytest
import asyncio
from pathlib import Path
from app.config import settings
from app.database import init_db

@pytest.fixture(autouse=True)
def isolate_environment(tmp_path: Path):
    """
    Ensure every test runs against clean, isolated temporary SQLite database
    and temporary uploads/runs storage so user projects, datasets, and runs
    are never modified.
    """
    original_db_path = settings.db_path
    original_uploads_dir = settings.uploads_dir
    original_data_dir = settings.data_dir
    original_runs_dir = settings.runs_dir
    original_app_mode = settings.app_mode
    original_model_name = settings.local_model_name
    original_endpoint = settings.local_model_endpoint

    settings.db_path = tmp_path / "test_trainer.sqlite3"
    settings.data_dir = tmp_path / "data"
    settings.uploads_dir = tmp_path / "uploads"
    settings.runs_dir = tmp_path / "runs"
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.runs_dir.mkdir(parents=True, exist_ok=True)

    asyncio.run(init_db())

    yield

    settings.db_path = original_db_path
    settings.uploads_dir = original_uploads_dir
    settings.data_dir = original_data_dir
    settings.runs_dir = original_runs_dir
    settings.app_mode = original_app_mode
    settings.local_model_name = original_model_name
    settings.local_model_endpoint = original_endpoint
