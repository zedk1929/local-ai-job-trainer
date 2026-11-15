from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class ClassStat(BaseModel):
    tp: int = 0
    fp: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0

class BaselineEvaluationReport(BaseModel):
    is_unlabeled: bool = False
    is_simulated: bool = False
    execution_mode: str = "connected"
    model_name: str = ""
    total_rows: int = 0
    attempted_rows: int = 0
    blank_rows: int = 0
    failed_requests: int = 0

    # Schema Validity (strictly on raw model output, independent of human labels)
    schema_valid_count: int = 0
    schema_invalid_count: int = 0
    schema_validity_pct: float = 0.0

    # Topic Metrics (evaluated only where valid human topic labels exist)
    has_topic_labels: bool = False
    topic_labeled_rows: int = 0
    invalid_topic_label_count: int = 0
    topic_coverage_pct: float = 0.0
    topic_tp: int = 0
    topic_fp: int = 0
    topic_fn: int = 0
    topic_precision: float = 0.0
    topic_recall: float = 0.0
    topic_micro_f1: Optional[float] = None
    per_topic_breakdown: Dict[str, ClassStat] = {}

    # Sentiment Metrics (evaluated only where valid human sentiment labels exist)
    has_sentiment_labels: bool = False
    sentiment_labeled_rows: int = 0
    invalid_sentiment_label_count: int = 0
    sentiment_coverage_pct: float = 0.0
    sentiment_correct: int = 0
    sentiment_accuracy: Optional[float] = None

    # Review Flag Metrics (evaluated only where valid human review flag labels exist)
    has_review_flag_labels: bool = False
    review_flag_labeled_rows: int = 0
    invalid_review_flag_count: int = 0
    review_flag_coverage_pct: float = 0.0
    review_flag_correct: int = 0
    review_flag_accuracy: Optional[float] = None

    # Performance
    total_elapsed_seconds: float = 0.0
    throughput_items_per_sec: float = 0.0
    average_latency_seconds: float = 0.0

    # Scientific honesty disclaimer
    scientific_disclaimer: str = (
        "Empirical measurement on configured batch dataset. Accuracy and F1 scores are descriptive "
        "of this local sample only and do not establish general statistical significance or performance guarantees."
    )

class EvaluationResult(BaseModel):
    eval_split: str
    sample_size: int
    topic_micro_f1: float
    sentiment_accuracy: float
    schema_validity: float
    review_flag_accuracy: float
    per_topic_stats: Dict[str, Dict[str, float]] = {}
    is_simulated_fixture: bool = False

def calculate_topic_micro_f1(predictions: List[List[str]], ground_truths: List[List[str]]) -> float:
    total_tp = 0
    total_fp = 0
    total_fn = 0

    for preds, truths in zip(predictions, ground_truths):
        pred_set = set(preds or [])
        truth_set = set(truths or [])

        tp = len(pred_set.intersection(truth_set))
        fp = len(pred_set.difference(truth_set))
        fn = len(truth_set.difference(pred_set))

        total_tp += tp
        total_fp += fp
        total_fn += fn

    if total_tp + total_fp + total_fn == 0:
        return 100.0

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0

    if precision + recall == 0:
        return 0.0

    f1 = 2 * (precision * recall) / (precision + recall)
    return round(f1 * 100, 1)

