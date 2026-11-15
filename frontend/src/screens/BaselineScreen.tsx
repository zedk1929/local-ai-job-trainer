import React, { useState, useEffect } from 'react';
import { Project, BaselineBatch, BaselinePrediction, AppMode, SystemCapabilities, DatasetRecord } from '../types';
import { api } from '../api/client';
import {
  Play,
  Square,
  RefreshCw,
  Download,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Cpu,
  Layers,
  HelpCircle,
  Filter,
  FileSpreadsheet,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  RotateCcw
} from 'lucide-react';

interface BaselineScreenProps {
  project: Project | null;
  appMode: AppMode;
  capabilities: SystemCapabilities | null;
  onNavigate: (screen: string) => void;
  onUpdateProject?: (updated: Project) => void;
}

export const BaselineScreen: React.FC<BaselineScreenProps> = ({
  project,
  appMode,
  capabilities,
  onNavigate,
  onUpdateProject,
}) => {
  if (!project) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center space-y-4">
        <h2 className="text-xl font-bold text-white">No Project Selected</h2>
        <button
          onClick={() => onNavigate('jobs')}
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold"
        >
          Go to Jobs
        </button>
      </div>
    );
  }

  const [activeBatch, setActiveBatch] = useState<BaselineBatch | null>(null);
  const [predictions, setPredictions] = useState<BaselinePrediction[]>([]);
  const [filterMode, setFilterMode] = useState<'all' | 'mistakes' | 'errors' | 'flagged'>('all');
  const [concurrency, setConcurrency] = useState<number>(1);
  const [starting, setStarting] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [loadingPreds, setLoadingPreds] = useState(false);

  // Datasets state
  const [availableDatasets, setAvailableDatasets] = useState<DatasetRecord[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>(
    project.selected_dataset_id || 'sample_cafe_labeled'
  );
  const [datasetPreview, setDatasetPreview] = useState<{
    columns: string[];
    row_count: number;
    preview_rows: any[];
  } | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);

  // Fetch datasets for project
  const loadDatasets = async () => {
    try {
      const res = await api.getDatasets(project.id);
      setAvailableDatasets(res.datasets || []);
      // If project has selected_dataset_id that still exists, use it
      if (project.selected_dataset_id && res.datasets.some((d: any) => d.id === project.selected_dataset_id)) {
        setSelectedDatasetId(project.selected_dataset_id);
      }
    } catch (err) {
      console.error('Failed to load datasets:', err);
    }
  };

  // Fetch active/latest batch
  const fetchActiveBatch = async () => {
    try {
      const res = await api.getActiveBaselineBatch(project.id);
      if (res.batch) {
        setActiveBatch(res.batch);
      }
    } catch (err) {
      console.error('Failed to fetch active baseline batch:', err);
    }
  };

  useEffect(() => {
    loadDatasets();
    fetchActiveBatch();
  }, [project.id]);

  // Load preview whenever selected dataset changes
  useEffect(() => {
    const fetchPreview = async () => {
      setLoadingPreview(true);
      try {
        const preview = await api.getDatasetPreview(project.id, selectedDatasetId, 5);
        setDatasetPreview(preview);
      } catch (err) {
        console.error('Failed to fetch dataset preview:', err);
        setDatasetPreview(null);
      } finally {
        setLoadingPreview(false);
      }
    };
    fetchPreview();
  }, [project.id, selectedDatasetId]);

  // Handle dataset selection change
  const handleSelectDataset = async (datasetId: string) => {
    setSelectedDatasetId(datasetId);
    try {
      // Find dataset to restore its column mappings if available
      const ds = availableDatasets.find((d) => d.id === datasetId);
      const updatedFields: any = { selected_dataset_id: datasetId };
      if (ds) {
        if (ds.response_col) updatedFields.response_col = ds.response_col;
        if (ds.id_col !== undefined) updatedFields.id_col = ds.id_col;
        if (ds.label_topics_col !== undefined) updatedFields.label_topics_col = ds.label_topics_col;
        if (ds.label_sentiment_col !== undefined) updatedFields.label_sentiment_col = ds.label_sentiment_col;
        if (ds.label_needs_review_col !== undefined) updatedFields.label_needs_review_col = ds.label_needs_review_col;
      } else if (datasetId === 'sample_cafe_labeled' || datasetId === 'sample_dev_60') {
        updatedFields.response_col = 'feedback_text';
        updatedFields.id_col = 'response_id';
        updatedFields.label_topics_col = 'label_topics';
        updatedFields.label_sentiment_col = 'label_sentiment';
        updatedFields.label_needs_review_col = 'label_needs_review';
      }
      const updated = await api.updateProject(project.id, updatedFields);
      if (onUpdateProject) {
        onUpdateProject(updated);
      }
    } catch (err) {
      console.error('Failed to persist selected dataset to project:', err);
    }
  };

  // Polling loop when batch is running
  useEffect(() => {
    if (!activeBatch) return;
    if (activeBatch.status !== 'running' && activeBatch.status !== 'queued') {
      // Terminal state (completed, interrupted, canceled, failed), load predictions
      loadPredictions(activeBatch.id, filterMode);
      return;
    }

    const interval = setInterval(async () => {
      try {
        const res = await api.getBaselineBatch(activeBatch.id);
        setActiveBatch(res.batch);
        if (
          res.batch.status === 'completed' ||
          res.batch.status === 'failed' ||
          res.batch.status === 'canceled' ||
          res.batch.status === 'interrupted'
        ) {
          loadPredictions(res.batch.id, filterMode);
        }
      } catch (err) {
        console.error('Error polling batch:', err);
      }
    }, 1200);

    return () => clearInterval(interval);
  }, [activeBatch?.id, activeBatch?.status, filterMode]);

  // Load predictions for batch
  const loadPredictions = async (batchId: string, filter: 'all' | 'mistakes' | 'errors' | 'flagged') => {
    setLoadingPreds(true);
    try {
      const res = await api.getBaselinePredictions(batchId, filter);
      setPredictions(res.predictions || []);
    } catch (err) {
      console.error('Failed to load predictions:', err);
    } finally {
      setLoadingPreds(false);
    }
  };

  // Start baseline evaluation batch
  const handleStartBaseline = async () => {
    const targetResponseCol = project.response_col || 'feedback_text';
    if (!targetResponseCol.trim()) {
      alert('Please configure a valid response column on the Configure screen before starting evaluation.');
      return;
    }

    setStarting(true);
    try {
      const batch = await api.startBaselineBatch({
        project_id: project.id,
        dataset_id: selectedDatasetId,
        response_col: targetResponseCol,
        id_col: project.id_col || undefined,
        label_topics_col: project.label_topics_col || undefined,
        label_sentiment_col: project.label_sentiment_col || undefined,
        label_needs_review_col: project.label_needs_review_col || undefined,
        concurrency: concurrency,
      });
      setActiveBatch(batch);
      setPredictions([]);
    } catch (err: any) {
      alert(err.message || 'Failed to start baseline batch');
    } finally {
      setStarting(false);
    }
  };

  // Cancel running batch
  const handleCancelBatch = async () => {
    if (!activeBatch) return;
    setCanceling(true);
    try {
      await api.cancelBaselineBatch(activeBatch.id);
      const res = await api.getBaselineBatch(activeBatch.id);
      setActiveBatch(res.batch);
    } catch (err: any) {
      alert(err.message || 'Failed to cancel batch');
    } finally {
      setCanceling(false);
    }
  };

  // Retry batch
  const handleRetryBatch = async () => {
    if (!activeBatch) return;
    setRetrying(true);
    try {
      const newBatch = await api.retryBaselineBatch(activeBatch.id);
      setActiveBatch(newBatch);
      setPredictions([]);
    } catch (err: any) {
      alert(err.message || 'Failed to retry batch');
    } finally {
      setRetrying(false);
    }
  };

  // Export CSV (available whenever processed_rows > 0)
  const handleExport = async () => {
    if (!activeBatch) return;
    try {
      await api.exportBaselineCsv(activeBatch.id);
    } catch (err: any) {
      alert(err.message || 'Export failed');
    }
  };

  const isRunning = activeBatch?.status === 'running' || activeBatch?.status === 'queued';
  const isInterrupted = activeBatch?.status === 'interrupted';
  const metrics = activeBatch?.metrics;

  // Selected dataset meta
  const currentDatasetRecord = availableDatasets.find((d) => d.id === selectedDatasetId);
  const currentDatasetName =
    selectedDatasetId === 'sample_dev_60'
      ? 'Fictional Dev Benchmark Dataset (Built-in, 61 rows)'
      : selectedDatasetId === 'sample_cafe_labeled'
      ? 'Fictional Sample Café Feedback (Built-in, 12 rows)'
      : currentDatasetRecord
      ? `${currentDatasetRecord.filename} (${currentDatasetRecord.row_count} rows)`
      : selectedDatasetId;

  // Frozen batch model label
  const batchModelLabel = activeBatch ? activeBatch.model_name : capabilities?.model_inference.model_name || 'qwen2.5-coder:3b';
  const batchModeLabel = activeBatch?.app_mode || appMode;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      {/* Screen Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800">
              Evaluation Milestone
            </span>
            <span className="text-xs text-slate-400">· Project: {project.name}</span>
          </div>
          <h1 className="text-2xl font-bold text-white mt-1">Real Batch Baseline Evaluation</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Measure how well the unspecialized base model performs on your survey rules before considering fine-tuning.
          </p>
        </div>

        {/* Model & Runtime Status Pill (Provenance) */}
        <div className="flex flex-col sm:items-end gap-1.5">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs">
            <Cpu className="w-4 h-4 text-blue-400" />
            <span className="font-semibold text-white">
              {batchModelLabel}
            </span>
            {batchModeLabel === 'preview' ? (
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-amber-950 text-amber-300 border border-amber-800">
                Simulated Preview Fixture
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                Real Local Inference (Ollama)
              </span>
            )}
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-blue-950 text-blue-300 border border-blue-800">
              Original model — no adapter
            </span>
          </div>
          {appMode === 'connected' && !capabilities?.model_inference.available && (
            <span className="text-[11px] text-amber-400 flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" /> Ollama connection unverified
            </span>
          )}
        </div>
      </div>

      {/* Interrupted Batch Banner */}
      {isInterrupted && activeBatch && (
        <div className="p-4 rounded-xl border border-amber-800/80 bg-amber-950/30 text-amber-200 text-xs space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-bold text-amber-300">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              Batch Interrupted by Backend Restart
            </div>
            <button
              onClick={handleRetryBatch}
              disabled={retrying}
              className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold shadow transition flex items-center gap-1.5 disabled:opacity-50"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              {retrying ? 'Starting Retry...' : 'Retry Batch (Creates New Run)'}
            </button>
          </div>
          <p className="text-slate-300 leading-relaxed">
            {activeBatch.error_message || 'The backend restarted while this batch was executing.'}
            {' '}All <span className="font-mono font-bold text-white">{activeBatch.processed_rows}</span> rows completed before interruption were safely saved. You can inspect partial predictions below, export them to CSV, or launch an explicit retry batch without losing historical data.
          </p>
        </div>
      )}

      {/* Dataset Selection & Execution Card */}
      <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          {/* Dataset Selector */}
          <div className="space-y-1.5 flex-1">
            <label className="text-xs font-semibold text-slate-300 flex items-center gap-2">
              <FileSpreadsheet className="w-4 h-4 text-purple-400" />
              Evaluation Dataset:
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <select
                aria-label="Select Evaluation Dataset"
                value={selectedDatasetId}
                onChange={(e) => handleSelectDataset(e.target.value)}
                disabled={isRunning}
                className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs font-medium text-white focus:outline-none focus:border-blue-500 cursor-pointer min-w-[280px]"
              >
                <option value="sample_cafe_labeled">
                  ★ Fictional Sample Café Dataset (12 rows, labeled)
                </option>
                <option value="sample_dev_60">
                  ★ Fictional Dev Benchmark Dataset (61 rows, labeled)
                </option>
                {availableDatasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename} ({d.row_count} rows · {d.origin})
                  </option>
                ))}
              </select>

              <button
                type="button"
                onClick={() => setShowPreview(!showPreview)}
                className="px-2.5 py-1.5 rounded text-xs font-mono text-slate-400 hover:text-white border border-slate-800 hover:border-slate-700 transition flex items-center gap-1"
              >
                {showPreview ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                {showPreview ? 'Hide Dataset Preview' : 'Preview Data & Mappings'}
              </button>
            </div>
            <div className="text-[11px] text-slate-400 flex flex-wrap gap-x-4 gap-y-1 pt-1 font-mono">
              <span>Response Col: <strong className="text-slate-200">{project.response_col || 'feedback_text'}</strong></span>
              {project.id_col && <span>ID Col: <strong className="text-slate-200">{project.id_col}</strong></span>}
              <span>Topic Labels: <strong className="text-slate-200">{project.label_topics_col || '(unmapped)'}</strong></span>
              <span>Sentiment Labels: <strong className="text-slate-200">{project.label_sentiment_col || '(unmapped)'}</strong></span>
              <span>Review Flag: <strong className="text-slate-200">{project.label_needs_review_col || '(unmapped)'}</strong></span>
            </div>
          </div>

          {/* Concurrency & Controls */}
          <div className="flex items-center gap-3 self-start lg:self-center">
            {/* Concurrency Selector */}
            <div className="flex items-center gap-1.5 bg-slate-950 px-2.5 py-2 rounded-lg border border-slate-800 text-xs text-slate-300">
              <span className="text-[11px] text-slate-400">Concurrency:</span>
              <select
                aria-label="Inference Concurrency"
                value={concurrency}
                onChange={(e) => setConcurrency(Number(e.target.value))}
                disabled={isRunning}
                className="bg-transparent text-xs font-semibold text-blue-400 focus:outline-none cursor-pointer"
                title="Bounded concurrency to avoid memory and thermal throttling on 8GB M2 Mac"
              >
                <option value={1} className="bg-slate-900 text-white">1 (Safe for 8GB Mac)</option>
                <option value={2} className="bg-slate-900 text-white">2 (Parallel)</option>
              </select>
            </div>

            {/* Run / Cancel / Retry Buttons */}
            {isRunning ? (
              <button
                onClick={handleCancelBatch}
                disabled={canceling}
                className="px-4 py-2 rounded-lg bg-rose-600/80 hover:bg-rose-600 text-white text-xs font-semibold shadow-md shadow-rose-600/30 transition flex items-center gap-1.5 disabled:opacity-50"
              >
                <Square className="w-3.5 h-3.5" />
                {canceling ? 'Canceling...' : 'Cancel Batch'}
              </button>
            ) : (
              <button
                onClick={handleStartBaseline}
                disabled={starting}
                className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition flex items-center gap-2 disabled:opacity-50"
              >
                <Play className="w-4 h-4 fill-white" />
                {starting ? 'Initializing...' : 'Run Real Baseline Batch'}
              </button>
            )}

            {/* Export CSV button (enabled whenever partial or full predictions exist) */}
            {activeBatch && activeBatch.processed_rows > 0 && (
              <button
                onClick={handleExport}
                className="px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/30 transition flex items-center gap-1.5"
                title="Export predictions and original columns preserved without overwriting source headers"
              >
                <Download className="w-3.5 h-3.5" />
                Export CSV ({activeBatch.processed_rows} rows)
              </button>
            )}
          </div>
        </div>

        {/* Collapsible Preview Table */}
        {showPreview && (
          <div className="border border-slate-800 rounded-lg p-3 bg-slate-950/80 space-y-2 text-xs">
            <div className="flex items-center justify-between text-slate-400 text-[11px] font-mono">
              <span>Dataset Preview: {currentDatasetName}</span>
              <span>Total Rows: {datasetPreview?.row_count ?? '...'}</span>
            </div>
            {loadingPreview ? (
              <div className="py-4 text-center text-slate-500">Loading dataset sample...</div>
            ) : datasetPreview ? (
              <div className="overflow-x-auto max-h-48 overflow-y-auto">
                <table className="w-full text-left text-[11px] font-mono">
                  <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 sticky top-0">
                    <tr>
                      {datasetPreview.columns.map((col) => (
                        <th key={col} className="px-2.5 py-1.5">
                          {col}
                          {col === project.response_col && (
                            <span className="ml-1 text-[9px] px-1 rounded bg-blue-900 text-blue-300">response</span>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300">
                    {datasetPreview.preview_rows.map((r, idx) => (
                      <tr key={idx} className="hover:bg-slate-900/50">
                        {datasetPreview.columns.map((col) => (
                          <td key={col} className="px-2.5 py-1 max-w-[240px] truncate" title={String(r[col] || '')}>
                            {String(r[col] ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-2 text-slate-500">Could not load preview for this dataset.</div>
            )}
          </div>
        )}

        {/* Live Progress Bar (when running or recent) */}
        {activeBatch && (
          <div className="pt-2 border-t border-slate-800 space-y-2 font-mono text-xs">
            <div className="flex items-center justify-between text-slate-300">
              <span className="flex items-center gap-2">
                {isRunning && <RefreshCw className="w-3.5 h-3.5 text-blue-400 animate-spin" />}
                Status: <span className="uppercase font-bold text-white">{activeBatch.status}</span>
                <span className="text-slate-500">· Batch ID: {activeBatch.id}</span>
                {activeBatch.retried_from_batch_id && (
                  <span className="text-slate-400 text-[10px]">(retried from {activeBatch.retried_from_batch_id})</span>
                )}
              </span>
              <span>
                Processed {activeBatch.processed_rows} / {activeBatch.total_rows} rows
                {activeBatch.error_count > 0 && (
                  <span className="text-rose-400 ml-2">({activeBatch.error_count} errors)</span>
                )}
                {activeBatch.blank_count > 0 && (
                  <span className="text-amber-400 ml-2">({activeBatch.blank_count} blank skipped)</span>
                )}
              </span>
            </div>

            {/* Visual Bar */}
            <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  activeBatch.status === 'completed'
                    ? 'bg-emerald-500'
                    : activeBatch.status === 'canceled'
                    ? 'bg-amber-500'
                    : activeBatch.status === 'interrupted'
                    ? 'bg-amber-500'
                    : activeBatch.status === 'failed'
                    ? 'bg-rose-500'
                    : 'bg-blue-500 animate-pulse'
                }`}
                style={{
                  width: `${
                    activeBatch.total_rows > 0
                      ? Math.min(100, Math.round((activeBatch.processed_rows / activeBatch.total_rows) * 100))
                      : 0
                  }%`,
                }}
              />
            </div>

            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>Elapsed: {activeBatch.elapsed_seconds}s</span>
              <span>Throughput: {activeBatch.throughput_items_per_sec} items/sec</span>
            </div>
          </div>
        )}
      </div>

      {/* Metrics Scorecards (Evaluated against human labels) */}
      {metrics && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-white">Baseline Evaluation Metrics</h2>
              <p className="text-xs text-slate-400">
                Calculated strictly where valid human labels exist. Failed requests count against the score.
              </p>
            </div>
            {metrics.is_unlabeled && (
              <span className="px-2.5 py-1 rounded bg-amber-950/80 text-amber-300 border border-amber-800 text-xs">
                Unlabeled Batch
              </span>
            )}
          </div>

          {metrics.is_unlabeled ? (
            <div className="p-4 rounded-xl border border-amber-800/60 bg-amber-950/20 text-amber-200 text-xs space-y-1">
              <div className="font-semibold flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-amber-400" />
                No Ground Truth Labels Found
              </div>
              <p className="text-slate-300 leading-relaxed">
                The batch was processed and structured outputs were generated. Ground-truth accuracy and F1 scores are not calculated because no human label columns were selected or valid.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* 1. Topic Micro-F1 */}
              <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Topic Micro-F1</span>
                  <span className="text-[11px] font-mono">{metrics.topic_labeled_rows} labeled</span>
                </div>
                <div className="text-3xl font-extrabold font-mono text-white">
                  {metrics.topic_micro_f1 !== null ? `${metrics.topic_micro_f1}%` : 'N/A'}
                </div>
                <div className="text-[11px] text-slate-400 font-mono flex justify-between border-t border-slate-800 pt-1.5">
                  <span>Prec: {metrics.topic_precision}%</span>
                  <span>Rec: {metrics.topic_recall}%</span>
                </div>
                <div className="text-[10px] text-slate-500 font-mono">
                  TP={metrics.topic_tp} | FP={metrics.topic_fp} | FN={metrics.topic_fn}
                </div>
              </div>

              {/* 2. Sentiment Accuracy */}
              <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Sentiment Accuracy</span>
                  <span className="text-[11px] font-mono">{metrics.sentiment_labeled_rows} labeled</span>
                </div>
                <div className="text-3xl font-extrabold font-mono text-white">
                  {metrics.sentiment_accuracy !== null ? `${metrics.sentiment_accuracy}%` : 'N/A'}
                </div>
                <div className="text-[11px] text-slate-400 font-mono border-t border-slate-800 pt-1.5">
                  {metrics.sentiment_correct} of {metrics.sentiment_labeled_rows} correct
                </div>
                <div className="text-[10px] text-slate-500 font-mono">
                  Coverage: {metrics.sentiment_coverage_pct}% of attempted
                </div>
              </div>

              {/* 3. Review Flag Accuracy */}
              <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Review Flag Accuracy</span>
                  <span className="text-[11px] font-mono">{metrics.review_flag_labeled_rows} labeled</span>
                </div>
                <div className="text-3xl font-extrabold font-mono text-white">
                  {metrics.review_flag_accuracy !== null ? `${metrics.review_flag_accuracy}%` : 'N/A'}
                </div>
                <div className="text-[11px] text-slate-400 font-mono border-t border-slate-800 pt-1.5">
                  {metrics.review_flag_correct} of {metrics.review_flag_labeled_rows} correct
                </div>
                <div className="text-[10px] text-slate-500 font-mono">
                  Coverage: {metrics.review_flag_coverage_pct}% of attempted
                </div>
              </div>

              {/* 4. Output Schema Validity */}
              <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Schema Validity</span>
                  <span className="text-[11px] font-mono">{metrics.attempted_rows} attempted</span>
                </div>
                <div className="text-3xl font-extrabold font-mono text-white">
                  {metrics.schema_validity_pct}%
                </div>
                <div className="text-[11px] text-slate-400 font-mono border-t border-slate-800 pt-1.5">
                  {metrics.schema_valid_count} compliant JSON records
                </div>
                <div className="text-[10px] text-slate-500 font-mono">
                  Taxonomy & type conformance
                </div>
              </div>
            </div>
          )}

          {/* Scientific Honesty Disclaimer */}
          <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800/80 text-[11px] text-slate-400 leading-relaxed">
            <span className="font-semibold text-slate-300">Methodological Note: </span>
            {metrics.scientific_disclaimer}
          </div>
        </div>
      )}

      {/* Filterable Predictions vs Ground Truth Table */}
      {activeBatch && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white">Per-Response Prediction vs Label</h2>
              <span className="text-xs text-slate-400 font-mono">({predictions.length} rows)</span>
            </div>

            {/* Filter Buttons */}
            <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
              <button
                onClick={() => setFilterMode('all')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition ${
                  filterMode === 'all' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                All Rows
              </button>
              <button
                onClick={() => setFilterMode('mistakes')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition ${
                  filterMode === 'mistakes' ? 'bg-amber-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                Mistakes Only
              </button>
              <button
                onClick={() => setFilterMode('errors')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition ${
                  filterMode === 'errors' ? 'bg-rose-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                Errors Only
              </button>
              <button
                onClick={() => setFilterMode('flagged')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition ${
                  filterMode === 'flagged' ? 'bg-purple-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                Needs Review
              </button>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto border border-slate-800 rounded-xl bg-slate-950/60 shadow-xl">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/90 text-slate-400 uppercase font-mono text-[11px] border-b border-slate-800">
                <tr>
                  <th className="px-3 py-2.5">ID</th>
                  <th className="px-3 py-2.5 max-w-[280px]">Response Text</th>
                  <th className="px-3 py-2.5">Predicted vs Label Topics</th>
                  <th className="px-3 py-2.5">Sentiment</th>
                  <th className="px-3 py-2.5">Review?</th>
                  <th className="px-3 py-2.5">Status & Validation</th>
                  <th className="px-3 py-2.5 text-right">Latency</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300 font-mono text-[11px]">
                {loadingPreds ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                      Loading prediction records...
                    </td>
                  </tr>
                ) : predictions.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                      No records match the selected filter.
                    </td>
                  </tr>
                ) : (
                  predictions.map((p) => {
                    const isBlank = p.status === 'blank_skipped';
                    const isError = p.status === 'error';
                    const hasGT = p.ground_truth_topics !== null;
                    const topicsMatch =
                      hasGT &&
                      Array.isArray(p.predicted_topics) &&
                      Array.isArray(p.ground_truth_topics) &&
                      p.predicted_topics.slice().sort().join(',') === p.ground_truth_topics.slice().sort().join(',');

                    const sentMatch =
                      p.ground_truth_sentiment !== null &&
                      p.predicted_sentiment.toLowerCase() === p.ground_truth_sentiment.toLowerCase();

                    const rfMatch =
                      p.ground_truth_needs_review !== null &&
                      p.predicted_needs_review === p.ground_truth_needs_review;

                    const labelErrors = p.ground_truth_label_errors || [];

                    return (
                      <tr key={p.id} className="hover:bg-slate-900/40">
                        <td className="px-3 py-2 text-slate-400 font-semibold">{p.response_id || p.row_index + 1}</td>
                        <td className="px-3 py-2 max-w-[280px] truncate font-sans" title={p.response_text}>
                          {isBlank ? (
                            <span className="text-amber-400 italic">[Blank response row]</span>
                          ) : (
                            p.response_text
                          )}
                        </td>

                        {/* Topics */}
                        <td className="px-3 py-2">
                          {isBlank ? (
                            <span className="text-slate-600">-</span>
                          ) : isError ? (
                            <span className="text-rose-400">Failed</span>
                          ) : (
                            <div className="space-y-0.5">
                              <div className="flex flex-wrap gap-1">
                                {p.predicted_topics.map((t) => (
                                  <span key={t} className="px-1.5 py-0.2 rounded text-[10px] bg-blue-950 text-blue-300 border border-blue-800">
                                    {t}
                                  </span>
                                ))}
                                {p.predicted_topics.length === 0 && (
                                  <span className="text-slate-500 text-[10px]">[]</span>
                                )}
                              </div>
                              {hasGT && p.ground_truth_topics && (
                                <div className="text-[10px] text-slate-400">
                                  GT: {p.ground_truth_topics.join(', ') || '[]'}
                                  {topicsMatch ? (
                                    <span className="text-emerald-400 ml-1">✓</span>
                                  ) : (
                                    <span className="text-amber-400 ml-1">≠</span>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </td>

                        {/* Sentiment */}
                        <td className="px-3 py-2">
                          {isBlank ? (
                            <span className="text-slate-600">-</span>
                          ) : isError ? (
                            <span className="text-rose-400">-</span>
                          ) : (
                            <div>
                              <span className="uppercase text-[10px] font-bold text-white">
                                {p.predicted_sentiment || '-'}
                              </span>
                              {p.ground_truth_sentiment && (
                                <div className="text-[10px] text-slate-400">
                                  GT: {p.ground_truth_sentiment}
                                  {sentMatch ? (
                                    <span className="text-emerald-400 ml-1">✓</span>
                                  ) : (
                                    <span className="text-amber-400 ml-1">≠</span>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </td>

                        {/* Review Flag */}
                        <td className="px-3 py-2">
                          {isBlank ? (
                            <span className="text-slate-600">-</span>
                          ) : p.predicted_needs_review ? (
                            <span className="px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 text-[10px] font-bold">
                              FLAG
                            </span>
                          ) : (
                            <span className="text-slate-500 text-[10px]">OK</span>
                          )}
                          {p.ground_truth_needs_review !== null && (
                            <div className="text-[10px] text-slate-400">
                              GT: {p.ground_truth_needs_review ? 'FLAG' : 'OK'}
                              {rfMatch ? (
                                <span className="text-emerald-400 ml-1">✓</span>
                              ) : (
                                <span className="text-amber-400 ml-1">≠</span>
                              )}
                            </div>
                          )}
                        </td>

                        {/* Status & Validation */}
                        <td className="px-3 py-2">
                          <div className="flex flex-col gap-1 items-start">
                            {/* Status and Provenance */}
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {p.status === 'success' ? (
                                <span className="text-emerald-400 text-[10px] flex items-center gap-1">
                                  <CheckCircle2 className="w-3 h-3" /> OK
                                </span>
                              ) : p.status === 'blank_skipped' ? (
                                <span className="text-amber-400 text-[10px]">BLANK</span>
                              ) : (
                                <span className="text-rose-400 text-[10px] flex items-center gap-1" title={p.error_message || ''}>
                                  <XCircle className="w-3 h-3" /> ERROR
                                </span>
                              )}

                              {p.is_simulated ? (
                                <span className="px-1 py-0.2 rounded bg-amber-950/80 text-amber-300 border border-amber-800 text-[9px] font-medium" title="Simulated heuristic fixture">
                                  SIMULATED
                                </span>
                              ) : (
                                <span className="px-1 py-0.2 rounded bg-blue-950/80 text-blue-300 border border-blue-800 text-[9px] font-medium" title={`Real local inference: ${p.model_name || batchModelLabel}`}>
                                  REAL
                                </span>
                              )}
                            </div>

                            {/* Schema validity warning badge */}
                            {!p.is_valid_schema && p.status === 'success' && (
                              <span
                                className="px-1 py-0.2 rounded bg-amber-950 text-amber-300 border border-amber-800 text-[9px] cursor-help"
                                title={`Schema validation issue: ${p.schema_errors?.join('; ') || 'Invalid JSON'}`}
                              >
                                Invalid Schema
                              </span>
                            )}

                            {/* Row-level Ground Truth label errors */}
                            {labelErrors.length > 0 && (
                              <span
                                className="px-1 py-0.2 rounded bg-purple-950 text-purple-300 border border-purple-800 text-[9px] cursor-help"
                                title={`Label parsing errors: ${labelErrors.join('; ')}`}
                              >
                                Label Error
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Latency */}
                        <td className="px-3 py-2 text-right text-slate-400">
                          {p.latency_seconds > 0 ? `${p.latency_seconds}s` : '-'}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
