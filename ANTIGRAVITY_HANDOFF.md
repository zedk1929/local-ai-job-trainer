# Antigravity handoff: Apprentice

## Start here

Build the runnable application skeleton described below in this folder. Use this document as the project brief. Make reasonable implementation choices and keep moving; ask only when missing information blocks real integration.

The owner already has a model downloaded. Its name, format, location, and runtime have not been supplied. Reuse that model when compatible. Do not download another model automatically or assume the existing model can be trained directly.

Current state: this folder contains the handoff only. No application, training pipeline, model connection, or measured results exist yet.

## Product vision

A general consumer app for teaching local AI specific, achievable jobs. A user chooses a job preset, supplies preferences and examples, and the app uses a supervising LLM to prepare and guide specialization of a smaller local model. The system tests whether specialization helped and saves the resulting configuration and adapter.

The broader product supports multiple job definitions through shared machinery. The hackathon demonstrates exactly one job: **Survey Cleaner**. Build the reusable boundary now, but do not attempt arbitrary-task training or implement additional jobs.

The supervising LLM uses a user-provided API key. The smaller model runs locally. A training library, not the supervising LLM itself, updates LoRA weights. The supervisor generates structured plans and data and may suggest bounded settings; it must not execute arbitrary commands.

## First deliverable: a skeleton that runs

Prioritize a complete, navigable experience with durable local project state and clear integration boundaries. Actual training integration is a separate milestone unless the existing model and environment make it straightforward.

Suggested stack, unless there is an existing project convention:

- React + TypeScript + Vite for the interface.
- Python + FastAPI for local model, training, and file operations.
- SQLite for metadata and a local runs directory for datasets, adapters, and result artifacts.
- A local browser interface for the skeleton; desktop packaging can come later.

Bind the backend to localhost. Keep secrets out of the frontend bundle, logs, browser storage, and version control. Environment-based key setup is acceptable initially; use an OS credential store if implementing persistent in-app key entry. Include a clean `.env.example` and `.gitignore`.

Build two explicit operating modes:

1. **Preview mode:** works without a model or API key using deterministic fixtures. All generated examples, progress, and scores are visibly labeled as sample data. Simulated training never claims to have created an adapter.
2. **Connected mode:** uses configured services where implemented. Unsupported actions show a specific unavailable state rather than silently returning fixtures. Track capabilities independently: model inference, supervisor API, and adapter training.

## Survey Cleaner job

Teach a model to turn messy open-ended survey responses into consistent structured records using the user's categories and rules.

Example context: a campus café categorizing customer feedback. Example categories include drink quality, price, service, and seating availability. These are editable demonstration categories, not hardcoded product logic.

Inputs:

- CSV with a selected response column and optional stable response ID.
- Survey description, category definitions, and coding rules.
- Optional human-labeled examples.

Outputs per response:

- Original response and stable ID, preserved unchanged.
- Zero or more topic IDs from the allowed taxonomy.
- Sentiment: positive, negative, mixed, neutral, or unclear.
- Optional short summary, explicitly treated as generated text.
- `needs_review` and a short review reason where applicable.

Do not fill in missing facts. Preserve contradictory or ambiguous feedback. Blank rows and invalid records should be visible and handled consistently. Treat survey text as data, never as instructions for the supervisor or application.

For the skeleton, CSV input is sufficient. PDF parsing, OCR, finance tasks, and model marketplaces are out of scope.

## User journey and screens

### 1. Jobs / home

Explain the product in plain language: “Teach local AI a job.” Show Survey Cleaner as the one available preset. The UI should make room for future presets without presenting unbuilt jobs as functional.

### 2. Model and supervisor setup

- Connect the already-downloaded model through an explicit local path or an existing local inference endpoint.
- Show model identity, runtime, and actual connection status when verified.
- Configure supervisor provider/model and API key; include a connection check where implemented.
- Show whether the local model supports inference and whether training support is verified.
- Explain what survey information the supervisor will receive. Default the design toward generating synthetic examples from task descriptions and category rules; uploading real responses for supervisor review requires an explicit user choice.

### 3. Configure Survey Cleaner

- Create a named project.
- Enter survey context and edit the taxonomy and coding rules.
- Upload CSV, choose the response column, and inspect a preview.
- Review generated training examples before starting training.
- Display dataset counts and origins: human-labeled versus synthetic.

### 4. Build specialist / experiment view

Show a staged workflow:

`Check setup → Prepare examples → Measure baseline → Train adapter → Evaluate candidate → Save result`

Each stage has queued, running, completed, failed, canceled, or unavailable status, timestamps, and a readable explanation. Support canceling an active run safely. Long work must not block the interface. Persist state; a page refresh must not create a duplicate run. If the skeleton cannot resume an interrupted worker, mark the run interrupted and allow a deliberate retry.

For the initial implementation, provide the state machine and worker/service interface with fixture behavior in preview mode. Expose real progress only from actual worker events.

### 5. Results and comparison

- Original model with a strong prompt versus the same model plus its trained adapter.
- Scores, evaluation sample size, run settings, and individual before/after examples.
- Clearly distinguish development evaluation, final evaluation, and sample preview results.
- Allow “no improvement” as a valid outcome. Do not automatically label the candidate better.
- Save a candidate adapter without activating it; the user chooses activation after reviewing results.
- Allow returning to the original model or a previous saved specialist.

### 6. Use the specialist