def evaluate_baseline_batch(
    records: List[Dict[str, Any]],
    total_elapsed_seconds: float = 0.0,
    all_taxonomy_ids: Optional[List[str]] = None,
    is_simulated: bool = False,
    execution_mode: str = "connected",
    model_name: str = ""
) -> BaselineEvaluationReport:
    """
    Compute rigorous evaluation metrics across a batch of responses and predictions.
    Failed predictions are NOT dropped; they count as failures in the denominator.
    Invalid human labels are excluded only from their affected metric and reported explicitly.
    Schema validity is evaluated strictly on the raw model output.
    """
    total_rows = len(records)
    attempted_rows = sum(1 for r in records if r.get("status") != "blank_skipped")
    blank_rows = sum(1 for r in records if r.get("status") == "blank_skipped")
    failed_requests = sum(1 for r in records if r.get("status") == "error")

    # 1. Output Schema Validity (strictly on raw model output)
    schema_valid_count = sum(
        1 for r in records
        if r.get("status") == "success" and r.get("is_valid_schema") is True
    )
    schema_invalid_count = attempted_rows - schema_valid_count
    schema_validity_pct = round((schema_valid_count / attempted_rows) * 100, 1) if attempted_rows > 0 else 0.0

    # 2. Topic Evaluation:
    # Only evaluate on attempted rows where ground_truth_topics is a valid list (not None)
    # Check for invalid topic labels
    invalid_topic_label_count = sum(
        1 for r in records
        if r.get("status") != "blank_skipped" and r.get("has_invalid_topic_label") is True
    )

    topic_labeled_records = [
        r for r in records
        if r.get("status") != "blank_skipped"
        and r.get("ground_truth_topics") is not None
        and not r.get("has_invalid_topic_label", False)
    ]
    has_topic_labels = len(topic_labeled_records) > 0
    topic_labeled_rows = len(topic_labeled_records)
    topic_coverage_pct = round((topic_labeled_rows / attempted_rows) * 100, 1) if attempted_rows > 0 else 0.0

    total_tp = 0
    total_fp = 0
    total_fn = 0
    per_topic: Dict[str, Dict[str, int]] = {}
    if all_taxonomy_ids:
        for tid in all_taxonomy_ids:
            per_topic[tid] = {"tp": 0, "fp": 0, "fn": 0}

    # Helpers to determine field validity with backward compatibility for mock tests
    def is_topics_valid(r: Dict[str, Any]) -> bool:
        if "topics_valid" in r:
            return bool(r["topics_valid"])
        if r.get("status") != "success":
            return False
        return isinstance(r.get("predicted_topics"), list) and r.get("is_valid_schema") is not False

    def is_sentiment_valid(r: Dict[str, Any]) -> bool:
        if "sentiment_valid" in r:
            return bool(r["sentiment_valid"])
        if r.get("status") != "success":
            return False
        pred_s = str(r.get("predicted_sentiment", "")).strip().lower()
        return pred_s in {"positive", "negative", "neutral", "mixed", "unclear"} and r.get("is_valid_schema") is not False

    def is_needs_review_valid(r: Dict[str, Any]) -> bool:
        if "needs_review_valid" in r:
            return bool(r["needs_review_valid"])
        if r.get("status") != "success":
            return False
        val = r.get("predicted_needs_review")
        return isinstance(val, bool) and r.get("is_valid_schema") is not False

    for r in topic_labeled_records:
        gt_set = set(r.get("ground_truth_topics") or [])

        if r.get("status") == "error" or not is_topics_valid(r):
            # Failed request or invalid topics output: all GT topics count as False Negatives
            total_fn += len(gt_set)
            if len(gt_set) == 0:
                # If ground truth was empty list, an invalid prediction counts as False Positive
                total_fp += 1
            for tid in gt_set:
                if tid in per_topic:
                    per_topic[tid]["fn"] += 1
        else:
            pred_set = set(r.get("predicted_topics") or [])
            tp = len(pred_set.intersection(gt_set))
            fp = len(pred_set.difference(gt_set))
            fn = len(gt_set.difference(pred_set))

            total_tp += tp
            total_fp += fp
            total_fn += fn

            for tid in pred_set.intersection(gt_set):
                if tid in per_topic:
                    per_topic[tid]["tp"] += 1
            for tid in pred_set.difference(gt_set):
                if tid in per_topic:
                    per_topic[tid]["fp"] += 1
            for tid in gt_set.difference(pred_set):
                if tid in per_topic:
                    per_topic[tid]["fn"] += 1

    topic_prec = round((total_tp / (total_tp + total_fp)) * 100, 1) if (total_tp + total_fp) > 0 else 0.0
    topic_rec = round((total_tp / (total_tp + total_fn)) * 100, 1) if (total_tp + total_fn) > 0 else 0.0
    if topic_prec + topic_rec > 0:
        topic_f1: Optional[float] = round(2 * (topic_prec * topic_rec) / (topic_prec + topic_rec), 1)
    else:
        topic_f1 = 0.0 if has_topic_labels else None

    # Per-topic breakdown
    per_topic_stats = {}
    for tid, counts in per_topic.items():
        tp = counts["tp"]
        fp = counts["fp"]
        fn = counts["fn"]
        p = round((tp / (tp + fp)) * 100, 1) if (tp + fp) > 0 else 0.0
        r_score = round((tp / (tp + fn)) * 100, 1) if (tp + fn) > 0 else 0.0
        f_score = round(2 * p * r_score / (p + r_score), 1) if (p + r_score) > 0 else 0.0
        per_topic_stats[tid] = ClassStat(
            tp=tp, fp=fp, fn=fn, precision=p, recall=r_score, f1=f_score
        )

    # 3. Sentiment Evaluation:
    invalid_sentiment_label_count = sum(
        1 for r in records
        if r.get("status") != "blank_skipped" and r.get("has_invalid_sentiment_label") is True
    )

    sentiment_labeled_records = [
        r for r in records
        if r.get("status") != "blank_skipped"
        and r.get("ground_truth_sentiment") is not None
        and not r.get("has_invalid_sentiment_label", False)
    ]
    has_sentiment_labels = len(sentiment_labeled_records) > 0
    sentiment_labeled_rows = len(sentiment_labeled_records)
    sentiment_coverage_pct = round((sentiment_labeled_rows / attempted_rows) * 100, 1) if attempted_rows > 0 else 0.0

    sentiment_correct = 0
    for r in sentiment_labeled_records:
        if (
            r.get("status") == "success"
            and is_sentiment_valid(r)
            and r.get("predicted_sentiment") is not None
        ):
            pred_s = str(r.get("predicted_sentiment", "")).strip().lower()
            gt_s = str(r.get("ground_truth_sentiment", "")).strip().lower()
            if pred_s == gt_s:
                sentiment_correct += 1

    sentiment_accuracy = (
        round((sentiment_correct / sentiment_labeled_rows) * 100, 1)
        if sentiment_labeled_rows > 0
        else None
    )

    # 4. Review Flag Evaluation:
    invalid_review_flag_count = sum(
        1 for r in records
        if r.get("status") != "blank_skipped" and r.get("has_invalid_needs_review_label") is True
    )

    review_labeled_records = [
        r for r in records
        if r.get("status") != "blank_skipped"
        and r.get("ground_truth_needs_review") is not None
        and not r.get("has_invalid_needs_review_label", False)
    ]
    has_review_flag_labels = len(review_labeled_records) > 0
    review_flag_labeled_rows = len(review_labeled_records)
    review_flag_coverage_pct = round((review_flag_labeled_rows / attempted_rows) * 100, 1) if attempted_rows > 0 else 0.0

    review_flag_correct = 0
    for r in review_labeled_records:
        if (
            r.get("status") == "success"
            and is_needs_review_valid(r)
            and r.get("predicted_needs_review") is not None
        ):
            pred_rf = bool(r.get("predicted_needs_review"))
            gt_rf = bool(r.get("ground_truth_needs_review"))
            if pred_rf == gt_rf:
                review_flag_correct += 1

    review_flag_accuracy = (
        round((review_flag_correct / review_flag_labeled_rows) * 100, 1)
        if review_flag_labeled_rows > 0
        else None
    )

    # Throughput
    throughput = round(attempted_rows / total_elapsed_seconds, 2) if total_elapsed_seconds > 0 else 0.0
    latencies = [r.get("latency_seconds", 0.0) for r in records if r.get("latency_seconds") is not None]
    avg_lat = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    is_unlabeled = not (has_topic_labels or has_sentiment_labels or has_review_flag_labels)

    return BaselineEvaluationReport(
        is_unlabeled=is_unlabeled,
        is_simulated=is_simulated,
        execution_mode=execution_mode,
        model_name=model_name,
        total_rows=total_rows,
        attempted_rows=attempted_rows,
        blank_rows=blank_rows,
        failed_requests=failed_requests,
        schema_valid_count=schema_valid_count,
        schema_invalid_count=schema_invalid_count,
        schema_validity_pct=schema_validity_pct,
        has_topic_labels=has_topic_labels,
        topic_labeled_rows=topic_labeled_rows,
        invalid_topic_label_count=invalid_topic_label_count,
        topic_coverage_pct=topic_coverage_pct,
        topic_tp=total_tp,
        topic_fp=total_fp,
        topic_fn=total_fn,
        topic_precision=topic_prec,
        topic_recall=topic_rec,
        topic_micro_f1=topic_f1,
        per_topic_breakdown=per_topic_stats,
        has_sentiment_labels=has_sentiment_labels,
        sentiment_labeled_rows=sentiment_labeled_rows,
        invalid_sentiment_label_count=invalid_sentiment_label_count,
        sentiment_coverage_pct=sentiment_coverage_pct,
        sentiment_correct=sentiment_correct,
        sentiment_accuracy=sentiment_accuracy,
        has_review_flag_labels=has_review_flag_labels,
        review_flag_labeled_rows=review_flag_labeled_rows,
        invalid_review_flag_count=invalid_review_flag_count,
        review_flag_coverage_pct=review_flag_coverage_pct,
        review_flag_correct=review_flag_correct,
        review_flag_accuracy=review_flag_accuracy,
        total_elapsed_seconds=round(total_elapsed_seconds, 2),
        throughput_items_per_sec=throughput,
        average_latency_seconds=avg_lat
    )

