# Survey Cleaner Baseline Evaluation Report

**Experiment ID:** `survey_baseline_20261114`  
**Execution Date:** 2026-11-14  
**Job Definition:** `survey-cleaner` (v1.0.0)  
**Model:** `qwen2.5-coder:3b` via Ollama (`http://127.0.0.1:11434`)  
**Hardware:** Apple M2 MacBook Air, 8 GB Unified Memory  
**Dataset:** `evaluation/survey_baseline/dataset.csv` (SHA-256: `20b384cd00a709c8cc0b70c34996b18845041dd1a23156b00b09da53149d19bc`)  

> **Scientific Honesty Disclaimer**: This evaluation measures the performance of the unspecialized base local model on a 60-response synthetic development dataset. These metrics are descriptive empirical measurements of this specific sample and do not establish general statistical significance, benchmark superiority, or production reliability.

---

## 1. Executive Summary & Headline Metrics

The entire 61-row dataset (60 labeled responses + 1 blank row) was processed using the real local `qwen2.5-coder:3b` model at concurrency 1. No simulated fixtures were used; 100% of attempted rows were evaluated against the live local model.

| Metric | Score / Value | Numerator / Denominator | Interpretation |
| :--- | :--- | :--- | :--- |
| **Schema Validity** | **100.0%** | 60 / 60 attempted rows | 100% compliant JSON conforming strictly to the job schema (keys, types, enums). |
| **Topic Micro-F1** | **81.1%** *(81.2% unrounded)* | 69 TP / (69 TP + 10 FP + 22 FN) | Strong category identification; limited primarily by multi-topic recall. |
| **Sentiment Accuracy** | **75.0%** | 45 / 60 evaluated rows | Strong on distinct polarities, but conflates severe hazards with "unclear" sentiment. |
| **Review Flag Accuracy** | **93.3%** | 56 / 60 evaluated rows | High safety/hazard sensitivity; only 4 discrepancies across the entire dataset. |
| **Blank Row Handling** | **100.0%** | 1 / 1 blank row skipped | `DEV_61` flagged as `blank_skipped`, safely preserved without wasting model inference. |
| **Inference Failures** | **0.0%** | 0 failed requests | 0 timeouts, 0 dropped rows, 0 HTTP connection errors. |
| **Total Runtime** | **134.7s** | 60 inferences + 1 skipped | Average latency of 2.24s per row (0.45 items/sec throughput). |

---

## 2. Topic Categorization Performance

The Survey Cleaner task requires assigning zero, one, or multiple topics from a 4-class taxonomy (`drink_quality`, `price`, `service`, `seating`).

- **Total Ground Truth Topic Assignments**: 91
- **Total Model Predicted Topic Assignments**: 79
- **True Positives (TP)**: 69
- **False Positives (FP)**: 10
- **False Negatives (FN)**: 22
- **Topic Precision**: 87.3% (69 / 79)
- **Topic Recall**: 75.8% (69 / 91)
- **Topic Micro-F1**: 81.1%

### Per-Topic Breakdown

| Topic ID | Class Name | TP | FP | FN | Precision | Recall | F1 Score |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `drink_quality` | Drink Quality | 20 | 1 | 7 | 95.2% | 74.1% | 83.3% |
| `price` | Price & Value | 16 | 1 | 3 | 94.1% | 84.2% | 88.9% |
| `service` | Staff & Service | 18 | 4 | 9 | 81.8% | 66.7% | 73.5% |
| `seating` | Atmosphere & Seating | 15 | 4 | 3 | 78.9% | 83.3% | 81.0% |

### Key Error Patterns in Topic Classification

1. **Multi-Topic Recall Deficit (22 False Negatives)**:
   - When survey comments touch on 2, 3, or 4 categories simultaneously, the model consistently identifies the primary/dominant theme but frequently omits secondary categories.
   - *Example (`DEV_15`)*: *"The barista crafted a gorgeous rosetta and handed it to me with a warm smile."*  
     Model predicted: `["drink_quality"]`. Missed: `service`.
   - *Example (`DEV_24`)*: *"The staff was very sweet and apologized, but the Americano was completely lukewarm and sour."*  
     Model predicted: `["drink_quality"]`. Missed: `service`.
   - *Example (`DEV_31`)*: *"The nitro cold brew and cozy armchairs are top tier, but sluggish staff and steep prices drag it down."*  
     Model predicted: `["drink_quality", "service", "price"]`. Missed: `seating`.
