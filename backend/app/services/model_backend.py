import os
import re
import httpx
import json
import logging
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class ModelServiceError(Exception):
    """Raised when the local model service fails or is misconfigured."""
    pass

class ModelNotFoundError(ModelServiceError):
    """Raised when the specified model is not available in the local runtime."""
    pass

class LocalModelBackend:
    def __init__(
        self,
        model_path: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        model_name: Optional[str] = None,
        app_mode: Optional[str] = None
    ):
        self.model_path = model_path if model_path is not None else settings.local_model_path
        self.endpoint_url = endpoint_url if endpoint_url is not None else settings.local_model_endpoint
        self.model_name = model_name if model_name is not None else (settings.local_model_name or "qwen2.5-coder:3b")
        self.app_mode = app_mode if app_mode is not None else settings.app_mode
        self.active_adapter: Optional[str] = None

    async def list_available_ollama_models(self) -> List[str]:
        """Fetch list of models currently installed in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(f"{self.endpoint_url.rstrip('/')}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    return [m.get("name") for m in data.get("models", []) if m.get("name")]
        except Exception as e:
            logger.warning(f"Failed to query Ollama models at {self.endpoint_url}: {e}")
        return []

    async def inspect_capabilities(self) -> Dict[str, Any]:
        """Inspect the model environment, distinguishing inference from training."""
        status = {
            "model_configured": False,
            "model_name": self.model_name or "qwen2.5-coder:3b",
            "model_path": self.model_path or "None",
            "endpoint_url": self.endpoint_url or "http://127.0.0.1:11434",
            "inference_available": False,
            "training_supported": False,
            "active_adapter": self.active_adapter,
            "available_models": [],
            "notes": []
        }

        # Check local HTTP inference endpoint (Ollama)
        if self.endpoint_url:
            available_models = await self.list_available_ollama_models()
            status["available_models"] = available_models

            if available_models:
                status["model_configured"] = True
                status["inference_available"] = True
                status["notes"].append(
                    f"Connected to local Ollama runtime at {self.endpoint_url}. Available: {', '.join(available_models)}"
                )

                # Check if configured model exists in Ollama
                matches = [m for m in available_models if m == self.model_name or m.startswith(f"{self.model_name}:")]
                if matches:
                    status["notes"].append(f"Configured model '{self.model_name}' is verified and ready for inference.")
                else:
                    status["notes"].append(
                        f"Configured model '{self.model_name}' is NOT present in Ollama. "
                        f"Please run 'ollama pull {self.model_name}'. No models will be downloaded automatically."
                    )
            else:
                status["notes"].append(f"Unable to reach local Ollama runtime at {self.endpoint_url}.")

        # Check local file path if configured
        if self.model_path:
            p = Path(self.model_path)
            if p.exists():
                status["model_configured"] = True
                status["notes"].append(f"Model path verified on disk: {p.name}")
                if p.suffix.lower() == ".gguf":
                    status["inference_available"] = True
                    status["training_supported"] = False
                    status["notes"].append("GGUF format detected: provides inference, but requires trainable weights (e.g. safetensors/HF) for LoRA fine-tuning.")
                elif p.is_dir() or p.suffix.lower() in [".safetensors", ".bin"]:
                    status["inference_available"] = True
                    status["training_supported"] = True
                    status["notes"].append("Weights directory / safetensors detected: compatible with PEFT/LoRA training backend.")
            else:
                status["notes"].append(f"Specified model path does not exist: {self.model_path}")

        return status

    def load_adapter(self, adapter_id: str):
        self.active_adapter = adapter_id
        logger.info(f"Loaded adapter: {adapter_id}")

    def unload_adapter(self):
        self.active_adapter = None
        logger.info("Unloaded adapter, reverted to baseline base model.")

    def build_strong_baseline_prompt(
        self,
        response_text: str,
        context: str,
        taxonomy: List[Dict[str, str]],
        rules: List[str]
    ) -> str:
        """
        Construct a strong zero-shot baseline prompt incorporating survey context,
        complete category definitions, and coding rules.
        Explicitly supports multiple topics, ambiguous feedback, and strict JSON output.
        """
        tax_lines = []
        for cat in taxonomy:
            cid = cat.get("id", "")
            cname = cat.get("name", cid)
            cdesc = cat.get("description", "")
            tax_lines.append(f"  - ID: \"{cid}\" | Name: \"{cname}\" | Description: {cdesc}")
        tax_str = "\n".join(tax_lines)

        rules_str = "\n".join(f"  {idx+1}. {r}" for idx, r in enumerate(rules))

        return f"""You are an expert survey data analyst specializing in customer feedback categorization.