def calculate_eval_metrics(
    predictions: List[Dict[str, Any]],
    ground_truths: List[Dict[str, Any]],
    eval_split: str = "dev_split",
    is_simulated_fixture: bool = False
) -> EvaluationResult:
    n = len(predictions)
    if n == 0 or len(ground_truths) != n:
        return EvaluationResult(
            eval_split=eval_split,
            sample_size=0,
            topic_micro_f1=0.0,
            sentiment_accuracy=0.0,
            schema_validity=0.0,
            review_flag_accuracy=0.0,
            is_simulated_fixture=is_simulated_fixture
        )

    pred_topics = [p.get("topics", []) for p in predictions]
    true_topics = [gt.get("topics", []) for gt in ground_truths]
    micro_f1 = calculate_topic_micro_f1(pred_topics, true_topics)

    correct_sentiment = sum(
        1 for p, gt in zip(predictions, ground_truths)
        if str(p.get("sentiment", "")).lower() == str(gt.get("sentiment", "")).lower()
    )
    sentiment_acc = round((correct_sentiment / n) * 100, 1)

    valid_schema = sum(
        1 for p in predictions
        if p.get("is_valid_schema", True) is True
    )
    schema_val = round((valid_schema / n) * 100, 1)

    correct_flags = sum(
        1 for p, gt in zip(predictions, ground_truths)
        if bool(p.get("needs_review", False)) == bool(gt.get("needs_review", False))
    )
    flag_acc = round((correct_flags / n) * 100, 1)

    return EvaluationResult(
        eval_split=eval_split,
        sample_size=n,
        topic_micro_f1=micro_f1,
        sentiment_accuracy=sentiment_acc,
        schema_validity=schema_val,
        review_flag_accuracy=flag_acc,
        is_simulated_fixture=is_simulated_fixture
    )