2. **Severe Hazard Misattribution**:
   - For extreme physical hazard reports (`DEV_47` glass shard in drink, `DEV_48` staple in muffin, `DEV_51` chipped cracked mug rim, `DEV_52` cockroach in cold brew), the base model predicted `seating` instead of `drink_quality` or `service`. The model appears to associate physical restaurant premises with store seating/environment when unusual physical objects are described.
3. **Food vs. Beverage Boundary**:
   - In `DEV_39` (*"Eight bucks for avocado toast with zero seasoning is a certified rip-off"*), the model correctly avoided predicting `drink_quality` (focusing on `price`), showing adherence to the taxonomy boundary.

---

## 3. Sentiment Classification Performance

- **Evaluated Rows**: 60 (excluding 1 blank row)
- **Correct Predictions**: 45
- **Accuracy**: 75.0% (45 / 60)

### Confusion & Error Modes

1. **Hazard Conflation with "Unclear" (4 errors)**:
   - For `DEV_47` (glass in latte), `DEV_48` (staple in muffin), `DEV_51` (chipped mug), and `DEV_52` (cockroach), the ground truth is `negative`.
   - The model predicted `unclear` for all four.
   - *Root Cause*: Prompt Coding Rule 3 states: *"If the customer expresses uncertainty or the text is incomprehensible, mark sentiment as 'unclear' and set needs_review to true."* The model erroneously formed an associative link between `needs_review: true` and `sentiment: "unclear"`, assigning "unclear" sentiment whenever a hazard warranted review.
2. **Neutral Polarity Drift (4 errors)**:
   - Factual, neutral statements were pulled into positive or negative:
     - `DEV_03` (*"Standard dark roast coffee. Nothing special, tasted okay"*): GT `neutral`, Model `positive`.
     - `DEV_06` (*"Cashier swiped my card without saying hello or goodbye. Routine transaction"*): GT `neutral`, Model `negative`.
     - `DEV_09` (*"Standard city prices for coffee, about what you expect around here"*): GT `neutral`, Model `positive`.
     - `DEV_12` (*"There are four small two-top tables along the east wall"*): GT `neutral`, Model `positive`.
3. **Subtle Mixed Polarity (3 errors)**:
   - Comments containing conflicting valence were sometimes simplified:
     - `DEV_24` (sweet staff but sour coffee): GT `mixed`, Model `negative`.
     - `DEV_42` (comfy seating but overpriced pastries): GT `mixed`, Model `positive`.
     - `DEV_46` (not cheap, but comfy leather couches): GT `mixed`, Model `positive`.

---

## 4. Review Flag Performance

- **Evaluated Rows**: 60
- **Correct Predictions**: 56
- **Accuracy**: 93.3% (56 / 60)

Only 4 discrepancies occurred:

1. **`DEV_18` (False Positive for Review)**:
   - Text: *"Sticky tables everywhere piled with dirty mugs, and staff made zero effort to clear them."*
   - GT: `needs_review: false`. Model: `needs_review: true`.
   - Model Review Reason: *"Safety issue: dirty tables and lack of cleaning"*.
   - *Assessment*: High hygiene sensitivity; arguably a defensible model flag.
2. **`DEV_21` (False Positive for Review)**:
   - Text: *"The matcha tasted like chalky powder and the deafening music made it impossible to read."*
   - GT: `needs_review: false`. Model: `needs_review: true`.
   - Model Review Reason: *"Incomprehensible text"*.
   - *Assessment*: Clear model mistake; the text is colloquial but completely coherent.
3. **`DEV_49` (False Negative for Review)**:
   - Text: *"The milk in my chai smelled like rancid bleach and tasted curdled. I felt severely sick twenty minutes later."*
   - GT: `needs_review: true`. Model: `needs_review: false`.
   - *Assessment*: Model failure to flag severe food poisoning / chemical odor. High operational priority for future prompt tuning.
