import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)

STAGES = [
    "check_setup",
    "prepare_examples",
    "measure_baseline",
    "train_adapter",
    "evaluate_candidate",
    "save_result"
]

class TrainingBackend:
    def __init__(self, runs_dir: Optional[Path] = None):
        self.runs_dir = runs_dir or settings.runs_dir
        self.active_tasks: Dict[str, asyncio.Task] = {}

    def is_training_available(self, model_info: Dict[str, Any]) -> (bool, str):
        """Check if hardware and model format allow local LoRA training."""
        if not model_info.get("model_configured", False):
            return False, "No local model configured. Real training unavailable; running in Preview mode."
        if not model_info.get("training_supported", False):
            return False, "Model is configured for inference only (e.g. GGUF or remote endpoint). Trainable weights (safetensors/PyTorch) required for training."
        return True, "Training environment validated."

    def cancel_run(self, run_id: str) -> bool:
        if run_id in self.active_tasks:
            task = self.active_tasks[run_id]
            task.cancel()
            logger.info(f"Canceled training task for run {run_id}")
            return True
        return False
