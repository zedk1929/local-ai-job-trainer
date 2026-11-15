import httpx
import json
import logging
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)


def safe_parent_error(error: Exception) -> str:
    """Classify failures without disclosing keys, request URLs, or provider response bodies."""
    suffix = ' No fixture was substituted.'
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        reason = ''
        try:
            details = error.response.json().get('error', {}).get('details', [])
            reason = next((d.get('reason', '') for d in details if isinstance(d, dict) and d.get('reason')), '')
        except Exception:
            pass
        if reason in ('API_KEY_INVALID', 'API_KEY_EXPIRED') or status == 401:
            message = 'The parent service rejected the API key. Create or check the key in your provider console.'
        elif status == 403:
            message = 'Parent access denied (HTTP 403). Check API-key restrictions, project permissions, and whether the API is enabled.'
        elif status == 404:
            message = 'Selected parent model is unavailable (HTTP 404). Choose a model available to your API project.'
        elif status == 429:
            message = 'Parent quota or rate limit reached (HTTP 429). Check project quotas and billing, then retry later.'
        elif status == 400:
            message = 'Parent request rejected (HTTP 400). Check the model name, key/project configuration, and supported request settings.'
        elif status in (402,):
            message = 'Parent billing or credits are required (HTTP 402). Check the provider billing console.'
        elif status >= 500:
            message = f'Parent service is temporarily unavailable (HTTP {status}). Retry later.'
        else:
            message = f'Parent request failed (HTTP {status}). Check the provider console.'
    elif isinstance(error, httpx.ReadTimeout):
        message = 'Parent response timed out. Your key may still be valid; check provider availability before retrying.'
    elif isinstance(error, httpx.TimeoutException):
        message = 'Parent connection timed out. Check your internet connection and retry.'
    elif isinstance(error, httpx.RequestError):
        if 'CERTIFICATE_VERIFY_FAILED' in str(error):
            message = 'Secure connection to the parent failed certificate verification. Check this Python environment’s trusted certificates; keep certificate verification enabled.'
        else:
            message = 'Could not reach the parent service. Check your internet connection, proxy, or firewall.'
    else:
        message = 'Parent returned empty, truncated, or unreadable output. Retry with a supported model.'
    return message + suffix

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

    async def generate_text(self, prompt: str, *, json_output: bool = True, max_tokens: int = 4096) -> str:
        """Backend-only provider requests. Never expose credentials or provider error bodies."""
        if not self.is_configured() or self.provider not in ('gemini', 'anthropic'):
            raise RuntimeError('Configure a supported parent provider and API key in Setup.')
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)) as http:
                if self.provider == 'anthropic':
                    response = await http.post(
                        'https://api.anthropic.com/v1/messages',
                        headers={'x-api-key': self.api_key, 'anthropic-version': '2026-10-21'},
                        json={'model': self.model, 'max_tokens': max_tokens,
                              'messages': [{'role': 'user', 'content': prompt}]},
                    )
                    response.raise_for_status()
                    result = response.json()
                    if result.get('stop_reason') == 'max_tokens':
                        raise ValueError('Truncated parent output')
                    text = ''.join(block['text'] for block in result.get('content', []) if block.get('type') == 'text')
                else:
                    response = await http.post(
                        f'https://generativelanguage.googleapis.com/v1beta/models/{self.model.removeprefix("models/")}:generateContent',
                        headers={'x-goog-api-key': self.api_key},
                        json={'contents': [{'parts': [{'text': prompt}]}],
                              'generationConfig': {'maxOutputTokens': max_tokens, **({'responseMimeType': 'application/json'} if json_output else {})}},
                    )
                    response.raise_for_status()
                    result = response.json()
                    candidate = result['candidates'][0]
                    if candidate.get('finishReason') == 'MAX_TOKENS':
                        raise ValueError('Truncated parent output')
                    text = ''.join(p.get('text', '') for p in candidate.get('content', {}).get('parts', []) if not p.get('thought'))
                if not text.strip():
                    raise ValueError('Empty parent output')
                return text
        except Exception as exc:
            raise RuntimeError(safe_parent_error(exc)) from None

    async def test_connection(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {'connected': False, 'provider': self.provider,
                    'message': 'Enter a parent API key first.'}
        try:
            if self.provider == 'gemini':
                # No generation: a 16-token probe can finish without text on reasoning models.
                model_id = self.model.removeprefix('models/')
                async with httpx.AsyncClient(timeout=15.0) as http:
                    response = await http.get(
                        f'https://generativelanguage.googleapis.com/v1beta/models/{model_id}',
                        headers={'x-goog-api-key': self.api_key},
                    )
                    response.raise_for_status()
                    methods = response.json().get('supportedGenerationMethods', [])
                    if 'generateContent' not in methods:
                        return {'connected': False, 'provider': self.provider,
                                'message': 'This Gemini model does not support text generation. Choose a generateContent model.'}
                return {'connected': True, 'provider': self.provider, 'model': self.model,
                        'message': 'Gemini key and model access verified without generation. Generation quota and billing have not been tested.'}
            await self.generate_text('Reply with OK only.', json_output=False, max_tokens=16)
            return {'connected': True, 'provider': self.provider, 'model': self.model,
                    'message': f'{self.provider.title()} parent connection verified.'}
        except RuntimeError as exc:
            return {'connected': False, 'provider': self.provider, 'message': str(exc)}
        except Exception as exc:
            return {'connected': False, 'provider': self.provider, 'message': safe_parent_error(exc)}

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

            items = json.loads(await self.generate_text(prompt))
            if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                raise ValueError('Parent must return an array of examples')
            for item in items:
                item['origin'] = 'synthetic (supervisor API)'
                item['is_simulated_fixture'] = False
            return items
        except Exception:
            raise RuntimeError('Synthetic example generation failed. No fixture was substituted.') from None
