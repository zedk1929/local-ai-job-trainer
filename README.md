# Local AI Job Trainer

A consumer application for teaching local AI models specific, recurring jobs. The application evaluates local model performance on structured tasks and prepares them for task specialization.

The hackathon preset is **Survey Cleaner**, which transforms unstructured open-ended survey feedback into consistent structured records using customizable categories and coding rules.

---

## Current Milestone: Real Batch Baseline Evaluation

Before training any adapters, the application measures how well your original, unspecialized local model performs on the task.

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
- `uploads_dir`: Writable folder for user-uploaded CSV datasets, segregated by project ID (`uploads/{project_id}/...`).
- `runs_dir`: Storage for adapter checkpoints and training run artifacts.
- `db_path`: SQLite database path (`data/trainer.sqlite3`).

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
