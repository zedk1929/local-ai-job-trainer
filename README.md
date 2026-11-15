# Apprentice

> 🚀 **Live Working App for Judges**: [https://diff-supplements-painted-please.trycloudflare.com](https://diff-supplements-painted-please.trycloudflare.com)  
> *(No login required. Works in private browsing. Explore immediately in **Preview Mode** with zero local configuration, or Connected Mode via the host).*

A consumer web application for configuring, evaluating, and supervising private local AI models for recurring operational jobs.

The hackathon preset is **Survey Cleaner**, which transforms raw, unstructured customer feedback into categorized, sentiment-analyzed, and safety-flagged structured records using customizable taxonomies and rules.

---

## Hackathon Submission Highlights

### 1. The Problem & Who Has It
Small business owners, customer experience teams, and community organizations receive high volumes of unstructured feedback (e.g. coffee shop reviews, student feedback, event responses).
- **The Challenge**: General-purpose AI models make frequent errors without domain-specific rules, sending all private customer feedback to cloud APIs can be costly and raises privacy concerns, and non-technical operators cannot easily evaluate whether an AI model actually follows their specific guidelines.
- **The Solution**: A local-first workflow where a lightweight, open-weight model runs privately on the user's laptop, guided by a stronger "Parent AI" supervisor that diagnoses mistakes and proposes refined rules with human-in-the-loop review.

### 2. What We Built
- **Local Inference Engine**: Runs `qwen2.5-coder:3b` locally via Ollama with zero cloud API dependencies.
- **Two-Stage Dataset Importer**: Flexible CSV inspection, header detection, and custom column mapping with UTF-8 BOM, multiline, and quote support.
- **Rigorous Ground-Truth Evaluator**: Evaluates topic micro-F1 (supporting multi-topic comments), sentiment accuracy, review flag accuracy, schema compliance, and latency against human labels.
- **Parent AI Failure Analysis**: Leverages Google Gemini or Anthropic Claude to analyze disagreements on a development subset and propose refined coding rules.
- **Human-in-the-Loop Safeguards**: Atomic revision checks, race condition protection, explicit rule diff transparency, and mandatory acknowledgment of removed rules.
- **Auditable Provenance & Export**: Collision-free CSV export with complete execution metadata (`is_simulated`, model identity, validity flags).
- **Offline Preview Mode**: Full interactive walkthrough with deterministic fixtures for judges running without Ollama or GPU hardware.

### 3. AI Tools Used & Credits
- **Ollama + Qwen2.5-Coder 3B (Alibaba Cloud)**: On-device local LLM inference engine executing prompt-driven survey categorization on an 8 GB M2 MacBook Air.
- **Google Gemini API (`gemini-2.5-pro` / `gemini-1.5-pro`)**: Parent AI supervisor diagnosing model failure patterns and proposing targeted coding rule improvements.
- **Anthropic Claude API (`claude-3-5-sonnet`)**: Secondary parent AI supervisor provider.
- **Google Antigravity**: Agentic coding pair programmer used to architect, build, verify, and harden the full-stack system, test suite, and database migrations.

### 4. Market & Student Validation (31 Cal Poly Responses)
To validate the demand for on-device AI automation, we surveyed 31 Cal Poly students across engineering, business, sciences, and student organizations:
- **Repetitive Workload**: **96.8%** of Cal Poly students perform recurring computer tasks weekly (**74.2% daily**)—organizing lab datasets, cleaning club feedback, summarizing papers, and administrative spreadsheets.
- **Primary Time Drains**: Reading/organizing information (58.1%), writing reports/messages (54.8%), and categorizing data (48.4%).
- **High Market Appetite**: **83.9%** expressed strong interest in customizable AI for recurring jobs (58.1% "Very interested").
- **Key Decision Criteria (The 4 Dealbreakers)**:
  1. *Ease of Use* (32.3%): No complex developer setup or brittle glue code.
  2. *Accuracy & Zero Hallucinations* (29.0%): Deterministic validation with exact source citations.
  3. *Data Privacy & Confidentiality* (19.4%): On-device execution for proprietary research, academic records, and confidential data.
  4. *Price & Cost Affordability* (19.4%): Freedom from recurring monthly SaaS subscription fatigue ($20+/mo per tool).

### 5. Measured On-Device Improvement & The "Glass in Latte" Case
- **The High-Stakes Catch**: Out-of-the-box baseline local AI categorized a review stating *"Found shattered glass in my latte. Almost swallowed it!"* as sentiment `"unclear"` with `needs_review=false`—burying a life-threatening health hazard. The parent AI diagnosed the failure, generated an explicit safety rule, and the retrained Apprentice instantly categorized it as `"negative"` sentiment with `needs_review=true` to alert management within seconds.
- **Reserved Benchmark Uplift**: On a separate benchmark of 40 reserved survey responses that the parent AI never saw, human-approved instruction refinement achieved measurable uplift on the exact same local model (`qwen2.5-coder:3b`):
  - **Topic Micro-F1**: **76.5% → 84.1%** (+7.6 percentage points)
  - **Sentiment Accuracy**: **72.5% → 80.0%** (+7.5 percentage points)
  - **Schema Validity**: **97.5% → 100.0%** (zero parse errors)
  - **Review Flag Accuracy**: **95.0%** (safety triage fully preserved)

### 6. Pitch Deliverables
- **Pitch Deck (6 Core Slides)**: [`pitch-deliverables/output/Apprentice_Presentation.pptx`](pitch-deliverables/output/Apprentice_Presentation.pptx)
- **Speaker Cue Cards (Presenter Bullet Points)**: [`pitch-deliverables/output/Presentation_Script.txt`](pitch-deliverables/output/Presentation_Script.txt)
- **HTML Slide Notes**: [`pitch-deliverables/output/Presentation_Script.html`](pitch-deliverables/output/Presentation_Script.html)
- **Submission Package**: [`pitch-deliverables/output/Submission_Checklist.txt`](pitch-deliverables/output/Submission_Checklist.txt)
- **Demo Video Walkthrough**: [`demo-video/Apprentice_Demo.mp4`](demo-video/Apprentice_Demo.mp4)

---

## Current Milestone: Real Batch Baseline Evaluation

Before training any adapters, the application measures how well your original, unspecialized local model performs on the task.

### Empirical Baseline Experiment Results (`qwen2.5-coder:3b`)

A complete 61-row baseline experiment was executed using the local Ollama model (`qwen2.5-coder:3b` at `http://127.0.0.1:11434`, GGUF Q4_K_M, concurrency 1, Apple M2 MacBook Air 8 GB). All artifacts are published in [`evaluation/survey_baseline/`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline):

| Metric | Empirical Score | Detail / Denominator |
| :--- | :--- | :--- |
| **Output Schema Validity** | **100.0%** | 60 / 60 attempted rows strictly compliant JSON |
| **Topic Micro-F1** | **81.1%** *(81.2% unrounded)* | 69 TP / (69 TP + 10 FP + 22 FN) across 4 classes |
| **Sentiment Accuracy** | **75.0%** | 45 / 60 evaluated rows |
| **Review Flag Accuracy** | **93.3%** | 56 / 60 evaluated rows |
| **Blank Row Handling** | **100.0%** | 1 blank row (`DEV_61`) identified & skipped cleanly |
| **Request Failures** | **0.0%** | 0 timeouts, 0 errors, 100% real inference |
| **Total Runtime / Throughput**| **134.7s** | 0.45 responses/sec (warm latency: ~1.8s/row) |

#### Inspectable Artifacts
- **Comprehensive Evaluation Report**: [`evaluation/survey_baseline/report.md`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/report.md)
- **Dataset**: [`evaluation/survey_baseline/dataset.csv`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/dataset.csv) (60 labeled responses + 1 blank row)
- **Labeling Notes & Ambiguities**: [`evaluation/survey_baseline/labeling_notes.md`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/labeling_notes.md)
- **Frozen Configuration**: [`evaluation/survey_baseline/config.json`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/config.json)
- **Per-Row Predictions & Provenance**: [`evaluation/survey_baseline/predictions.jsonl`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/predictions.jsonl)
- **Exported CSV**: [`evaluation/survey_baseline/results.csv`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/results.csv)
- **Metrics Report**: [`evaluation/survey_baseline/metrics.json`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/metrics.json)
- **Reproducible Runner**: [`evaluation/survey_baseline/run_experiment.py`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/evaluation/survey_baseline/run_experiment.py)

#### How to Reproduce the Baseline Experiment
```bash
cd backend
uv run python ../evaluation/survey_baseline/run_experiment.py
```
*(Executes against an isolated temporary SQLite database and upload storage, leaving all user data untouched).*

---

### Hardware & Local Model Configuration
- **Runtime**: Ollama local inference endpoint at `http://127.0.0.1:11434`
- **Model**: `qwen2.5-coder:3b`
- **Status**: Original model — no adapter applied
- **Concurrency**: Bounded to 1 (recommended for M2 MacBook Air with 8 GB RAM) or 2 parallel requests to ensure memory stability.

---

## Quick Start

### 1. Prerequisites
- Python 3.10+ (and [uv](https://docs.astral.sh/uv/) recommended)
- Node.js 18+ and npm
- [Ollama](https://ollama.com/) running with `qwen2.5-coder:3b`:
  ```bash
  ollama run qwen2.5-coder:3b
  ```

### 2. Launch Application
```bash
./start.sh
```
This starts both the FastAPI backend (`http://127.0.0.1:8000`) and the Vite frontend (`http://localhost:5173`).

Or run separately:
- **Backend**: `cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
- **Frontend**: `cd frontend && npm run dev`

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Operating Modes & Honesty Guarantee

1. **Connected Mode**
   - Connects to your actual Ollama endpoint (`http://127.0.0.1:11434`) and runs real inference on `qwen2.5-coder:3b`.
   - Never substitutes simulated fixtures if inference fails or if the model is unreachable.
   - Requires the model to already be downloaded; it never automatically pulls unrequested models.
   - Simulated LoRA training and predetermined comparison are disabled in Connected Mode for this milestone.
   - The adapter control is disabled, displaying: `"Original model — no adapter"`.
   - Survey responses are processed entirely on your local machine and are **never** transmitted to any cloud API.

2. **Preview Mode**
   - Operates completely offline without Ollama or downloads.
   - Uses deterministic sample fixtures with visible provenance tags (`[PREVIEW FIXTURE]`).

---

## Architecture & Provenance Guarantees

### Storage Path Conventions & File Isolation
The backend strictly separates bundled read-only assets from writable project uploads and runtime data via explicit, strongly-typed settings in `app/config.py`:
- `data_dir`: General data folder containing the bundled read-only sample datasets.
- `sample_csv_path`: Direct path to the bundled read-only `sample_survey_labeled.csv`.
- `dev_sample_csv_path`: Direct path to the bundled read-only `dev_survey_60_labeled.csv`.
- `uploads_dir`: Writable folder for user-uploaded CSV datasets, segregated by project ID (`uploads/{project_id}/...`).
- `runs_dir`: Storage for adapter checkpoints and training run artifacts.
- `db_path`: SQLite database path (`data/apprentice.sqlite3`).

In tests, `conftest.py` isolates these paths into temporary folders (`tmp_path`) so user projects and datasets are never touched.

### Batch Execution Freezing & Provenance Tracking
- **Immutable Snapshot**: When a baseline evaluation batch is initialized, the backend captures an immutable configuration snapshot (`app_mode`, `model_name`, `model_endpoint`, `taxonomy`, `survey_context`, `coding_rules`, prompt template, and concurrency).
- **Execution Isolation**: Every row of the batch explicitly receives this frozen snapshot. Changing global settings mid-batch does not alter the running batch.
- **Strict Provenance**:
  - Every prediction record stores `is_simulated` (0 for real inference, 1 for preview fixtures) and `model_name`.
  - The UI displays explicit badges: `[REAL LOCAL INFERENCE]` vs `[SIMULATED PREVIEW FIXTURE]`.
  - CSV exports allocate collision-free metadata columns (`baseline_is_simulated`, `baseline_execution_mode`, `baseline_model_identity`) while preserving all original columns verbatim.

---

## CSV Dataset Format & Human Labels

The application accepts standard UTF-8 CSV files with quotes, commas, and multiline text. All original columns are preserved during export.

### Two-Stage CSV Upload Flow (Inspect -> Map -> Confirm)
To ensure reliable dataset handling for arbitrary CSV files (e.g. `id,comment` without predefined columns):
1. **Stage 1 (Inspect)**:
   - User drops or selects any CSV file (or chooses the fictional sample).
   - Backend endpoint `POST /api/datasets/inspect` parses the file with standard `csv.reader` (supporting `utf-8-sig` BOM, quotes, commas, and multiline cells) and stages it to a temporary staging area without mutating project state or creating permanent records.
   - Headers and a 5-row preview are returned with smart column mapping suggestions.
2. **Stage 2 (Map & Confirm)**:
   - User explicitly maps the required **Response** column and optional **ID**, **Topics**, **Sentiment**, and **Review** columns (or explicitly leaves them as "(None)").
   - `POST /api/datasets/confirm` verifies the mappings against the actual inspected file headers, computes a label validation summary (valid, valid empty `[]`, missing, invalid), and moves the file to a collision-free internal path (`uploads/{project_id}/{uuid[:8]}_{filename}`).
   - Canceling or replacing an inspected file never alters existing confirmed datasets or their saved mappings.

### Column Mapping & Label Format Rules
| Column Type | Description | Required? | Accepted Values / Format |
| :--- | :--- | :--- | :--- |
| **Response** | The survey feedback text to categorize. | **Yes** | Any string (blank/empty rows are flagged `blank_skipped` and reported). |
| **Response ID** | Stable unique identifier for the response. | Optional | String or number (e.g. `RESP_01`, `101`). |
| **Topics Label** | Human ground-truth category tags. | Optional | Semicolon-delimited (e.g. `drink_quality; price`), comma-delimited, or JSON list `["drink_quality"]`. Explicit empty list marked via `[]`, `none`, or `no topics`. Unknown topic tokens are preserved as row-level errors and excluded from topic micro-F1 without being silently converted to empty answers. |
| **Sentiment Label** | Human ground-truth sentiment. | Optional | `positive`, `negative`, `mixed`, `neutral`, `unclear` (case-insensitive, aliases like `pos`, `neg` supported). Invalid values are flagged as row errors and excluded only from sentiment accuracy. |
| **Needs Review Label** | Human ground-truth flag for supervisor review. | Optional | `true`/`false`, `yes`/`no`, or `1`/`0`. Invalid values are flagged as row errors and excluded only from review flag accuracy. |

> **Note on Multiple Topics & Ground Truth Reliability:** Survey comments often touch on multiple areas (e.g., great drink quality but bad pricing). Both the prompt and evaluator explicitly support multiple topic assignments per response. Unknown topic tokens are never silently converted into empty answers. Invalid labels are reported in the UI, excluded only from their affected metric, and other valid labels on the row continue to be evaluated.

### Interruption Recovery & Retries
If the backend server restarts while a baseline evaluation batch is running or queued:
- Startup recovery detects active batches and marks them `interrupted`.
- All rows processed before the interruption are preserved.
- The UI stops polling, displays an informative amber interruption alert, allows exporting partial CSV results, and provides a **Retry Batch** action.
- Retrying creates a linked new batch (`retried_from_batch_id`) while leaving the interrupted batch and its predictions intact.

### CSV Preservation & Collision Avoidance
When exporting evaluation results:
- Every original column and raw cell value is preserved verbatim, including multiline text, quotes, and commas.
- Evaluator columns use collision-free allocation (`_make_unique_col`): if the uploaded dataset already contains a column like `baseline_summary` or `baseline_status`, the exporter allocates `eval_baseline_summary` so user data is never overwritten.

### Example Fictional Labeled CSV (`sample_survey_labeled.csv`)
A fictional sample dataset is provided at [`backend/data/sample_survey_labeled.csv`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/backend/data/sample_survey_labeled.csv):

```csv
response_id,customer_name,feedback_text,label_topics,label_sentiment,label_needs_review
CF_01,Maya,"The oat milk cappuccino was silky and perfectly poured, but $7.50 is steep for a small cup.",drink_quality; price,mixed,false
CF_02,Alex,"Staff were super cheerful despite the morning rush! Ordered iced matcha and had it in 2 minutes flat.",service; drink_quality,positive,false
CF_03,Jordan,"Music is deafening inside, couldn't hear my zoom call and had to sit on the cold floor because zero outlets near chairs.",seating,negative,false
CF_04,Sam,"Found a rusty paperclip in my blueberry scone. When I told the cashier they just shrugged.",service,negative,true
CF_05,Taylor,"Regular drip coffee. Nothing special, tasted okay.",drink_quality,neutral,false
CF_06,Casey,"Great atmosphere for reading with comfortable chairs, but the pour-over was lukewarm and overpriced.",seating; drink_quality; price,mixed,false
CF_07,Morgan,"Waited 25 minutes in line only to be told they were out of oat milk and iced cups.",service,negative,false
CF_08,Robin,"Clean restrooms, super fast WiFi, and plenty of power outlets for students.",seating,positive,false
CF_09,Dana,"Found shards of green glass at the bottom of my cold brew! Manager didn't even apologize.",drink_quality; service,negative,true
CF_10,Pat,"Not sure if this place is open on Sundays? Nobody was there.",,unclear,false
CF_11,Jamie,"Line was long, but baristas moved fast. Cappuccino was great value for money.",service; price; drink_quality,positive,false
CF_12,Quinn,"",,,
```

*Disclaimer: This sample CSV is provided solely to check the workflow and automated evaluation machinery. It is not evidence of overall model quality or benchmark superiority.*

### Development Benchmark Dataset (`dev_survey_60_labeled.csv`)
An expanded 61-row fictional development survey dataset (60 labeled responses + 1 blank row) is provided at [`backend/data/dev_survey_60_labeled.csv`](file:///Users/lcooney/Documents/ChatGPT/HACKATHON/hackathon-project/backend/data/dev_survey_60_labeled.csv) for evaluating local models:
- **Coverage**: Single-topic and multi-topic feedback (2-4 categories across `drink_quality`, `service`, `price`, and `seating`).
- **Sentiment**: Balanced coverage of `positive`, `negative`, `mixed`, `neutral`, and `unclear`.
- **Linguistic Variation**: Implicit feedback, informal/slang expressions, spelling errors/typos, and negation.
- **Safety Hazards & Review Flags**: 10 rows flagged `needs_review=true` (physical hazards such as glass/staples, severe hygiene/chemical issues, and ambiguous/incomprehensible comments).
- **Zero-topic & Out-of-Domain**: Explicitly empty topic lists (`[]`) for unrelated or non-applicable comments.
- **Quoting & Parsing Robustness**: Quoted commas, escaped quotes (`""`), multiline cell text, and a blank response row.

---

## Automated Test Suite

All automated tests use an isolated temporary SQLite database fixture (`conftest.py`) so tests never mutate real project databases.

Run the unit test suite (using mocked local model service):
```bash
cd backend
uv run --with pytest --with pytest-asyncio pytest -m "not smoke"
```

Run all tests including live Ollama smoke checks:
```bash
cd backend
uv run --with pytest --with pytest-asyncio pytest
```

### Verified Acceptance Tests (36 passed):
1. **`test_csv_upload_flow.py`**:
   - Two-stage inspect -> map -> confirm flow for arbitrary CSVs (e.g. `id,comment`).
   - Preservation of column mappings across project retrieval and page refreshes.
   - Fully unlabeled CSV configuration with all optional columns mapped to None.
   - Robust parsing of quoted commas, multiline cell content, escaped quotes, and UTF-8 BOM (`utf-8-sig`).
   - Strict CSV parsing: rejection of malformed quoted input (e.g. unclosed quotes merging rows) with informative line numbers before staging or dataset confirmation.
   - Preservation of pending staged files and project state when confirmation fails (e.g., nonexistent column), allowing user correction and retry with the same staged upload.
   - Automatic rollback and cleanup on persistence failures to prevent falsely confirmed datasets or orphaned storage files.
   - Rejection with clear HTTP 400 errors for empty CSVs, missing/duplicate headers, and malformed rows.
   - Collision-free internal storage preserving separate files when uploading identical filenames.
2. **`test_baseline_batch.py`**:
   - Batch creation, queued/running/completed state transitions with mocked local model service.
   - Blank response rows flagged `blank_skipped` and reported in counts.
   - Cancellation mid-batch: runner stops cleanly and persists all rows processed up to cancellation.
   - Full persistence in SQLite and retrieval across page refreshes.
3. **`test_evaluator_advanced.py`**:
   - **Failed requests counted in denominator**: Verifies that failed predictions drop accuracy and F1 scores rather than being omitted.
   - **Partially labeled data**: Evaluates Topic Micro-F1, sentiment accuracy, and review flag accuracy only where valid ground-truth labels exist.
   - **Unlabeled datasets**: Verifies that unlabeled datasets do not fabricate accuracy scores (`is_unlabeled = True`).
   - **Schema validity**: Measured independently of label presence.
4. **`test_interruption_and_export.py`**:
   - **Interrupted batch marking**: Verifies backend restart automatically sets queued/running batches to `interrupted`.
   - **Export column collision avoidance**: Verifies that source columns colliding with evaluator output names (e.g. `baseline_summary`) are preserved and collision-free names are allocated.
   - **Retry batch linking**: Retrying an interrupted batch creates a new batch linked by `retried_from_batch_id` without altering past records.
5. **`test_routes_integration.py`**:
   - **CSV upload with custom mappings**: Verifies file upload via HTTP route, project column mappings persistence, and file storage under `settings.uploads_dir`.
   - **Sample retry route**: Verifies retry HTTP route creates linked batch on sample data.
   - **Mid-batch configuration isolation**: Verifies that mutating global mode, model name, and endpoint mid-batch does not alter the running batch; a subsequent batch uses the updated configuration.
   - **Connected mode error honesty**: Verifies that inference failure records an error status and never falls back to preview fixtures.
   - **Export provenance & source preservation**: Verifies exported CSV includes `baseline_is_simulated`, `baseline_execution_mode`, `baseline_model_identity` alongside all preserved source columns.
   - **End-to-End User Journey**: Verifies custom-column inspect -> mapping -> confirmation -> refresh persistence -> batch execution -> evaluation vs human labels -> provenance export.
6. **`test_job_contract.py`**:
   - Strict output schema validation: `{}` is rejected as invalid schema (`is_valid_schema=False`).
   - Strict boolean validation: `"needs_review": "false"` is rejected as invalid schema.
   - Valid zero-topic responses (`topics: []`) pass validation.
7. **`test_label_parser.py`**:
   - Multi-topic parsing (semicolons, commas, JSON lists, explicit `[]` and `none`).
   - Unknown topic tokens rejected as invalid (`is_valid=False`, `value=None`) and never treated as empty `[]`.
   - Sentiment normalization and aliases (`pos`, `neg`, `mixed`).
   - Boolean truthiness for review flags (`yes`/`no`, `1`/`0`, `true`/`false`).
   - Blank row detection.
8. **`test_csv_roundtrip.py`**:
   - Preserves commas inside quotes, multiline text, original IDs, and headers during import and export.
9. **`test_ollama_smoke.py`**:
   - Endpoint discovery verification (`http://127.0.0.1:11434`).
   - Real Ollama model inference smoke test executing live unadaptered generation on `qwen2.5-coder:3b`.

---

## Current Scope & Limitations
- **In Scope (Implemented)**:
  - Real Ollama batch baseline evaluation (`qwen2.5-coder:3b`).
  - Human label parsing, taxonomy validation, and multi-topic support.
  - Micro-F1, sentiment accuracy, review flag accuracy, schema validity, throughput, and error logging.
  - Safe cancellation and SQLite batch persistence.
  - CSV export with original columns preserved and predictions appended.
  - Bounded concurrency for memory stability on M2 8GB MacBook Air.
- **Out of Scope for this Milestone**:
  - LoRA fine-tuning and weight updates (intentionally disabled until baseline evaluation results justify specialization).

Connected parent analyses run as background jobs: POST returns accepted status promptly, and the UI polls saved status with elapsed time. Refreshing or clicking again while a job is analyzing reuses that job. Provider requests have a 180-second response timeout and a 190-second overall analysis-call deadline. No automatic retry occurs; a failed request may have reached the provider, so retry is deliberate. The provider/model/key are captured when the user starts the job and are not changed by later setup edits. Preview analysis remains immediate.
