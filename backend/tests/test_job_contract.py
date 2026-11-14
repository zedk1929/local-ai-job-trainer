from app.jobs.survey_cleaner import survey_cleaner_job

def test_survey_cleaner_validation():
    taxonomy = [
        {"id": "drink_quality", "name": "Drink Quality"},
        {"id": "price", "name": "Price"}
    ]

    # Valid output
    valid_raw = {
        "topics": ["drink_quality"],
        "sentiment": "positive",
        "summary": "Great latte",
        "needs_review": False
    }
    validated = survey_cleaner_job.validate_output(valid_raw, taxonomy)
    assert validated["is_valid_schema"] is True
    assert validated["topics"] == ["drink_quality"]
    assert validated["sentiment"] == "positive"

    # Invalid topic and invalid sentiment should be sanitized safely
    invalid_raw = {
        "topics": ["drink_quality", "fake_topic_99"],
        "sentiment": "super_happy_unknown",
        "needs_review": "false_string"
    }
    validated = survey_cleaner_job.validate_output(invalid_raw, taxonomy)
    assert validated["is_valid_schema"] is False
    assert "fake_topic_99" not in validated["topics"]
    assert validated["sentiment"] == "unclear"
    assert any("Unknown topic ID" in err for err in validated["validation_errors"])
    assert any("Invalid sentiment" in err for err in validated["validation_errors"])
    assert any("needs_review" in err for err in validated["validation_errors"])

def test_survey_cleaner_strict_contract_violations():
    taxonomy = [
        {"id": "drink_quality", "name": "Drink Quality"},
        {"id": "price", "name": "Price"}
    ]

    # 1. Empty dict must be rejected as invalid schema
    empty_val = survey_cleaner_job.validate_output({}, taxonomy)
    assert empty_val["is_valid_schema"] is False
    assert len(empty_val["validation_errors"]) >= 3

    # 2. String "false" for needs_review must be rejected as invalid schema (strictly requires bool)
    str_bool_val = survey_cleaner_job.validate_output({
        "topics": ["drink_quality"],
        "sentiment": "positive",
        "needs_review": "false"
    }, taxonomy)
    assert str_bool_val["is_valid_schema"] is False
    assert any("Field 'needs_review' must be a boolean" in err for err in str_bool_val["validation_errors"])

    # 3. Valid zero-topic response
    zero_topic_val = survey_cleaner_job.validate_output({
        "topics": [],
        "sentiment": "neutral",
        "needs_review": False
    }, taxonomy)
    assert zero_topic_val["is_valid_schema"] is True
    assert zero_topic_val["topics"] == []

    # 4. Non-dict input
    non_dict_val = survey_cleaner_job.validate_output("invalid string", taxonomy)
    assert non_dict_val["is_valid_schema"] is False
