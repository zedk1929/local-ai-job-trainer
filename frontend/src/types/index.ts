export type AppMode = 'preview' | 'connected';

export interface TaxonomyItem {
  id: string;
  name: string;
  description: string;
}

export interface MetricDefinition {
  id: string;
  name: string;
  description: string;
  unit: string;
  higher_is_better?: boolean;
}

export interface JobDefinition {
  id: string;
  title: string;
  version: string;
  description: string;
  is_active: boolean;
  config_schema: {
    survey_context_label: string;
    survey_context_description: string;
    default_taxonomy: TaxonomyItem[];
    default_rules: string[];
  };
  metrics: MetricDefinition[];
  supported_models: string[];
  supported_backends: string[];
}

export interface Project {
  id: string;
  name: string;
  job_id: string;
  description: string;
  survey_context: string;
  taxonomy: TaxonomyItem[];
  coding_rules: string[];
  active_adapter_id?: string | null;
  selected_dataset_id?: string | null;
  response_col?: string;
  id_col?: string;
  label_topics_col?: string;
  label_sentiment_col?: string;
  label_needs_review_col?: string;
  created_at: string;
  updated_at: string;
}

export interface SystemCapabilities {
  app_mode: AppMode;
  model_inference: {
    available: boolean;
    model_configured: boolean;
    model_name: string;
    model_path: string;
    endpoint_url: string;
    active_adapter: string | null;
    notes: string[];
  };
  supervisor_api: {
    configured: boolean;
    provider: string;
    model: string;
  };
  adapter_training: {
    supported: boolean;
    backend: string;
    message: string;
  };
}

export interface RunEvent {
  id: number;
  run_id: string;
  stage: string;
  level: 'info' | 'warning' | 'error';
  message: string;
  timestamp: string;
}

export interface EvaluationResultData {
  eval_split: string;
  sample_size: number;
  topic_micro_f1: number;
  sentiment_accuracy: number;
  schema_validity: number;
  review_flag_accuracy: number;
  is_simulated_fixture: boolean;
}

export interface RunResults {
  baseline: EvaluationResultData;
  candidate: EvaluationResultData;
  differences: {
    topic_micro_f1: number;
    sentiment_accuracy: number;
    schema_validity: number;
    review_flag_accuracy: number;
    net_score: number;
  };
  outcome: 'improved' | 'regressed' | 'neutral';
  summary: string;
  is_simulated_fixture: boolean;
  adapter_id: string;
  model_name: string;
  example_comparisons: Array<{
    input: string;
    baseline: any;
    specialist: any;
    ground_truth: any;
  }>;
}

export interface Run {
  id: string;
  project_id: string;
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'canceled' | 'interrupted';
  current_stage: string;
  config: Record<string, any>;
  results?: RunResults | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface SingleInferenceResult {
  topics: string[];
  sentiment: string;
  summary: string;
  needs_review: boolean;
  review_reason?: string | null;
  is_valid_schema: boolean;
  is_simulated_fixture: boolean;
  model_used: string;
  adapter_used?: string | null;
  latency_seconds?: number;
}

export interface ClassStat {
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
}

export interface BaselineEvaluationReport {
  is_unlabeled: boolean;
  is_simulated?: boolean;
  execution_mode?: string;
  model_name?: string;
  total_rows: number;
  attempted_rows: number;
  blank_rows: number;
  failed_requests: number;

  schema_valid_count: number;
  schema_validity_pct: number;

  has_topic_labels: boolean;
  topic_labeled_rows: number;
  topic_coverage_pct: number;
  topic_tp: number;
  topic_fp: number;
  topic_fn: number;
  topic_precision: number;
  topic_recall: number;
  topic_micro_f1: number | null;
  per_topic_breakdown: Record<string, ClassStat>;

  has_sentiment_labels: boolean;
  sentiment_labeled_rows: number;
  sentiment_coverage_pct: number;
  sentiment_correct: number;
  sentiment_accuracy: number | null;

  has_review_flag_labels: boolean;
  review_flag_labeled_rows: number;
  review_flag_coverage_pct: number;
  review_flag_correct: number;
  review_flag_accuracy: number | null;

  total_elapsed_seconds: number;
  throughput_items_per_sec: number;
  average_latency_seconds: number;
  scientific_disclaimer: string;
}

export interface BaselineBatch {
  id: string;
  project_id: string;
  dataset_id: string;
  status: 'queued' | 'running' | 'completed' | 'canceled' | 'failed' | 'interrupted';
  model_name: string;
  model_endpoint: string;
  job_version: string;
  app_mode?: string;
  retried_from_batch_id?: string | null;
  concurrency: number;
  total_rows: number;
  processed_rows: number;
  error_count: number;
  blank_count: number;
  elapsed_seconds: number;
  throughput_items_per_sec: number;
  snapshot: Record<string, any>;
  metrics: BaselineEvaluationReport | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface BaselinePrediction {
  id: number;
  batch_id: string;
  row_index: number;
  response_id: string;
  response_text: string;
  original_data: Record<string, any>;
  ground_truth_topics: string[] | null;
  ground_truth_sentiment: string | null;
  ground_truth_needs_review: boolean | null;
  ground_truth_label_errors?: string[];
  raw_model_output?: any;
  predicted_topics: string[];
  predicted_sentiment: string;
  generated_summary: string;
  predicted_needs_review: boolean;
  review_reason: string;
  is_valid_schema: boolean;
  schema_errors: string[];
  status: 'success' | 'error' | 'blank_skipped';
  error_message: string | null;
  latency_seconds: number;
  is_simulated?: boolean;
  model_name?: string;
}

export interface DatasetRecord {
  id: string;
  project_id: string;
  filename: string;
  filepath: string;
  row_count: number;
  response_col: string;
  id_col?: string;
  label_topics_col?: string;
  label_sentiment_col?: string;
  label_needs_review_col?: string;
  origin: string;
  created_at: string;
}

export interface DatasetRowLabelError {
  row_idx: number;
  response_id?: string;
  raw_value: string;
  error: string;
}

export interface DatasetValidationSummary {
  total_rows: number;
  valid_response_rows: number;
  blank_response_rows: number;

  has_topics_label: boolean;
  topics_labeled_rows: number;
  topics_valid_empty_rows?: number;
  topics_invalid_rows?: number;
  topics_missing_rows?: number;
  topic_errors?: DatasetRowLabelError[];
  unrecognized_topic_tokens: string[];

  has_sentiment_label: boolean;
  sentiment_labeled_rows: number;
  sentiment_invalid_rows?: number;
  sentiment_missing_rows?: number;
  sentiment_errors?: DatasetRowLabelError[];

  has_needs_review_label: boolean;
  needs_review_labeled_rows: number;
  needs_review_invalid_rows?: number;
  needs_review_missing_rows?: number;
  needs_review_errors?: DatasetRowLabelError[];

  is_unlabeled: boolean;
}

export interface InspectedCsvResponse {
  temp_file_id: string;
  filename: string;
  is_sample: boolean;
  columns: string[];
  row_count: number;
  preview_rows: any[];
  suggested_mappings: {
    response_col: string;
    id_col: string;
    label_topics_col: string;
    label_sentiment_col: string;
    label_needs_review_col: string;
  };
}

export interface ConfirmDatasetRequest {
  project_id: string;
  temp_file_id: string;
  filename: string;
  response_col: string;
  id_col?: string;
  label_topics_col?: string;
  label_sentiment_col?: string;
  label_needs_review_col?: string;
  is_sample?: boolean;
}