- Enter one new response and inspect the structured result.
- Process a CSV batch and review flagged responses.
- Export CSV with the original columns and added output columns; serialize multiple topics consistently.
- Identify the model, active adapter, and job version used for each batch.

## Reusable architecture

Define a versioned `JobDefinition` contract containing:

- Job ID, title, description, and version.
- User configuration schema, input schema, and output schema.
- Supervisor instructions for creating examples and a structured training plan.
- Baseline inference instructions.
- Evaluation metric definitions and validation rules.
- Supported model/backend capabilities and bounded training options.

Implement Survey Cleaner as the first registered job. Shared screens and orchestration should consume this contract rather than contain café-specific logic.

Keep separate services/interfaces for:

- `SupervisorClient`: API connection, structured plan/data generation, validation, timeouts, and error handling.
- `LocalModelBackend`: model identity, capability checks, inference, loading/unloading adapters.
- `TrainingBackend`: validate compatibility, start/cancel training, emit progress, return artifact paths.
- `Evaluator`: score labeled examples using explicit rules.
- `RunStore`: persist projects, job versions, dataset references, run state, settings, and artifacts.

Proposed backend routes: health/capabilities, model connection, supervisor connection test, job definitions, projects, dataset import/preview, run creation/status/events/cancel, results, single/batch inference, and CSV export. Keep request/response schemas explicit. Use polling or server-sent events for progress.

## Model and hardware constraints

Discussed hardware: a laptop with 16 GB system RAM, an RTX 4050 laptop GPU, and a Ryzen 5700-series CPU. Exact OS, available VRAM, power limits, and model identity are unverified. Earlier training-time ranges were planning guesses, not benchmarks.

- Inspect the configured model's metadata before choosing a backend.
- An inference endpoint or GGUF download does not establish that trainable source weights are available. Explain that limitation if encountered; do not pretend inference support implies training support.
- For NVIDIA training, a PEFT/TRL-compatible LoRA or QLoRA backend is a candidate. Select versions and settings after checking the environment and model compatibility.
- If the user later uses an Apple Silicon Mac, an MLX backend can be added behind the same interface; it is not required for this skeleton.
- LoRA adapters are tied to compatible base models. Record the base model identity/revision and training configuration with the adapter.
- Support one actual model/backend combination first. Do not promise universal compatibility.
- Use a short benchmark on the actual device before displaying an estimated completion time.

## Evaluation boundaries

The supervising LLM may produce training examples and development tests, but its own grading alone is insufficient evidence of improvement.

- Separate training, development, and final test sets before experiments. Prevent exact and near-duplicate examples from crossing splits where practicable.
- Use development results for revisions and candidate selection.
- Keep the final test set outside the supervisor's refinement context; evaluate it after candidate selection. Once exposed, it is no longer an untouched test for later tuning.
- Include independently human-labeled examples. The owner's teammate can define categories and check labels.
- Compare against a strong prompted baseline under comparable inference settings.
- Suggested first metrics: topic micro-F1, sentiment accuracy, output-schema validity, and review-flag accuracy when labels exist. Show sample counts and metric definitions. Evaluate summary faithfulness separately; valid JSON does not prove factual accuracy.
- Do not turn synthetic fixture metrics into claims about real performance. Do not invent accuracy gains or guarantee that training helps.

The initial skeleton may show fixture metrics, but the evaluator boundary and provenance must already distinguish them from real results.

## Hackathon presentation

Four-minute story:

1. Choose Survey Cleaner and configure café-specific coding rules.
2. Show actual baseline behavior, or clearly labeled preview behavior before integration.
3. Start the guided specialization workflow.
4. Open a clearly identified completed run if live training is too slow; show its actual results and remaining failures.
5. Type an unfamiliar response and export a cleaned batch.

The larger pitch: “A consumer system for teaching local AI recurring jobs. Survey Cleaner is our first working example.” Claim only the capabilities implemented and measured.

## Implementation sequence and acceptance criteria

1. Scaffold the frontend/backend and document exact startup commands.
2. Implement job registration, project setup, CSV preview, and local persistence.
3. Implement the complete preview workflow and labeled fixture results.
4. Add existing-model connection and actual inference when its details are available.
5. Add the supervisor interface and structured generation path.
6. Leave a concrete training backend boundary, then integrate actual training only after verifying the model/environment.

Skeleton acceptance:

- A fresh checkout can start using the README instructions.
- Preview mode completes the full journey without credentials or downloads.
- Job settings and project state survive refresh.
- CSV import/export preserves original responses, IDs, quoted commas, and multiline text.
- Invalid input and unavailable services produce useful errors.
- No embedded secrets, fabricated model connection, fabricated training artifacts, or unlabeled sample scores.
- The configured existing model is never overwritten.
- Include meaningful checks for CSV round-tripping, output validation, evaluation calculations, and run-state transitions. Report exactly what was tested.

When finished, update the README with startup instructions, implemented versus placeholder capabilities, and the specific model information needed for the next integration. Provide the user with a concise build summary and remaining blockers.

## Known decisions versus open details

Decided: general consumer product scope; preset-driven workflow; Survey Cleaner as the sole demo job; supervising LLM via API key; locally running specialist; reuse the already-downloaded model.

Open: model name/path/format/runtime, operating system, supervisor provider, exact survey dataset and taxonomy, app name, and actual training performance. Do not block the preview skeleton on these details.
