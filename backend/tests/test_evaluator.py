from app.services.evaluator import calculate_topic_micro_f1, calculate_eval_metrics, compare_results

def test_topic_micro_f1():
    # 2 samples
    # Sample 1: true=[A, B], pred=[A] (1 TP, 0 FP, 1 FN)
    # Sample 2: true=[B], pred=[B, C] (1 TP, 1 FP, 0 FN)
    # Total TP=2, FP=1, FN=1 -> Precision = 2/3, Recall = 2/3 -> F1 = 66.7%
    preds = [["A"], ["B", "C"]]
    truths = [["A", "B"], ["B"]]

    f1 = calculate_topic_micro_f1(preds, truths)
    assert f1 == 66.7

def test_evaluator_metrics_and_comparison():
    predictions = [
        {"topics": ["drink_quality"], "sentiment": "positive", "is_valid_schema": True, "needs_review": False},
        {"topics": ["service", "price"], "sentiment": "mixed", "is_valid_schema": True, "needs_review": True}
    ]
    ground_truth = [
        {"topics": ["drink_quality"], "sentiment": "positive", "is_valid_schema": True, "needs_review": False},
        {"topics": ["service"], "sentiment": "mixed", "is_valid_schema": True, "needs_review": True}
    ]

    metrics = calculate_eval_metrics(predictions, ground_truth, eval_split="dev_split")
    assert metrics.sample_size == 2
    assert metrics.sentiment_accuracy == 100.0
    assert metrics.schema_validity == 100.0
    assert metrics.review_flag_accuracy == 100.0

    # Test honest no-improvement comparison
    comp = compare_results(metrics, metrics)
    assert comp["outcome"] == "neutral"
    assert comp["differences"]["net_score"] == 0.0
