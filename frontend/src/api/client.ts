import {
  JobDefinition,
  Project,
  SystemCapabilities,
  Run,
  RunEvent,
  SingleInferenceResult,
  AppMode,
  BaselineBatch,
  BaselinePrediction,
  DatasetValidationSummary,
  InspectedCsvResponse,
  ConfirmDatasetRequest
} from '../types';

const API_BASE = '/api';

export const api = {
  // Health & Capabilities
  async getCapabilities(): Promise<SystemCapabilities> {
    const res = await fetch(`${API_BASE}/capabilities`);
    return res.json();
  },

  async setAppMode(mode: AppMode): Promise<{ app_mode: AppMode }> {
    const res = await fetch(`${API_BASE}/setup/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_mode: mode }),
    });
    return res.json();
  },

  // Setup
  async updateModelConfig(data: { model_path?: string; endpoint_url?: string; model_name?: string }) {
    const res = await fetch(`${API_BASE}/setup/model`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async updateSupervisorConfig(data: { provider?: string; model?: string; api_key?: string }) {
    const res = await fetch(`${API_BASE}/setup/supervisor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async testSupervisor(): Promise<{ connected: boolean; provider: string; message: string }> {
    const res = await fetch(`${API_BASE}/setup/supervisor/test`, {
      method: 'POST',
    });
    return res.json();
  },

  // Jobs
  async listJobs(): Promise<{ jobs: JobDefinition[]; future_presets: any[] }> {
    const res = await fetch(`${API_BASE}/jobs`);
    return res.json();
  },

  async getJob(jobId: string): Promise<JobDefinition> {
    const res = await fetch(`${API_BASE}/jobs/${jobId}`);
    return res.json();
  },

  // Projects
  async listProjects(): Promise<Project[]> {
    const res = await fetch(`${API_BASE}/projects`);
    return res.json();
  },

  async createProject(data: Partial<Project>): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async getProject(projectId: string): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects/${projectId}`);
    return res.json();
  },

  async updateProject(projectId: string, data: Partial<Project>): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects/${projectId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  // Datasets
  async inspectCsv(
    file?: File,
    source?: string
  ): Promise<InspectedCsvResponse> {
    const formData = new FormData();
    if (file) {
      formData.append('file', file);
    }
    if (source) {
      formData.append('source', source);
    }
    const res = await fetch(`${API_BASE}/datasets/inspect`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to inspect CSV');
    }
    return res.json();
  },

  async confirmDataset(data: ConfirmDatasetRequest): Promise<{
    dataset: any;
    columns: string[];
    row_count: number;
    preview_rows: any[];
    validation_summary: DatasetValidationSummary;
  }> {
    const res = await fetch(`${API_BASE}/datasets/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to confirm dataset');
    }
    return res.json();
  },

  async uploadCsv(
    projectId: string,
    responseCol: string,
    idCol: string,
    file: File,
    labelTopicsCol: string = '',
    labelSentimentCol: string = '',
    labelNeedsReviewCol: string = ''
  ): Promise<{
    dataset: any;
    columns: string[];
    row_count: number;
    preview_rows: any[];
    validation_summary: DatasetValidationSummary;
  }> {
    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('response_col', responseCol);
    formData.append('id_col', idCol);
    formData.append('label_topics_col', labelTopicsCol);
    formData.append('label_sentiment_col', labelSentimentCol);
    formData.append('label_needs_review_col', labelNeedsReviewCol);
    formData.append('file', file);

    const res = await fetch(`${API_BASE}/datasets/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to upload CSV');
    }
    return res.json();
  },

  async generateSynthetic(projectId: string, count: number = 6) {
    const res = await fetch(`${API_BASE}/datasets/synthetic-generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, count }),
    });
    return res.json();
  },

  // Baseline Evaluation (Milestone)
  async startBaselineBatch(data: {
    project_id: string;
    dataset_id?: string;
    rows?: any[];
    response_col: string;
    id_col?: string;
    label_topics_col?: string;
    label_sentiment_col?: string;
    label_needs_review_col?: string;
    concurrency?: number;
  }): Promise<BaselineBatch> {
    const res = await fetch(`${API_BASE}/baseline/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to start baseline batch');
    }
    return res.json();
  },

  async getActiveBaselineBatch(projectId: string): Promise<{ batch: BaselineBatch | null }> {
    const res = await fetch(`${API_BASE}/baseline/active/${projectId}`);
    return res.json();
  },

  async getBaselineBatch(batchId: string): Promise<{ batch: BaselineBatch }> {
    const res = await fetch(`${API_BASE}/baseline/batch/${batchId}`);
    return res.json();
  },

  async getBaselinePredictions(
    batchId: string,
    filterMode: 'all' | 'mistakes' | 'errors' | 'flagged' = 'all'
  ): Promise<{ predictions: BaselinePrediction[]; count: number }> {
    const res = await fetch(`${API_BASE}/baseline/batch/${batchId}/predictions?filter_mode=${filterMode}`);
    return res.json();
  },

  async cancelBaselineBatch(batchId: string): Promise<{ status: string; message: string }> {
    const res = await fetch(`${API_BASE}/baseline/batch/${batchId}/cancel`, {
      method: 'POST',
    });
    return res.json();
  },

  async retryBaselineBatch(batchId: string): Promise<BaselineBatch> {
    const res = await fetch(`${API_BASE}/baseline/batch/${batchId}/retry`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to retry baseline batch');
    }
    return res.json();
  },

  async getDatasets(projectId: string): Promise<{ datasets: any[] }> {
    const res = await fetch(`${API_BASE}/datasets/${projectId}`);
    return res.json();
  },

  async getDatasetPreview(projectId: string, datasetId: string, limit: number = 5): Promise<{ columns: string[]; row_count: number; preview_rows: any[] }> {
    const res = await fetch(`${API_BASE}/datasets/${projectId}/${datasetId}/preview?limit=${limit}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to load dataset preview');
    }
    return res.json();
  },

  async exportBaselineCsv(batchId: string) {
    const res = await fetch(`${API_BASE}/baseline/batch/${batchId}/export`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error('Failed to export baseline CSV');
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `baseline_evaluation_${batchId}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
  },

  // Runs (LoRA Experiment)
  async startRun(projectId: string, config: any = {}): Promise<Run> {
    const res = await fetch(`${API_BASE}/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, ...config }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to start run');
    }
    return res.json();
  },

  async getRun(runId: string): Promise<Run> {
    const res = await fetch(`${API_BASE}/runs/${runId}`);
    return res.json();
  },

  async getRunEvents(runId: string): Promise<{ events: RunEvent[] }> {
    const res = await fetch(`${API_BASE}/runs/${runId}/events`);
    return res.json();
  },

  async cancelRun(runId: string): Promise<{ status: string; message: string }> {
    const res = await fetch(`${API_BASE}/runs/${runId}/cancel`, {
      method: 'POST',
    });
    return res.json();
  },

  // Inference & Export (Playground)
  async inferSingle(projectId: string, responseText: string, useAdapter: boolean = false): Promise<{ result: SingleInferenceResult; active_adapter?: string | null; adapter_note?: string }> {
    const res = await fetch(`${API_BASE}/specialist/infer-single`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, response_text: responseText, use_adapter: useAdapter }),
    });
    return res.json();
  },

  async inferBatch(projectId: string, items: any[], responseCol: string, useAdapter: boolean = false) {
    const res = await fetch(`${API_BASE}/specialist/infer-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, items, response_col: responseCol, use_adapter: useAdapter }),
    });
    return res.json();
  },

  async exportCsv(projectId: string, processedRows: any[], originalColumns: string[]) {
    const res = await fetch(`${API_BASE}/specialist/export-csv`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, processed_rows: processedRows, original_columns: originalColumns }),
    });
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cleaned_survey_project_${projectId}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
  }
};
