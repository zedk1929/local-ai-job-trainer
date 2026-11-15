import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RUNS_DIR = BASE_DIR / "runs"
UPLOADS_DIR = DATA_DIR / "uploads"
SAMPLE_CSV_PATH = DATA_DIR / "sample_survey_labeled.csv"
DEV_SAMPLE_CSV_PATH = DATA_DIR / "dev_survey_60_labeled.csv"

DATA_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

class Settings(BaseModel):
    app_name: str = "Local AI Job Trainer"
    app_mode: str = os.getenv("APP_MODE", "preview") # "preview" or "connected"
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    data_dir: Path = DATA_DIR
    DATA_DIR: Path = DATA_DIR # Backward-compatibility alias
    uploads_dir: Path = UPLOADS_DIR
    sample_csv_path: Path = SAMPLE_CSV_PATH
    dev_sample_csv_path: Path = DEV_SAMPLE_CSV_PATH
    db_path: Path = DATA_DIR / "trainer.sqlite3"
    runs_dir: Path = RUNS_DIR

    # Supervisor configuration
    supervisor_provider: str = os.getenv("SUPERVISOR_PROVIDER", "gemini")
    supervisor_model: str = os.getenv("SUPERVISOR_MODEL", "claude-sonnet-5-5" if os.getenv("SUPERVISOR_PROVIDER") == "anthropic" else "gemini-3.8-flash")
    supervisor_api_key: str = os.getenv("SUPERVISOR_API_KEY", "")

    # Local model configuration
    local_model_path: str = os.getenv("LOCAL_MODEL_PATH", "")
    local_model_endpoint: str = os.getenv("LOCAL_MODEL_ENDPOINT", "http://127.0.0.1:11434")
    local_model_name: str = os.getenv("LOCAL_MODEL_NAME", "")

    # Training backend
    training_backend: str = os.getenv("TRAINING_BACKEND", "mock")

settings = Settings()