def compare_results(baseline: EvaluationResult, candidate: EvaluationResult) -> Dict[str, Any]:
    f1_diff = round(candidate.topic_micro_f1 - baseline.topic_micro_f1, 1)
    sent_diff = round(candidate.sentiment_accuracy - baseline.sentiment_accuracy, 1)
    schema_diff = round(candidate.schema_validity - baseline.schema_validity, 1)
    flag_diff = round(candidate.review_flag_accuracy - baseline.review_flag_accuracy, 1)

    net_improvement = (f1_diff + sent_diff + schema_diff + flag_diff) / 4.0
    if net_improvement > 1.0:
        outcome = "improved"
        summary = f"Candidate specialist improved performance (+{round(net_improvement, 1)}% average metric gain)."
    elif net_improvement < -1.0:
        outcome = "regressed"
        summary = f"Candidate specialist regressed compared to baseline ({round(net_improvement, 1)}% average loss)."
    else:
        outcome = "neutral"
        summary = "No statistically meaningful difference observed between baseline and candidate."

    return {
        "baseline": baseline.model_dump(),
        "candidate": candidate.model_dump(),
        "differences": {
            "topic_micro_f1": f1_diff,
            "sentiment_accuracy": sent_diff,
            "schema_validity": schema_diff,
            "review_flag_accuracy": flag_diff,
            "net_score": round(net_improvement, 1)
        },
        "outcome": outcome,
        "summary": summary
    }
