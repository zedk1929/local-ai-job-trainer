import json
from typing import Dict, Any, List, Optional, Tuple, Set
from pydantic import BaseModel, Field
from app.core.job_contract import JobDefinition, JobConfigSchema, MetricDefinition, TrainingOptionSchema

VALID_SENTIMENTS = {"positive", "negative", "mixed", "neutral", "unclear"}

class SurveyCleanerJob(JobDefinition):
    id: str = "survey-cleaner"
    title: str = "Survey Cleaner"
    version: str = "1.0.0"
    description: str = "Turn messy open-ended survey responses into consistent structured records using custom categories and rules."
    config_schema: JobConfigSchema = JobConfigSchema(
        survey_context_label="Survey Context",
        survey_context_description="e.g. A campus café gathering customer feedback on menu quality, pricing, speed, and seating.",
        default_taxonomy=[
            {"id": "drink_quality", "name": "Drink Quality", "description": "Taste, temperature, espresso extraction, milk texture, or recipe accuracy."},
            {"id": "price", "name": "Price & Value", "description": "Cost of items, discounts, value for money, perceived affordability."},
            {"id": "service", "name": "Staff & Service", "description": "Speed of service, barista friendliness, accuracy of orders, wait times."},
            {"id": "seating", "name": "Atmosphere & Seating", "description": "Table availability, noise level, cleanliness, seating comfort, WiFi, power outlets."}
        ],
        default_rules=[
            "Assign all relevant topics that are explicitly mentioned or strongly implied.",
            "If the comment mentions both good and bad aspects (e.g. 'Coffee was great but line was huge'), mark sentiment as 'mixed'.",
            "If the customer expresses uncertainty or the text is incomprehensible, mark sentiment as 'unclear' and set needs_review to true.",
            "Do not infer unmentioned details or extrapolate facts.",
            "Flag needs_review=true if customer reports an unresolved safety, harassment, or severe hygiene issue."
        ]
    )
    metrics: List[MetricDefinition] = [
        MetricDefinition(id="topic_micro_f1", name="Topic Micro-F1", description="Harmonic mean of precision and recall across all taxonomy categories.", unit="%"),
        MetricDefinition(id="sentiment_accuracy", name="Sentiment Accuracy", description="Percentage of correctly classified sentiment labels (pos/neg/mixed/neutral/unclear).", unit="%"),
        MetricDefinition(id="schema_validity", name="Schema Validity", description="Percentage of outputs that strictly comply with JSON schema and allowed taxonomies.", unit="%"),
        MetricDefinition(id="review_flag_accuracy", name="Review Flag Accuracy", description="Accuracy on determining whether a response requires human supervisor review.", unit="%"),
    ]

    def build_supervisor_prompt(self, context: str, taxonomy: List[Dict[str, str]], rules: List[str], count: int = 10) -> str:
        tax_str = json.dumps(taxonomy, indent=2)
        rules_str = "\n".join(f"- {r}" for r in rules)
        return (
            f"You are a supervisor LLM preparing training examples for a local AI survey cleaner model.\n\n"
            f"Context: {context}\n\n"
            f"Allowed Taxonomy:\n{tax_str}\n\n"
            f"Coding Rules:\n{rules_str}\n\n"
            f"Generate exactly {count} realistic, diverse, messy customer feedback examples.\n"
            f"Return a strict JSON list of objects, each containing:\n"
            f"- original_response: raw realistic user survey text\n"
            f"- topics: array of topic IDs chosen ONLY from the allowed taxonomy\n"
            f"- sentiment: one of ['positive', 'negative', 'mixed', 'neutral', 'unclear']\n"
            f"- summary: a concise factual 1-sentence recap\n"
            f"- needs_review: boolean\n"
            f"- review_reason: brief string explanation if needs_review is true, else null\n\n"
            f"Return ONLY valid JSON."
        )

    def build_baseline_inference_prompt(self, response_text: str, context: str, taxonomy: List[Dict[str, str]], rules: List[str]) -> str:
        tax_str = json.dumps(taxonomy, indent=2)
        rules_str = "\n".join(f"- {r}" for r in rules)
        return (
            f"You are an expert survey data categorizer.\n"
            f"Survey Context: {context}\n\n"
            f"Allowed Taxonomy:\n{tax_str}\n\n"
            f"Coding Rules:\n{rules_str}\n\n"
            f"Response to categorize:\n\"{response_text}\"\n\n"
            f"Output a JSON object with keys: topics, sentiment, summary, needs_review, review_reason."
        )

    def validate_output(self, raw_output: Any, taxonomy: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Strictly validate raw model output against the output schema contract.
        Does NOT silently repair invalid outputs to claim schema validity.
        Returns:
            {
                "is_valid_schema": bool,
                "validation_errors": List[str],
                "topics": List[str] (sanitized for safe downstream use),
                "sentiment": str (sanitized for safe downstream use),
                "summary": str or None,
                "needs_review": bool,
                "review_reason": str or None,
                "raw_output": raw_output
            }
        """
        valid_topic_ids = {t["id"] for t in taxonomy}
        errors: List[str] = []

        if not isinstance(raw_output, dict):
            return {
                "is_valid_schema": False,
                "validation_errors": [f"Model output must be a JSON object, got {type(raw_output).__name__}"],
                "topics": [],
                "sentiment": "unclear",
                "summary": "",
                "needs_review": False,
                "review_reason": None,
                "raw_output": raw_output
            }

        # 1. Validate topics field
        sanitized_topics: List[str] = []
        if "topics" not in raw_output:
            errors.append("Missing required field 'topics'")
        else:
            raw_topics = raw_output["topics"]
            if not isinstance(raw_topics, list):
                errors.append(f"Field 'topics' must be an array of strings, got {type(raw_topics).__name__}")
            else:
                invalid_topics = []
                for item in raw_topics:
                    if not isinstance(item, str):
                        invalid_topics.append(str(item))
                    elif item not in valid_topic_ids:
                        invalid_topics.append(item)
                    else:
                        if item not in sanitized_topics:
                            sanitized_topics.append(item)
                if invalid_topics:
                    errors.append(f"Unknown topic ID(s) not in taxonomy: {invalid_topics}")

        # 2. Validate sentiment field
        sanitized_sentiment = "unclear"
        if "sentiment" not in raw_output:
            errors.append("Missing required field 'sentiment'")
        else:
            raw_sentiment = raw_output["sentiment"]
            if not isinstance(raw_sentiment, str):
                errors.append(f"Field 'sentiment' must be a string, got {type(raw_sentiment).__name__}")
            else:
                clean_sentiment = raw_sentiment.strip().lower()
                if clean_sentiment not in VALID_SENTIMENTS:
                    errors.append(
                        f"Invalid sentiment '{raw_sentiment}'. Must be one of {sorted(VALID_SENTIMENTS)}"
                    )
                else:
                    sanitized_sentiment = clean_sentiment

        # 3. Validate needs_review field
        # MUST BE STRICT BOOLEAN (type(val) is bool)
        sanitized_needs_review = False
        if "needs_review" not in raw_output:
            errors.append("Missing required field 'needs_review'")
        else:
            raw_needs_review = raw_output["needs_review"]
            if type(raw_needs_review) is not bool:
                errors.append(
                    f"Field 'needs_review' must be a boolean (true/false), got {type(raw_needs_review).__name__} ('{raw_needs_review}')"
                )
                # For safety downstream, if it looks like true
                if str(raw_needs_review).lower() in {"true", "1", "yes"}:
                    sanitized_needs_review = True
            else:
                sanitized_needs_review = raw_needs_review

        # 4. Validate summary field
        raw_summary = raw_output.get("summary")
        sanitized_summary: Optional[str] = None
        if raw_summary is not None:
            if not isinstance(raw_summary, str):
                errors.append(f"Field 'summary' must be a string or null, got {type(raw_summary).__name__}")
                sanitized_summary = str(raw_summary)
            else:
                sanitized_summary = raw_summary

        # 5. Validate review_reason field
        raw_reason = raw_output.get("review_reason")
        sanitized_reason: Optional[str] = None
        if raw_reason is not None:
            if not isinstance(raw_reason, str):
                errors.append(f"Field 'review_reason' must be a string or null, got {type(raw_reason).__name__}")
                sanitized_reason = str(raw_reason)
            else:
                sanitized_reason = raw_reason

        is_valid = len(errors) == 0

        return {
            "is_valid_schema": is_valid,
            "validation_errors": errors,
            "topics": sanitized_topics,
            "sentiment": sanitized_sentiment,
            "summary": sanitized_summary,
            "needs_review": sanitized_needs_review,
            "review_reason": sanitized_reason,
            "raw_output": raw_output
        }

survey_cleaner_job = SurveyCleanerJob()
