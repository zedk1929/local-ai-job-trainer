import pytest
from app.services.evaluator import evaluate_baseline_batch

def test_evaluator_failed_requests_counted_in_denominator():
    # 2 rows with ground truth.
    # Row 1: model succeeded and got it right.
    # Row 2: model request failed with error!
    # Expected: Accuracy should be 1/2 = 50.0%, NOT 1/1 = 100%!
    records = [
        {
            "status": "success",
            "ground_truth_topics": ["drink_quality"],
            "ground_truth_sentiment": "positive",
            "ground_truth_needs_review": False,
            "predicted_topics": ["drink_quality"],
            "predicted_sentiment": "positive",
            "predicted_needs_review": False,
            "is_valid_schema": True,
            "latency_seconds": 1.2
        },
        {
            "status": "error",
            "ground_truth_topics": ["service"],
            "ground_truth_sentiment": "negative",
            "ground_truth_needs_review": True,
            "predicted_topics": [],
            "predicted_sentiment": "",
            "predicted_needs_review": False,
            "is_valid_schema": False,
            "latency_seconds": 0.5
        }
    ]

    report = evaluate_baseline_batch(records, total_elapsed_seconds=1.7, all_taxonomy_ids=["drink_quality", "service"])

    assert report.total_rows == 2
    assert report.attempted_rows == 2
    assert report.failed_requests == 1
    # Schema validity: 1 / 2 = 50.0%
    assert report.schema_validity_pct == 50.0

    # Sentiment: 1 correct out of 2 labeled rows = 50.0%
    assert report.sentiment_labeled_rows == 2
    assert report.sentiment_correct == 1
    assert report.sentiment_accuracy == 50.0

    # Review flag: 1 correct out of 2 labeled rows = 50.0%
    assert report.review_flag_labeled_rows == 2
    assert report.review_flag_correct == 1
    assert report.review_flag_accuracy == 50.0

    # Topic Micro-F1:
    # Row 1: GT=[drink_quality], Pred=[drink_quality] -> TP=1, FP=0, FN=0
    # Row 2: GT=[service], Pred=[] (failed) -> TP=0, FP=0, FN=1
    # Total TP=1, FP=0, FN=1 -> Prec = 1/1 = 1.0, Rec = 1/2 = 0.5 -> F1 = 2*(1*0.5)/(1+0.5) = 66.7%
    assert report.topic_tp == 1
    assert report.topic_fp == 0
    assert report.topic_fn == 1
    assert report.topic_precision == 100.0
    assert report.topic_recall == 50.0
    assert report.topic_micro_f1 == 66.7

def test_evaluator_partially_labeled_data():
    # Dataset where only topic labels were provided for row 1, and only sentiment for row 2
    records = [
        {
            "status": "success",
            "ground_truth_topics": ["drink_quality"],
            "ground_truth_sentiment": None,  # unlabelled
            "ground_truth_needs_review": None, # unlabelled
            "predicted_topics": ["drink_quality"],
            "predicted_sentiment": "positive",
            "predicted_needs_review": False,
            "is_valid_schema": True
        },
        {
            "status": "success",
            "ground_truth_topics": None, # unlabelled
            "ground_truth_sentiment": "negative",
            "ground_truth_needs_review": True,
            "predicted_topics": ["service"],
            "predicted_sentiment": "negative",
            "predicted_needs_review": True,
            "is_valid_schema": True
        }
    ]

    report = evaluate_baseline_batch(records, total_elapsed_seconds=1.0)

    # Topic evaluation should only have denominator of 1
    assert report.has_topic_labels is True
    assert report.topic_labeled_rows == 1
    assert report.topic_micro_f1 == 100.0

    # Sentiment evaluation should only have denominator of 1
    assert report.has_sentiment_labels is True
    assert report.sentiment_labeled_rows == 1
    assert report.sentiment_accuracy == 100.0

    # Review flag evaluation should only have denominator of 1
    assert report.has_review_flag_labels is True
    assert report.review_flag_labeled_rows == 1
    assert report.review_flag_accuracy == 100.0

def test_evaluator_unlabeled_dataset():
    # Dataset where no ground truth labels were supplied
    records = [
        {
            "status": "success",
            "ground_truth_topics": None,
            "ground_truth_sentiment": None,
            "ground_truth_needs_review": None,
            "predicted_topics": ["drink_quality"],
            "predicted_sentiment": "positive",
            "predicted_needs_review": False,
            "is_valid_schema": True
        },
        {
            "status": "success",
            "ground_truth_topics": None,
            "ground_truth_sentiment": None,
            "ground_truth_needs_review": None,
            "predicted_topics": ["service"],
            "predicted_sentiment": "negative",
            "predicted_needs_review": False,
            "is_valid_schema": True
        }
    ]

    report = evaluate_baseline_batch(records, total_elapsed_seconds=0.5)

    assert report.is_unlabeled is True
    assert report.has_topic_labels is False
    assert report.topic_micro_f1 is None
    assert report.sentiment_accuracy is None
    assert report.review_flag_accuracy is None
    # Schema validity is still calculated!
    assert report.schema_validity_pct == 100.0
