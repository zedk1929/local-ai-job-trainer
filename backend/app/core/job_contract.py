from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class JobConfigSchema(BaseModel):
    survey_context_label: str = "Survey Context"
    survey_context_description: str = "Describe what this survey measures, who was asked, and any background."
    default_taxonomy: List[Dict[str, str]] = []
    default_rules: List[str] = []

class MetricDefinition(BaseModel):
    id: str
    name: str
    description: str
    unit: str = "%" # "%", "0-1", "count"
    higher_is_better: bool = True

class TrainingOptionSchema(BaseModel):
    learning_rate: float = 2e-4
    epochs: int = 3
    batch_size: int = 4
    lora_r: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    target_modules: List[str] = ["q_proj", "v_proj"]

class JobDefinition(BaseModel):
    id: str
    title: str
    version: str
    description: str
    config_schema: JobConfigSchema
    supported_models: List[str] = ["llama", "mistral", "qwen", "gemma"]
    supported_backends: List[str] = ["peft_lora", "mlx", "mock"]
    metrics: List[MetricDefinition]
    default_training_options: TrainingOptionSchema = Field(default_factory=TrainingOptionSchema)

    # Prompt builders and validation
    def build_supervisor_prompt(self, context: str, taxonomy: List[Dict[str, str]], rules: List[str], count: int = 10) -> str:
        raise NotImplementedError

    def build_baseline_inference_prompt(self, response_text: str, context: str, taxonomy: List[Dict[str, str]], rules: List[str]) -> str:
        raise NotImplementedError

    def validate_output(self, raw_output: Dict[str, Any], taxonomy: List[Dict[str, str]]) -> Dict[str, Any]:
        """Validate output conforms strictly to job schema."""
        raise NotImplementedError
