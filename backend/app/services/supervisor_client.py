import httpx
import json
import logging
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

FIXTURE_SYNTHETIC_EXAMPLES = [
    {
        "original_response": "The oat milk cappuccino was silky and perfectly poured, but $7.50 is steep for a small cup.",
        "topics": ["drink_quality", "price"],
        "sentiment": "mixed",
        "summary": "Customer praised the cappuccino quality but found the price too high.",
        "needs_review": False,
        "review_reason": None,
        "origin": "synthetic"
    },
    {
        "original_response": "Staff were super cheerful despite the morning rush! Ordered iced matcha and had it in 2 minutes flat.",
        "topics": ["service", "drink_quality"],
        "sentiment": "positive",
        "summary": "Fast service and friendly staff during peak hours.",
        "needs_review": False,
        "review_reason": None,
        "origin": "synthetic"
    },
    {
        "original_response": "Music is deafening inside, couldn't hear my zoom call and had to sit on the cold floor because zero outlets near chairs.",
        "topics": ["seating"],
        "sentiment": "negative",
        "summary": "Customer complained of loud music and lack of power outlets near seating.",
        "needs_review": False,
        "review_reason": None,
        "origin": "synthetic"
    },
    {
        "original_response": "Found a rusty paperclip in my blueberry scone. When I told the cashier they just shrugged.",
        "topics": ["service"],
        "sentiment": "negative",
        "summary": "Foreign object in pastry and poor staff reaction.",
        "needs_review": True,
        "review_reason": "Foreign object hazard and hygiene complaint requiring immediate manager review.",
        "origin": "synthetic"
    },
    {
        "original_response": "Regular drip coffee. Nothing special, tasted okay.",
        "topics": ["drink_quality"],
        "sentiment": "neutral",
        "summary": "Average drip coffee with neither positive nor negative distinction.",
        "needs_review": False,
        "review_reason": None,
        "origin": "synthetic"
    },
    {
        "original_response": "dfhsjkldfh 123 ???? not sure what this cafe is",
        "topics": [],
        "sentiment": "unclear",
        "summary": "Incomprehensible response text.",
        "needs_review": True,
        "review_reason": "Garbled or meaningless survey entry.",
        "origin": "synthetic"
    }
]

class SupervisorClient:
    def __init__(self, provider: str = None, api_key: str = None, model: str = None):
        self.provider = provider or settings.supervisor_provider
        self.api_key = api_key or settings.supervisor_api_key
        self.model = model or settings.supervisor_model

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    async def test_connection(self) -> Dict[str, Any]:
        """Test the supervisor API connection with user-configured credentials."""
        if not self.is_configured():
            return {
                "connected": False,
                "provider": self.provider,
                "message": "No supervisor API key provided. Running in Preview mode."
            }

        try:
            if self.provider == "gemini":
                # Test using Gemini REST endpoint
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
                payload = {
                    "contents": [{"parts": [{"text": "Reply with 'OK' only."}]}]
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        return {
                            "connected": True,
                            "provider": self.provider,
                            "model": self.model,
                            "message": "Connection to Google Gemini supervisor verified."
                        }
                    else:
                        return {
                            "connected": False,
                            "provider": self.provider,
                            "message": f"Gemini API returned status {resp.status_code}: {resp.text[:200]}"
                        }
            else:
                return {
                    "connected": False,
                    "provider": self.provider,
                    "message": f"Provider '{self.provider}' test not implemented yet."
                }
        except Exception as e:
            logger.error(f"Supervisor connection test failed: {e}")
            return {
                "connected": False,
                "provider": self.provider,
                "message": f"Connection error: {str(e)}"
            }

    async def generate_synthetic_examples(
        self,
        context: str,
        taxonomy: List[Dict[str, str]],
        rules: List[str],
        count: int = 6
    ) -> List[Dict[str, Any]]:
        """Generate synthetic survey examples adhering strictly to taxonomy and rules."""
        # If in preview mode or no key configured, return verified deterministic fixtures
        if not self.is_configured() or settings.app_mode == "preview":
            return [
                {
                    **ex,
                    "is_simulated_fixture": True,
                    "origin": "synthetic (fixture)"
                }
                for ex in FIXTURE_SYNTHETIC_EXAMPLES[:count]
            ]

        # Connected Mode: call real LLM
        try:
            prompt = (
                f"You are a supervisor LLM creating synthetic training examples for a survey classification task.\n"
                f"Context: {context}\n"
                f"Taxonomy: {json.dumps(taxonomy)}\n"
                f"Coding Rules: {json.dumps(rules)}\n\n"
                f"Generate exactly {count} distinct realistic examples. "
                f"Return ONLY a JSON array of objects with keys: original_response, topics, sentiment, summary, needs_review, review_reason."
            )

            if self.provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"}
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    items = json.loads(text)
                    if isinstance(items, list):
                        for item in items:
                            item["origin"] = "synthetic (supervisor API)"
                            item["is_simulated_fixture"] = False
                        return items
        except Exception as e:
            logger.warning(f"Failed to generate synthetic examples via supervisor ({e}), falling back to fixtures.")

        return [
            {
                **ex,
                "is_simulated_fixture": True,
                "origin": "synthetic (fixture fallback)"
            }
            for ex in FIXTURE_SYNTHETIC_EXAMPLES[:count]
        ]