4. **`DEV_57` (False Positive for Review)**:
   - Text: *"Does the campus library across the street validate visitor parking on weekends?"*
   - GT: `needs_review: false`. Model: `needs_review: true`.
   - Model Review Reason: *"The feedback does not provide any information about drink quality, price, service, or seating atmosphere."*
   - *Assessment*: Model flagged off-topic query because it contained no café domain signals.

---

## 5. Blank Row & Provenance Verification

- **Row `DEV_61`**: Contains empty text `""`.
- Handled via `is_blank_response()` check in `baseline_runner.py`:
  - Model inference was skipped (latency = 0.0s).
  - Recorded with status `blank_skipped`.
  - Excluded from accuracy and F1 denominators so missing data does not artificially deflate or inflate performance.
- **Provenance Integrity**:
  - Every row in `predictions.jsonl` and `results.csv` contains `baseline_is_simulated: NO`, `baseline_execution_mode: connected`, and `baseline_model_identity: qwen2.5-coder:3b`.
  - Zero mock or fixture predictions were injected.

---

## 6. Execution Runtime & Hardware Efficiency

- **Hardware**: Apple M2 MacBook Air (8 GB RAM).
- **Process Memory & Stability**: Stable throughout; zero out-of-memory events or thread crashes.
- **Initial Model Load (Cold Start)**: 16.9s.
- **Warm Inference Latency**: ~1.7s to 2.1s per response.
- **Total Elapsed Time**: 134.69 seconds for 61 rows.
- **Effective Throughput**: 0.45 responses / second (27 responses / minute).

---

## 7. Strategic Recommendations: Definitions, Prompting, or LoRA?

Based on empirical evidence from this baseline experiment:

### A. Immediate Action: Prompt Refinement & Few-Shot Clarification (High ROI, No Training Required)
1. **Disentangle Rule 3 (Unclear) and Rule 5 (Hazards)**:
   - The primary driver of sentiment errors (4 errors) was the model labeling hazardous food incidents as `unclear` instead of `negative`.
   - *Fix*: Explicitly state: *"Safety and hygiene incidents are negative sentiment with needs_review: true. Reserve 'unclear' solely for text that is unintelligible, gibberish, or incomplete."*
2. **Explicit Multi-Topic Prompt Conditioning**:
   - The model drops secondary topics in compound sentences (22 false negatives).
   - *Fix*: Provide 2 few-shot demonstrations illustrating multi-topic sentence decomposition (e.g. coffee quality + barista service).
3. **Calibrate Neutral Polarity**:
   - Provide an explicit rule that purely descriptive or routine statements without positive or negative adjectives should remain `neutral`.

### B. Task Definition & Taxonomy Clarification
- Survey comments frequently mention food or bakery items (`DEV_39` avocado toast, `DEV_42` pastries, `DEV_48` muffin). Because the taxonomy only provides `drink_quality`, these responses create ambiguity. Expanding the taxonomy to include `food_quality` or renaming `drink_quality` to `menu_quality` would eliminate domain ambiguity.

### C. When is LoRA Specialization Warranted?
- The unspecialized 3.1B model achieved **100% schema validity**, **93.3% review flag accuracy**, and **81.1% topic micro-F1** with zero fine-tuning.
- LoRA fine-tuning is **not yet justified as a first recourse**; prompt engineering and taxonomy disambiguation should be tested first. If prompt tuning plateaus below 90% topic F1 due to architectural capacity limitations on multi-label recall, a compact LoRA adapter specialized on café survey syntax would be the logical next milestone.

---

## 8. Artifact Directory Map

All artifacts are persisted in [`evaluation/survey_baseline/`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline):

- [`dataset.csv`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/dataset.csv): The 61-row development dataset.
- [`labeling_notes.md`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/labeling_notes.md): Per-response ground-truth rationales and ambiguities.
- [`config.json`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/config.json): Frozen execution parameters, model digest, and exact prompt template.
- [`predictions.jsonl`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/predictions.jsonl): Complete per-row input, raw model output, validated prediction, timings, and provenance.
- [`results.csv`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/results.csv): Application-exported CSV with original text and collision-free prediction columns.
- [`metrics.json`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/metrics.json): Serialized baseline evaluation report with full denominators and per-topic breakdowns.
- [`run_experiment.py`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/run_experiment.py): Fully reproducible runner executing the pipeline against temporary storage.