Your job is to read raw survey feedback and transform it into a structured record strictly adhering to the specified taxonomy and coding rules.

### SURVEY CONTEXT:
{context}

### ALLOWED TOPIC TAXONOMY:
{tax_str}

### CODING RULES:
{rules_str}
  - Multiple Topics: Assign ALL matching topic IDs from the taxonomy above. A response may mention 0, 1, or multiple topics. Output topic IDs as an array of strings. Do NOT invent new topic IDs.
  - Sentiment: Must be strictly one of: "positive", "negative", "mixed", "neutral", "unclear".
    * If both positive and negative aspects are mentioned, use "mixed".
    * If incomprehensible, gibberish, or vague, use "unclear".
  - Needs Review: Set needs_review to true if the feedback reports an unresolved safety incident, physical hazard, severe hygiene issue, harassment, or if text is completely unintelligible. Otherwise false.
  - Summary: Write a concise, 1-sentence factual summary of the feedback. Do not extrapolate or add unmentioned details.

### RAW SURVEY RESPONSE TO CATEGORIZE:
"{response_text}"

### OUTPUT FORMAT:
Respond ONLY with a valid JSON object matching this exact schema:
{{
  "topics": ["topic_id_1", "topic_id_2"],
  "sentiment": "positive",
  "summary": "1-sentence factual summary",
  "needs_review": false,
  "review_reason": null
}}"""

    async def infer_single_real(
        self,
        response_text: str,
        context: str,
        taxonomy: List[Dict[str, str]],
        rules: List[str],
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
        endpoint_url: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Call the real Ollama local model with retries, timeout, and strict validation.
        NEVER returns simulated fixtures on failure.
        """
        target_endpoint = endpoint_url or self.endpoint_url
        target_model_name = model_name or self.model_name

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(f"{target_endpoint.rstrip('/')}/api/tags")
                if resp.status_code == 200:
                    available = [m.get("name") for m in resp.json().get("models", []) if m.get("name")]
                else:
                    available = []
        except Exception as e:
            raise ModelServiceError(
                f"Cannot connect to Ollama at {target_endpoint}: {e}. Please ensure Ollama is running."
            )

        if not available:
            raise ModelServiceError(
                f"Cannot connect to Ollama at {target_endpoint}. Please ensure Ollama is running."
            )

        # Check if configured model exists
        matches = [m for m in available if m == target_model_name or m.startswith(f"{target_model_name}:")]
        if not matches:
            raise ModelNotFoundError(
                f"Model '{target_model_name}' is not installed in local Ollama at {target_endpoint}. "
                f"Available models: {', '.join(available)}. "
                f"Please install it using 'ollama pull {target_model_name}'."
            )

        target_model = matches[0]
        prompt = self.build_strong_baseline_prompt(response_text, context, taxonomy, rules)

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                t0 = time.perf_counter()
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    resp = await client.post(
                        f"{target_endpoint.rstrip('/')}/api/generate",
                        json={
                            "model": target_model,
                            "prompt": prompt,
                            "stream": False,
                            "format": "json",
                            "options": {
                                "temperature": 0.0,
                                "num_predict": 256
                            }
                        }
                    )
                    latency = round(time.perf_counter() - t0, 3)

                    if resp.status_code != 200:
                        raise ModelServiceError(
                            f"Ollama returned HTTP status {resp.status_code}: {resp.text[:300]}"
                        )

                    data = resp.json()
                    raw_text = data.get("response", "")

                    is_strict_json = False
                    has_markdown_fence = False
                    parsed = None

                    try:
                        parsed = json.loads(raw_text.strip())
                        is_strict_json = True
                    except (json.JSONDecodeError, TypeError):
                        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text.strip(), flags=re.IGNORECASE)
                        if fence_match:
                            has_markdown_fence = True
                            try:
                                parsed = json.loads(fence_match.group(1).strip())
                            except (json.JSONDecodeError, TypeError):
                                parsed = None
                        elif raw_text.strip().startswith("```"):
                            has_markdown_fence = True
                            cleaned = raw_text.replace("```json", "").replace("```", "").strip()
                            try:
                                parsed = json.loads(cleaned)
                            except (json.JSONDecodeError, TypeError):
                                parsed = None
                        else:
                            parsed = None

                    parsed_dict = parsed if isinstance(parsed, dict) else {}

                    result = {
                        **parsed_dict,
                        "raw_model_text": raw_text,
                        "is_strict_json": is_strict_json,
                        "has_markdown_fence": has_markdown_fence,
                        "is_valid_json": isinstance(parsed, dict),
                        "is_simulated_fixture": False,
                        "model_used": target_model,
                        "adapter_used": None,
                        "latency_seconds": latency
                    }
                    return result

            except (httpx.TimeoutException, httpx.NetworkError, Exception) as err:
                last_error = err
                logger.warning(f"Ollama inference attempt {attempt + 1}/{max_retries + 1} failed: {err}")
                if attempt < max_retries:
                    await asyncio.sleep(0.8 * (attempt + 1))

        raise ModelServiceError(f"Inference failed after {max_retries + 1} attempts: {str(last_error)}")

    async def infer_single(
        self,
        response_text: str,
        context: str,
        taxonomy: List[Dict[str, str]],
        rules: List[str],
        use_adapter: bool = False,
        app_mode: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        High-level inference dispatcher.
        Uses the explicit/frozen app_mode (or instance app_mode), NOT mutable global settings.
        If mode is connected, calls real model and fails honestly if unavailable.
        If mode is preview, returns deterministic sample fixtures.
        """
        effective_mode = app_mode or self.app_mode
        if effective_mode == "connected":
            return await self.infer_single_real(
                response_text=response_text,
                context=context,
                taxonomy=taxonomy,
                rules=rules,
                endpoint_url=endpoint_url or self.endpoint_url,
                model_name=model_name or self.model_name
            )
        else:
            return self._generate_preview_prediction(
                text=response_text,
                taxonomy=taxonomy,
                rules=rules,
                use_adapter=use_adapter,
                model_name=model_name or self.model_name
            )

    def _generate_preview_prediction(
        self,
        text: str,
        taxonomy: List[Dict[str, str]],
        rules: List[str],
        use_adapter: bool,
        model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Deterministic heuristic for preview mode that clearly labels fixtures."""
        lower = text.lower()
        topics = []
        sentiment = "neutral"
        summary = ""
        needs_review = False
        review_reason = None

        has_drink = any(w in lower for w in ["coffee", "latte", "cappuccino", "espresso", "matcha", "drink", "taste", "flavor"])
        has_price = any(w in lower for w in ["price", "$", "expensive", "cheap", "cost", "steep", "affordable", "worth"])
        has_service = any(w in lower for w in ["staff", "barista", "slow", "fast", "wait", "minutes", "friendly", "rude", "line"])
        has_seating = any(w in lower for w in ["seat", "table", "chair", "outlet", "plug", "wifi", "noisy", "loud", "crowded"])

        if has_drink:
            topics.append("drink_quality")
        if has_price:
            topics.append("price")
        if has_service:
            topics.append("service")
        if has_seating:
            topics.append("seating")

        has_flag = any(w in lower for w in ["rusty", "hair", "insect", "glass", "hazard", "food poisoning", "scone", "paperclip", "harass"])
        if has_flag:
            needs_review = True
            review_reason = "Flagged: customer mentions severe quality or hygiene incident."

        has_pos = any(w in lower for w in ["great", "silky", "perfect", "good", "love", "cheerful", "fast", "amazing"])
        has_neg = any(w in lower for w in ["steep", "expensive", "slow", "deafening", "cold", "couldn't", "terrible", "bad", "shrugged", "zero"])

        if has_pos and has_neg:
            sentiment = "mixed"
        elif has_pos:
            sentiment = "positive"
        elif has_neg:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        if not use_adapter:
            if len(topics) > 1:
                topics = [topics[0]]
            summary = f"The respondent mentioned: {text[:60]}..."
        else:
            summary = f"Customer provided feedback covering {', '.join(topics) if topics else 'general feedback'}."

        preview_payload = {
            "topics": topics,
            "sentiment": sentiment,
            "summary": summary,
            "needs_review": needs_review,
            "review_reason": review_reason
        }
        return {
            "original_response": text,
            **preview_payload,
            "raw_model_text": json.dumps(preview_payload),
            "is_strict_json": True,
            "has_markdown_fence": False,
            "is_valid_json": True,
            "is_valid_schema": True,
            "is_simulated_fixture": True,
            "model_used": f"{model_name or self.model_name} (preview fixture)",
            "adapter_used": "survey-cleaner-lora-v1" if use_adapter else None,
            "latency_seconds": 0.05
        }
