import json
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple, Set

VALID_SENTIMENTS = {"positive", "negative", "mixed", "neutral", "unclear"}

SENTIMENT_ALIASES = {
    "pos": "positive",
    "positive": "positive",
    "neg": "negative",
    "negative": "negative",
    "mix": "mixed",
    "mixed": "mixed",
    "neut": "neutral",
    "neutral": "neutral",
    "unclear": "unclear",
    "ambiguous": "unclear",
    "unknown": "unclear"
}

TRUE_VALUES = {"true", "yes", "1", "y", "t", "flag", "flagged"}
FALSE_VALUES = {"false", "no", "0", "n", "f", "ok", "none", "clear", "unflagged"}

EXPLICIT_EMPTY_TOPIC_STRINGS = {"[]", "[ ]", "none", "<none>", "no topics", "no_topic", "no_topics", "n/a", "empty"}

@dataclass
class LabelParseResult:
    """
    Structured outcome of parsing a human-labeled ground truth field.
    value: The sanitized ground truth value if valid, or None.
    is_present: Whether the row cell contained non-empty text.
    is_valid: True if valid or missing; False if present but unrecognized/invalid.
    error: Diagnostic message explaining why the label was rejected.
    """
    value: Any
    is_present: bool
    is_valid: bool
    error: Optional[str] = None

def parse_ground_truth_topics(
    raw_value: Any,
    valid_taxonomy_ids: Set[str]
) -> LabelParseResult:
    """
    Parse a human-labeled topics cell.
    Distinguishes:
      - Missing label: raw_value is empty/None -> is_present=False, is_valid=True, value=None
      - Valid empty list: "[]", "none" -> is_present=True, is_valid=True, value=[]
      - Valid topics: e.g. "drink_quality; price" -> is_present=True, is_valid=True, value=["drink_quality", "price"]
      - Invalid label: unknown topic -> is_present=True, is_valid=False, value=None, error="..."
    """
    if raw_value is None:
        return LabelParseResult(value=None, is_present=False, is_valid=True)

    val_str = str(raw_value).strip()
    if not val_str:
        return LabelParseResult(value=None, is_present=False, is_valid=True)

    # Check explicit zero-topic markers
    if val_str.lower() in EXPLICIT_EMPTY_TOPIC_STRINGS:
        return LabelParseResult(value=[], is_present=True, is_valid=True)

    tokens = []
    if val_str.startswith("[") and val_str.endswith("]"):
        try:
            parsed = json.loads(val_str)
            if isinstance(parsed, list):
                if len(parsed) == 0:
                    return LabelParseResult(value=[], is_present=True, is_valid=True)
                tokens = [str(t).strip() for t in parsed if str(t).strip()]
        except Exception:
            pass

    if not tokens:
        tokens = [t.strip() for t in re.split(r"[;,\n|]+", val_str) if t.strip()]

    recognized = []
    unrecognized = []

    for token in tokens:
        clean = token.lower().replace(" ", "_")
        if clean in valid_taxonomy_ids:
            if clean not in recognized:
                recognized.append(clean)
        else:
            unrecognized.append(token)

    if unrecognized:
        return LabelParseResult(
            value=None,
            is_present=True,
            is_valid=False,
            error=f"Unknown topic ID(s): {unrecognized}. Allowed taxonomy IDs: {sorted(valid_taxonomy_ids)}"
        )

    return LabelParseResult(value=recognized, is_present=True, is_valid=True)

def parse_ground_truth_sentiment(raw_value: Any) -> LabelParseResult:
    """
    Parse a human-labeled sentiment cell.
    Allowed: positive, negative, mixed, neutral, unclear (case-insensitive, aliases supported).
    """
    if raw_value is None:
        return LabelParseResult(value=None, is_present=False, is_valid=True)

    val_str = str(raw_value).strip().lower()
    if not val_str:
        return LabelParseResult(value=None, is_present=False, is_valid=True)

    if val_str in SENTIMENT_ALIASES:
        return LabelParseResult(value=SENTIMENT_ALIASES[val_str], is_present=True, is_valid=True)

    return LabelParseResult(
        value=None,
        is_present=True,
        is_valid=False,
        error=f"Unrecognized sentiment '{raw_value}'. Allowed: positive, negative, mixed, neutral, unclear"
    )

def parse_ground_truth_needs_review(raw_value: Any) -> LabelParseResult:
    """
    Parse a human-labeled review flag cell.
    Allowed: true/false, yes/no, 1/0.
    """
    if raw_value is None:
        return LabelParseResult(value=None, is_present=False, is_valid=True)

    val_str = str(raw_value).strip().lower()
    if not val_str:
        return LabelParseResult(value=None, is_present=False, is_valid=True)

    if val_str in TRUE_VALUES:
        return LabelParseResult(value=True, is_present=True, is_valid=True)
    elif val_str in FALSE_VALUES:
        return LabelParseResult(value=False, is_present=True, is_valid=True)

    return LabelParseResult(
        value=None,
        is_present=True,
        is_valid=False,
        error=f"Unrecognized review flag '{raw_value}'. Allowed: true/false, yes/no, 1/0"
    )

def is_blank_response(text: Any) -> bool:
    """Return True if response text is null, whitespace, or empty."""
    if text is None:
        return True
    return len(str(text).strip()) == 0
