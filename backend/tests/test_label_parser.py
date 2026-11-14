import pytest
from app.services.label_parser import (
    parse_ground_truth_topics,
    parse_ground_truth_sentiment,
    parse_ground_truth_needs_review,
    is_blank_response,
    LabelParseResult
)

def test_parse_ground_truth_topics_formats():
    taxonomy_ids = {"drink_quality", "price", "service", "seating"}

    # Semicolon delimited
    res = parse_ground_truth_topics("drink_quality; price", taxonomy_ids)
    assert res.is_present is True
    assert res.is_valid is True
    assert res.value == ["drink_quality", "price"]
    assert res.error is None

    # Comma delimited with spacing
    res = parse_ground_truth_topics("service, seating", taxonomy_ids)
    assert res.is_present is True
    assert res.is_valid is True
    assert res.value == ["service", "seating"]
    assert res.error is None

    # JSON array
    res = parse_ground_truth_topics('["drink_quality", "service"]', taxonomy_ids)
    assert res.is_present is True
    assert res.is_valid is True
    assert res.value == ["drink_quality", "service"]
    assert res.error is None

    # Explicit empty topic representations
    for empty_repr in ["[]", "[ ]", "none", "<none>", "no topics", "no_topic"]:
        res = parse_ground_truth_topics(empty_repr, taxonomy_ids)
        assert res.is_present is True
        assert res.is_valid is True
        assert res.value == [], f"Expected [] for '{empty_repr}'"
        assert res.error is None

    # Invalid / unknown topics: must NEVER be treated as valid empty answer []
    res = parse_ground_truth_topics("drink_quality; unknown_category; price", taxonomy_ids)
    assert res.is_present is True
    assert res.is_valid is False
    assert res.value is None
    assert "unknown_category" in res.error

    res_unknown_only = parse_ground_truth_topics("completely_fake_topic", taxonomy_ids)
    assert res_unknown_only.is_present is True
    assert res_unknown_only.is_valid is False
    assert res_unknown_only.value is None
    assert "Allowed taxonomy IDs" in res_unknown_only.error

    # Empty / whitespace / None (missing labels)
    for missing in ["", "   ", "\t\n", None]:
        res = parse_ground_truth_topics(missing, taxonomy_ids)
        assert res.is_present is False
        assert res.is_valid is True
        assert res.value is None
        assert res.error is None

def test_parse_ground_truth_sentiment():
    for pos in ["positive", "POS", "Positive"]:
        res = parse_ground_truth_sentiment(pos)
        assert res.is_present is True and res.is_valid is True and res.value == "positive"

    for neg in ["negative", "neg", "Negative"]:
        res = parse_ground_truth_sentiment(neg)
        assert res.is_present is True and res.is_valid is True and res.value == "negative"

    for mix in ["mixed", "mix"]:
        res = parse_ground_truth_sentiment(mix)
        assert res.is_present is True and res.is_valid is True and res.value == "mixed"

    for neut in ["neutral", "neut"]:
        res = parse_ground_truth_sentiment(neut)
        assert res.is_present is True and res.is_valid is True and res.value == "neutral"

    for unc in ["unclear", "ambiguous", "unknown"]:
        res = parse_ground_truth_sentiment(unc)
        assert res.is_present is True and res.is_valid is True and res.value == "unclear"

    # Missing sentiment
    for missing in ["", "   ", None]:
        res = parse_ground_truth_sentiment(missing)
        assert res.is_present is False and res.is_valid is True and res.value is None

    # Invalid sentiment
    res = parse_ground_truth_sentiment("super_excited")
    assert res.is_present is True
    assert res.is_valid is False
    assert res.value is None
    assert "Unrecognized sentiment" in res.error

def test_parse_ground_truth_needs_review():
    for true_val in ["true", "YES", "1", "flag", "flagged"]:
        res = parse_ground_truth_needs_review(true_val)
        assert res.is_present is True and res.is_valid is True and res.value is True

    for false_val in ["false", "NO", "0", "ok", "none", "clear", "unflagged"]:
        res = parse_ground_truth_needs_review(false_val)
        assert res.is_present is True and res.is_valid is True and res.value is False

    # Missing review flag
    for missing in ["", "   ", None]:
        res = parse_ground_truth_needs_review(missing)
        assert res.is_present is False and res.is_valid is True and res.value is None

    # Invalid review flag
    res = parse_ground_truth_needs_review("maybe")
    assert res.is_present is True
    assert res.is_valid is False
    assert res.value is None
    assert "Unrecognized review flag" in res.error

def test_is_blank_response():
    assert is_blank_response("") is True
    assert is_blank_response("   \t\n  ") is True
    assert is_blank_response(None) is True
    assert is_blank_response("Great coffee!") is False
    assert is_blank_response(" 0 ") is False
