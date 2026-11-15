import React, { useState, useEffect } from 'react';
import { Project, TaxonomyItem, DatasetValidationSummary, InspectedCsvResponse } from '../types';
import { api } from '../api/client';
import { SAMPLE_CAFE_CSV } from '../fixtures/sampleCafeData';
import {
  Plus,
  Trash2,
  Upload,
  FileText,
  Check,
  Sparkles,
  Layers,
  ListFilter,
  AlertCircle,
  HelpCircle,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  X,
  FileCheck
} from 'lucide-react';

interface ConfigScreenProps {
  project: Project | null;
  onUpdateProject: (updated: Project) => void;
  onNavigate: (screen: string) => void;
}

export const ConfigScreen: React.FC<ConfigScreenProps> = ({
  project,
  onUpdateProject,
  onNavigate,
}) => {
  if (!project) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center space-y-4">
        <h2 className="text-xl font-bold text-white">No Project Selected</h2>
        <p className="text-sm text-slate-400">Please choose or create a project on the Jobs / Home screen first.</p>
        <button
          onClick={() => onNavigate('jobs')}
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold"
        >
          Go to Jobs
        </button>
      </div>
    );
  }

  // Local state for editing
  const [context, setContext] = useState(project.survey_context);
  const [taxonomy, setTaxonomy] = useState<TaxonomyItem[]>(project.taxonomy);
  const [rules, setRules] = useState<string[]>(project.coding_rules);

  // New category inputs
  const [newCatId, setNewCatId] = useState('');
  const [newCatName, setNewCatName] = useState('');
  const [newCatDesc, setNewCatDesc] = useState('');

  // New rule input
  const [newRule, setNewRule] = useState('');

  // CSV upload & two-stage inspection/confirmation state
  const [pendingInspection, setPendingInspection] = useState<InspectedCsvResponse | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [confirmSuccess, setConfirmSuccess] = useState(false);

  // Confirmed dataset state
  const [confirmedDataset, setConfirmedDataset] = useState<any | null>(null);
  const [csvPreview, setCsvPreview] = useState<any[] | null>(null);
  const [csvColumns, setCsvColumns] = useState<string[]>([]);
  const [responseCol, setResponseCol] = useState(project.response_col || '');
  const [idCol, setIdCol] = useState(project.id_col || '');
  const [labelTopicsCol, setLabelTopicsCol] = useState(project.label_topics_col || '');
  const [labelSentimentCol, setLabelSentimentCol] = useState(project.label_sentiment_col || '');
  const [labelNeedsReviewCol, setLabelNeedsReviewCol] = useState(project.label_needs_review_col || '');
  const [rowCount, setRowCount] = useState<number>(0);
  const [validationSummary, setValidationSummary] = useState<DatasetValidationSummary | null>(null);

  // Reset all editing state whenever project changes to maintain strict project isolation
  useEffect(() => {
    setContext(project.survey_context || '');
    setTaxonomy(project.taxonomy || []);
    setRules(project.coding_rules || []);
    setNewCatId('');
    setNewCatName('');
    setNewCatDesc('');
    setNewRule('');
    setPendingInspection(null);
    setInspecting(false);
    setConfirming(false);
    setUploadError(null);
    setConfirmSuccess(false);
    setConfirmedDataset(null);
    setCsvPreview(null);
    setCsvColumns([]);
    setResponseCol(project.response_col || '');
    setIdCol(project.id_col || '');
    setLabelTopicsCol(project.label_topics_col || '');
    setLabelSentimentCol(project.label_sentiment_col || '');
    setLabelNeedsReviewCol(project.label_needs_review_col || '');
    setRowCount(0);
    setValidationSummary(null);
    setSyntheticExamples([]);
    setGeneratingSynthetic(false);
    setSavingChanges(false);
    setSaveSuccess(false);
  }, [project.id]);

  // Load preview of currently confirmed dataset on mount or project switch with race condition guard
  useEffect(() => {
    let active = true;
    if (project.selected_dataset_id) {
      api.getDatasetPreview(project.id, project.selected_dataset_id)
        .then((preview) => {
          if (!active) return;
          setCsvPreview(preview.preview_rows);
          setCsvColumns(preview.columns);
          setRowCount(preview.row_count);
        })
        .catch((e) => {
          if (!active) return;
          console.warn('Could not load confirmed dataset preview:', e);
          setCsvPreview(null);
          setCsvColumns([]);
          setRowCount(0);
        });
    } else {
      setCsvPreview(null);
      setCsvColumns([]);
      setRowCount(0);
    }
    return () => {
      active = false;
    };
  }, [project.id, project.selected_dataset_id]);

  // Synthetic example state
  const [syntheticExamples, setSyntheticExamples] = useState<any[]>([]);
  const [generatingSynthetic, setGeneratingSynthetic] = useState(false);
  const [savingChanges, setSavingChanges] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Add category
  const handleAddCategory = () => {
    if (!newCatId || !newCatName) return;
    const cleanId = newCatId.trim().toLowerCase().replace(/\s+/g, '_');
    setTaxonomy([...taxonomy, { id: cleanId, name: newCatName, description: newCatDesc }]);
    setNewCatId('');
    setNewCatName('');
    setNewCatDesc('');
  };

  const handleRemoveCategory = (id: string) => {
    setTaxonomy(taxonomy.filter((t) => t.id !== id));
  };

  // Add rule
  const handleAddRule = () => {
    if (!newRule.trim()) return;
    setRules([...rules, newRule.trim()]);
    setNewRule('');
  };

  const handleRemoveRule = (index: number) => {
    setRules(rules.filter((_, idx) => idx !== index));
  };

  // Save project configuration
  const handleSave = async () => {
    const targetProjectId = project.id;
    setSavingChanges(true);
    try {
      const updated = await api.updateProject(targetProjectId, {
        survey_context: context,
        taxonomy,
        coding_rules: rules,
        response_col: responseCol,
        id_col: idCol,
        label_topics_col: labelTopicsCol,
        label_sentiment_col: labelSentimentCol,
        label_needs_review_col: labelNeedsReviewCol,
      });
      onUpdateProject(updated);
      if (project.id === targetProjectId) {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 2500);
      }
    } finally {
      if (project.id === targetProjectId) {
        setSavingChanges(false);
      }
    }
  };

  // Stage 1: Load Sample Café CSV fixture (inspect only)
  const handleLoadSampleCsv = async () => {
    setInspecting(true);
    setUploadError(null);
    setConfirmSuccess(false);
    try {
      const res = await api.inspectCsv(undefined, 'sample');
      setPendingInspection(res);
      setResponseCol(res.suggested_mappings.response_col || res.columns[0] || '');
      setIdCol(res.suggested_mappings.id_col || '');
      setLabelTopicsCol(res.suggested_mappings.label_topics_col || '');
      setLabelSentimentCol(res.suggested_mappings.label_sentiment_col || '');
      setLabelNeedsReviewCol(res.suggested_mappings.label_needs_review_col || '');
    } catch (err: any) {
      setUploadError(err.message || 'Failed to inspect sample CSV');
    } finally {
      setInspecting(false);
    }
  };

  // Stage 1: Load Dev Benchmark CSV (~60 rows) fixture (inspect only)
  const handleLoadDevBenchmarkCsv = async () => {
    setInspecting(true);
    setUploadError(null);
    setConfirmSuccess(false);
    try {
      const res = await api.inspectCsv(undefined, 'dev_60');
      setPendingInspection(res);
      setResponseCol(res.suggested_mappings.response_col || res.columns[0] || '');
      setIdCol(res.suggested_mappings.id_col || '');
      setLabelTopicsCol(res.suggested_mappings.label_topics_col || '');
      setLabelSentimentCol(res.suggested_mappings.label_sentiment_col || '');
      setLabelNeedsReviewCol(res.suggested_mappings.label_needs_review_col || '');
    } catch (err: any) {
      setUploadError(err.message || 'Failed to inspect dev benchmark CSV');
    } finally {
      setInspecting(false);
    }
  };

  // Stage 1: Inspect user CSV file
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setInspecting(true);
    setUploadError(null);
    setConfirmSuccess(false);
    try {
      const res = await api.inspectCsv(file);
      setPendingInspection(res);
      setResponseCol(res.suggested_mappings.response_col || res.columns[0] || '');
      setIdCol(res.suggested_mappings.id_col || '');
      setLabelTopicsCol(res.suggested_mappings.label_topics_col || '');
      setLabelSentimentCol(res.suggested_mappings.label_sentiment_col || '');
      setLabelNeedsReviewCol(res.suggested_mappings.label_needs_review_col || '');
    } catch (err: any) {
      setUploadError(err.message || 'Failed to inspect CSV file');
    } finally {
      setInspecting(false);
      e.target.value = '';
    }
  };

  // Cancel pending inspection without altering saved dataset or project mappings
  const handleCancelPending = () => {
    setPendingInspection(null);
    setUploadError(null);
    setResponseCol(project.response_col || '');
    setIdCol(project.id_col || '');
    setLabelTopicsCol(project.label_topics_col || '');
    setLabelSentimentCol(project.label_sentiment_col || '');
    setLabelNeedsReviewCol(project.label_needs_review_col || '');
  };

  // Stage 2: Confirm dataset and persist to project
  const handleConfirmDataset = async () => {
    if (!pendingInspection) return;
    if (!responseCol) {
      setUploadError('Please select a response text column before confirming.');
      return;
    }

    const targetProjectId = project.id;
    setConfirming(true);
    setUploadError(null);
    try {
      const res = await api.confirmDataset({
        project_id: targetProjectId,
        temp_file_id: pendingInspection.temp_file_id,
        filename: pendingInspection.filename,
        response_col: responseCol,
        id_col: idCol || '',
        label_topics_col: labelTopicsCol || '',
        label_sentiment_col: labelSentimentCol || '',
        label_needs_review_col: labelNeedsReviewCol || '',
        is_sample: pendingInspection.is_sample,
      });

      // Update project parent state
      const updatedProject: Project = {
        ...project,
        id: targetProjectId,
        selected_dataset_id: res.dataset.id,
        response_col: responseCol,
        id_col: idCol || '',
        label_topics_col: labelTopicsCol || '',
        label_sentiment_col: labelSentimentCol || '',
        label_needs_review_col: labelNeedsReviewCol || '',
      };
      onUpdateProject(updatedProject);

      if (project.id === targetProjectId) {
        setConfirmedDataset(res.dataset);
        setCsvPreview(res.preview_rows);
        setCsvColumns(res.columns);
        setRowCount(res.row_count);
        setValidationSummary(res.validation_summary);
        setPendingInspection(null);
        setConfirmSuccess(true);
        setTimeout(() => setConfirmSuccess(false), 4000);
      }
    } catch (err: any) {
      if (project.id === targetProjectId) {
        setUploadError(err.message || 'Failed to confirm dataset');
      }
    } finally {
      if (project.id === targetProjectId) {
        setConfirming(false);
      }
    }
  };

  // Generate synthetic training examples
  const handleGenerateSynthetic = async () => {
    setGeneratingSynthetic(true);
    try {
      const res = await api.generateSynthetic(project.id, 6);
      setSyntheticExamples(res.examples || []);
    } finally {
      setGeneratingSynthetic(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      {/* Header and Save Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800">
              Preset: Survey Cleaner
            </span>
            <span className="text-xs text-slate-400">· Project: {project.name}</span>
          </div>
          <h1 className="text-2xl font-bold text-white mt-1">Configure Task Context & Rules</h1>
        </div>

        <div className="flex items-center gap-3">
          {saveSuccess && (
            <span className="flex items-center gap-1 text-xs text-emerald-400 font-medium">
              <Check className="w-4 h-4" /> Saved!
            </span>
          )}
          <button
            onClick={handleSave}
            disabled={savingChanges}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/30 transition disabled:opacity-50"
          >
            {savingChanges ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left Column: Context & Taxonomy */}
        <div className="space-y-6">
          {/* Survey Context */}
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3">
            <label className="block text-sm font-bold text-white">Survey Context & Purpose</label>
            <p className="text-xs text-slate-400 leading-relaxed">
              Describe who answered the survey and what the study measures. The model uses this to ground category definitions.
            </p>
            <textarea
              rows={3}
              value={context}
              onChange={(e) => setContext(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500"
              placeholder="e.g. A campus café gathering customer feedback on drink taste, pricing, speed, and seating comfort."
            />
          </div>

          {/* Categories / Taxonomy */}
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Layers className="w-4 h-4 text-blue-400" />
                  Category Taxonomy ({taxonomy.length})
                </h3>
                <p className="text-xs text-slate-400">Allowed classification topics for responses</p>
              </div>
            </div>

            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {taxonomy.map((cat) => (
                <div
                  key={cat.id}
                  className="p-3 rounded-lg bg-slate-800/60 border border-slate-700/60 flex items-start justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-white">{cat.name}</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-900 text-blue-400 border border-slate-700">
                        {cat.id}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400">{cat.description}</p>
                  </div>
                  <button
                    onClick={() => handleRemoveCategory(cat.id)}
                    className="text-slate-500 hover:text-rose-400 p-1"
                    title="Remove category"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>

            {/* Add Category Form */}
            <div className="pt-3 border-t border-slate-800/80 space-y-2">
              <span className="text-xs font-semibold text-slate-300">Add New Category</span>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="text"
                  placeholder="ID (e.g. cleanliness)"
                  value={newCatId}
                  onChange={(e) => setNewCatId(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500"
                />
                <input
                  type="text"
                  placeholder="Display Name"
                  value={newCatName}
                  onChange={(e) => setNewCatName(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Category definition & boundary rules..."
                  value={newCatDesc}
                  onChange={(e) => setNewCatDesc(e.target.value)}
                  className="flex-1 px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500"
                />
                <button
                  type="button"
                  onClick={handleAddCategory}
                  className="px-3 py-1.5 rounded-lg bg-blue-600/80 hover:bg-blue-600 text-white text-xs font-semibold flex items-center gap-1"
                >
                  <Plus className="w-3.5 h-3.5" /> Add
                </button>
              </div>
            </div>
          </div>

          {/* Coding Rules */}
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <ListFilter className="w-4 h-4 text-emerald-400" />
                  Coding Rules ({rules.length})
                </h3>
                <p className="text-xs text-slate-400">Explicit classification criteria given to the model</p>
              </div>
            </div>

            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {rules.map((rule, idx) => (
                <div
                  key={idx}
                  className="p-2.5 rounded-lg bg-slate-800/60 border border-slate-700/60 flex items-start justify-between gap-3"
                >
                  <span className="text-xs text-slate-300">• {rule}</span>
                  <button
                    onClick={() => handleRemoveRule(idx)}
                    className="text-slate-500 hover:text-rose-400 p-1"
                    title="Remove rule"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>

            <div className="flex items-center gap-2 pt-2 border-t border-slate-800/80">
              <input
                type="text"
                placeholder="New coding rule (e.g. Flag needs_review=true if customer reports an injury)..."
                value={newRule}
                onChange={(e) => setNewRule(e.target.value)}
                className="flex-1 px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500"
              />
              <button
                type="button"
                onClick={handleAddRule}
                className="px-3 py-1.5 rounded-lg bg-emerald-600/80 hover:bg-emerald-600 text-white text-xs font-semibold flex items-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" /> Add
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Dataset Upload, Human Labels & Validation */}
        <div className="space-y-6">
          {/* CSV Upload & Quick Sample */}
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <FileText className="w-4 h-4 text-purple-400" />
                  Survey Dataset (CSV)
                </h3>
                <p className="text-xs text-slate-400">Two-stage inspect and confirm flow preserving original columns</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleLoadSampleCsv}
                  disabled={inspecting || confirming}
                  className="px-3 py-1.5 rounded-lg bg-blue-950 text-blue-300 border border-blue-800 hover:bg-blue-900 text-xs font-semibold transition disabled:opacity-50"
                >
                  {inspecting && pendingInspection?.temp_file_id === 'sample_cafe_labeled' ? 'Inspecting Sample...' : 'Load Sample (12 rows)'}
                </button>
                <button
                  type="button"
                  onClick={handleLoadDevBenchmarkCsv}
                  disabled={inspecting || confirming}
                  className="px-3 py-1.5 rounded-lg bg-indigo-950 text-indigo-300 border border-indigo-800 hover:bg-indigo-900 text-xs font-semibold transition disabled:opacity-50"
                >
                  {inspecting && pendingInspection?.temp_file_id === 'sample_dev_60' ? 'Inspecting Benchmark...' : 'Load Dev Benchmark (~60 rows)'}
                </button>
              </div>
            </div>

            {/* Error banner */}
            {uploadError && (
              <div className="p-3.5 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-xs flex items-start justify-between gap-2">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
                  <span className="leading-relaxed">{uploadError}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setUploadError(null)}
                  className="text-rose-400 hover:text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Confirm success banner */}
            {confirmSuccess && (
              <div className="p-3.5 rounded-lg bg-emerald-950/60 border border-emerald-800 text-emerald-200 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>Dataset confirmed and saved! Available on the Baseline Evaluation screen.</span>
              </div>
            )}

            {/* File dropzone (Stage 1 Inspect) */}
            <div className="border-2 border-dashed border-slate-700 rounded-xl p-6 text-center space-y-2 hover:border-blue-500 transition cursor-pointer relative bg-slate-950/40">
              <Upload className="w-8 h-8 text-slate-400 mx-auto" />
              <div className="text-xs text-slate-300">
                {inspecting ? (
                  <span className="font-semibold text-blue-400">Inspecting CSV headers and formatting...</span>
                ) : (
                  <>
                    <span className="font-semibold text-blue-400">Click to upload CSV</span> or drag and drop
                  </>
                )}
              </div>
              <p className="text-[11px] text-slate-500">Supports standard UTF-8 CSVs, multiline responses, and UTF-8 BOMs</p>
              <input
                type="file"
                accept=".csv"
                disabled={inspecting || confirming}
                onChange={handleFileUpload}
                className="absolute inset-0 opacity-0 cursor-pointer disabled:cursor-not-allowed"
              />
            </div>

            {/* Stage 1: Pending Inspection & Mapping Selection */}
            {pendingInspection && (
              <div className="p-4 rounded-xl border border-amber-800/80 bg-amber-950/20 space-y-4">
                <div className="flex items-center justify-between border-b border-amber-900/60 pb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-amber-900/80 text-amber-300 border border-amber-700">
                        Stage 1: Inspected
                      </span>
                      <span className="text-xs font-bold text-white">
                        {pendingInspection.filename}
                      </span>
                      {pendingInspection.is_sample && (
                        <span className="text-[10px] text-purple-300 bg-purple-950 px-1.5 py-0.2 rounded border border-purple-800">
                          Built-in Fictional Sample
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-400 mt-1">
                      {pendingInspection.row_count} rows found. Review column mappings below and click Confirm.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleCancelPending}
                    className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition flex items-center gap-1"
                  >
                    <X className="w-3.5 h-3.5" /> Discard
                  </button>
                </div>

                {/* Column Selection Form */}
                <div className="space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-semibold text-slate-200 mb-1">
                        Response Text Column <span className="text-rose-400">*</span>
                      </label>
                      <select
                        aria-label="Response Column"
                        value={responseCol}
                        onChange={(e) => setResponseCol(e.target.value)}
                        className="w-full px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500"
                      >
                        <option value="">-- Select Response Column --</option>
                        {pendingInspection.columns.map((col) => (
                          <option key={col} value={col}>
                            {col}
                          </option>
                        ))}
                      </select>
                      {!responseCol && (
                        <span className="text-[10px] text-rose-400 mt-0.5 block">Response column is required</span>
                      )}
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-slate-200 mb-1">
                        ID Column (Optional)
                      </label>
                      <select
                        aria-label="ID Column"
                        value={idCol}
                        onChange={(e) => setIdCol(e.target.value)}
                        className="w-full px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white text-xs focus:outline-none"
                      >
                        <option value="">(None - Auto-generate index)</option>
                        {pendingInspection.columns.map((col) => (
                          <option key={col} value={col}>
                            {col}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {/* Optional Human Label Columns */}
                  <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-2.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-200">Optional Human-Label Columns (for Evaluation)</span>
                      <span className="text-[10px] text-slate-400">Leave (None) if unlabeled</span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
                      <div>
                        <label className="block text-[10px] text-slate-400 mb-1">Topics Label</label>
                        <select
                          aria-label="Topics Label Column"
                          value={labelTopicsCol}
                          onChange={(e) => setLabelTopicsCol(e.target.value)}
                          className="w-full px-2 py-1 rounded bg-slate-900 border border-slate-700 text-white text-xs"
                        >
                          <option value="">(None)</option>
                          {pendingInspection.columns.map((c) => (
                            <option key={c} value={c}>{c}</option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-[10px] text-slate-400 mb-1">Sentiment Label</label>
                        <select
                          aria-label="Sentiment Label Column"
                          value={labelSentimentCol}
                          onChange={(e) => setLabelSentimentCol(e.target.value)}
                          className="w-full px-2 py-1 rounded bg-slate-900 border border-slate-700 text-white text-xs"
                        >
                          <option value="">(None)</option>
                          {pendingInspection.columns.map((c) => (
                            <option key={c} value={c}>{c}</option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-[10px] text-slate-400 mb-1">Needs Review Label</label>
                        <select
                          aria-label="Needs Review Label Column"
                          value={labelNeedsReviewCol}
                          onChange={(e) => setLabelNeedsReviewCol(e.target.value)}
                          className="w-full px-2 py-1 rounded bg-slate-900 border border-slate-700 text-white text-xs"
                        >
                          <option value="">(None)</option>
                          {pendingInspection.columns.map((c) => (
                            <option key={c} value={c}>{c}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="text-[10px] text-slate-400 space-y-0.5 border-t border-slate-800/80 pt-2 font-mono">
                      <p>• <strong>Topics:</strong> Semicolon-delimited IDs (e.g. <code>drink_quality; price</code>), JSON array, or <code>[]</code> for none.</p>
                      <p>• <strong>Sentiment:</strong> <code>positive</code>, <code>negative</code>, <code>mixed</code>, <code>neutral</code>, <code>unclear</code>.</p>
                      <p>• <strong>Review Flag:</strong> <code>true/false</code>, <code>yes/no</code>, <code>1/0</code>.</p>
                    </div>
                  </div>

                  {/* Stage 1 Inspected Preview Table */}
                  <div className="space-y-1.5 pt-1">
                    <span className="text-[11px] font-semibold text-slate-300">
                      Inspected Preview (First {pendingInspection.preview_rows.length} rows):
                    </span>
                    <div className="overflow-x-auto border border-slate-800 rounded-lg max-h-40 overflow-y-auto">
                      <table className="w-full text-[11px] text-left">
                        <thead className="bg-slate-950 text-slate-400 font-mono sticky top-0 border-b border-slate-800">
                          <tr>
                            {pendingInspection.columns.slice(0, 5).map((col) => (
                              <th key={col} className="px-2.5 py-1.5">
                                {col}
                                {col === responseCol && (
                                  <span className="ml-1 text-[9px] px-1 rounded bg-blue-900 text-blue-300">response</span>
                                )}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                          {pendingInspection.preview_rows.map((row, idx) => (
                            <tr key={idx} className="hover:bg-slate-800/40">
                              {pendingInspection.columns.slice(0, 5).map((col) => (
                                <td key={col} className="px-2.5 py-1 truncate max-w-[160px]">
                                  {String(row[col] ?? '')}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Stage 2 Confirm Action Button */}
                  <div className="pt-2 flex items-center justify-between">
                    <span className="text-xs text-slate-400">
                      Step 2: Confirm to save dataset and update project mappings.
                    </span>
                    <button
                      type="button"
                      onClick={handleConfirmDataset}
                      disabled={confirming || !responseCol}
                      className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/30 transition flex items-center gap-1.5 disabled:opacity-50"
                    >
                      <Check className="w-4 h-4" />
                      {confirming ? 'Confirming & Saving...' : 'Confirm & Save Dataset'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Confirmed Dataset & Validation Summary (When no pending inspection) */}
            {!pendingInspection && project.selected_dataset_id && (
              <div className="space-y-4">
                {/* Confirmed Dataset Card */}
                <div className="p-3.5 rounded-lg bg-emerald-950/20 border border-emerald-800/60 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-emerald-300 flex items-center gap-1.5">
                      <FileCheck className="w-4 h-4 text-emerald-400" />
                      Active Confirmed Dataset: {confirmedDataset?.filename || (project.selected_dataset_id === 'sample_dev_60' ? 'Fictional Dev Benchmark Dataset (Built-in, 61 rows)' : project.selected_dataset_id === 'sample_cafe_labeled' ? 'Fictional Sample Café Feedback (Built-in, 12 rows)' : project.selected_dataset_id)}
                    </span>
                    <button
                      type="button"
                      onClick={() => onNavigate('baseline')}
                      className="px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-semibold transition flex items-center gap-1"
                    >
                      Evaluate <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>

                  <div className="flex flex-wrap gap-2 text-[11px] font-mono text-slate-300 pt-1">
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                      Response: <strong className="text-white">{project.response_col}</strong>
                    </span>
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                      ID: <strong className="text-white">{project.id_col || '(None)'}</strong>
                    </span>
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                      Topics: <strong className="text-white">{project.label_topics_col || '(None)'}</strong>
                    </span>
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                      Sentiment: <strong className="text-white">{project.label_sentiment_col || '(None)'}</strong>
                    </span>
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                      Review: <strong className="text-white">{project.label_needs_review_col || '(None)'}</strong>
                    </span>
                  </div>
                </div>

                {/* Validation Summary Card */}
                {validationSummary && (
                  <div className="p-3.5 rounded-lg bg-slate-950/80 border border-slate-800 text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white flex items-center gap-1.5">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        Dataset Validation ({validationSummary.total_rows} total rows)
                      </span>
                      {validationSummary.is_unlabeled ? (
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px]">
                          Unlabeled Dataset
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px]">
                          Human Labels Validated
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-slate-300">
                      <div>Valid responses: {validationSummary.valid_response_rows}</div>
                      <div>Blank skipped: {validationSummary.blank_response_rows}</div>
                      <div>
                        Topic labeled: {validationSummary.topics_labeled_rows}
                        {validationSummary.topics_valid_empty_rows ? ` (${validationSummary.topics_valid_empty_rows} empty [])` : ''}
                      </div>
                      <div>
                        Topic invalid: {validationSummary.topics_invalid_rows ?? 0} | Missing: {validationSummary.topics_missing_rows ?? 0}
                      </div>
                      <div>Sentiment labeled: {validationSummary.sentiment_labeled_rows}</div>
                      <div>
                        Sentiment invalid: {validationSummary.sentiment_invalid_rows ?? 0} | Missing: {validationSummary.sentiment_missing_rows ?? 0}
                      </div>
                      <div>Review flag labeled: {validationSummary.needs_review_labeled_rows}</div>
                      <div>
                        Review invalid: {validationSummary.needs_review_invalid_rows ?? 0} | Missing: {validationSummary.needs_review_missing_rows ?? 0}
                      </div>
                    </div>

                    {validationSummary.unrecognized_topic_tokens.length > 0 && (
                      <div className="p-2 rounded bg-amber-950/40 border border-amber-800 text-amber-300 text-[10px]">
                        ⚠ Unrecognized topic labels found: {validationSummary.unrecognized_topic_tokens.join(', ')}.
                        These are excluded from topic metrics as invalid labels.
                      </div>
                    )}

                    {/* Row-level errors sample */}
                    {validationSummary.topic_errors && validationSummary.topic_errors.length > 0 && (
                      <div className="space-y-1 border-t border-slate-800 pt-2 text-[10px] font-mono text-rose-300">
                        <span className="font-semibold text-rose-400">Row-level Label Issues:</span>
                        {validationSummary.topic_errors.slice(0, 3).map((err, i) => (
                          <div key={i} className="truncate">
                            Row {err.row_idx} ({err.response_id}): "{err.raw_value}" → {err.error}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Confirmed CSV Preview Table */}
                {csvPreview && (
                  <div className="space-y-2 pt-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-300">Confirmed Dataset Preview ({rowCount} rows total)</span>
                      <span className="text-[11px] text-emerald-400">Showing first {csvPreview.length} rows</span>
                    </div>
                    <div className="overflow-x-auto border border-slate-800 rounded-lg">
                      <table className="w-full text-[11px] text-left">
                        <thead className="bg-slate-950 text-slate-400 uppercase font-mono">
                          <tr>
                            {csvColumns.slice(0, 5).map((col) => (
                              <th key={col} className="px-3 py-2 border-b border-slate-800">
                                {col}
                                {col === project.response_col && (
                                  <span className="ml-1 text-[9px] px-1 rounded bg-blue-900 text-blue-300 normal-case">response</span>
                                )}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                          {csvPreview.map((row, idx) => (
                            <tr key={idx} className="hover:bg-slate-800/40">
                              {csvColumns.slice(0, 5).map((col) => (
                                <td key={col} className="px-3 py-1.5 truncate max-w-[180px]">
                                  {String(row[col] ?? '')}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Synthetic Examples Review */}
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-amber-400" />
                  Supervisor Synthetic Examples
                </h3>
                <p className="text-xs text-slate-400">Review synthetic training pairs before training</p>
              </div>
              <button
                onClick={handleGenerateSynthetic}
                disabled={generatingSynthetic}
                className="px-3 py-1.5 rounded-lg bg-amber-600/80 hover:bg-amber-600 text-white text-xs font-semibold transition disabled:opacity-50"
              >
                {generatingSynthetic ? 'Generating...' : 'Generate 6 Examples'}
              </button>
            </div>

            {syntheticExamples.length === 0 ? (
              <div className="p-6 rounded-lg border border-dashed border-slate-800 text-center space-y-1 text-slate-400 text-xs">
                <p>Click "Generate" to create synthetic examples matching your categories.</p>
                <p className="text-[11px] text-slate-500">In preview mode, deterministic fixtures are returned.</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                {syntheticExamples.map((ex, idx) => (
                  <div
                    key={idx}
                    className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                        Origin: {ex.origin || 'synthetic'}
                      </span>
                      <span className="text-[10px] font-semibold text-blue-400 uppercase">
                        Sentiment: {ex.sentiment}
                      </span>
                    </div>
                    <p className="text-slate-200 italic">"{ex.original_response}"</p>
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {ex.topics.map((t: string) => (
                        <span key={t} className="px-1.5 py-0.5 rounded text-[10px] bg-blue-950 text-blue-300 border border-blue-800">
                          {t}
                        </span>
                      ))}
                      {ex.needs_review && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-rose-950 text-rose-300 border border-rose-800">
                          Needs Review: {ex.review_reason}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Action Footer: Proceed to Baseline Evaluation */}
      <div className="flex items-center justify-between pt-4 border-t border-slate-800">
        <span className="text-xs text-slate-400">Ready to benchmark the unspecialized model?</span>
        <button
          onClick={() => onNavigate('baseline')}
          className="px-6 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition flex items-center gap-2"
        >
          Proceed to Baseline Evaluation &rarr;
        </button>
      </div>
    </div>
  );
};
