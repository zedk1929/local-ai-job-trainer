import React, { useState } from 'react';
import { Project, SingleInferenceResult } from '../types';
import { api } from '../api/client';
import { SAMPLE_CAFE_CSV } from '../fixtures/sampleCafeData';
import { Play, Download, CheckCircle2, AlertTriangle, Layers, FileSpreadsheet, Bot, RefreshCw } from 'lucide-react';

interface InferenceScreenProps {
  project: Project | null;
  onNavigate: (screen: string) => void;
}

export const InferenceScreen: React.FC<InferenceScreenProps> = ({ project, onNavigate }) => {
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

  const [activeTab, setActiveTab] = useState<'single' | 'batch'>('single');

  // Single response playground state
  const [inputText, setInputText] = useState(
    'The matcha latte had clumps of dry powder, and when I told the cashier they rolled their eyes.'
  );
  const [useAdapter, setUseAdapter] = useState(true);
  const [inferringSingle, setInferringSingle] = useState(false);
  const [singleResult, setSingleResult] = useState<SingleInferenceResult | null>(null);

  // Batch inference state
  const [batchRows, setBatchRows] = useState<any[]>([]);
  const [batchColumns, setBatchColumns] = useState<string[]>([]);
  const [responseCol, setResponseCol] = useState('feedback_text');
  const [idCol, setIdCol] = useState('id');
  const [inferringBatch, setInferringBatch] = useState(false);
  const [processedBatch, setProcessedBatch] = useState<any[]>([]);
  const [filterFlaggedOnly, setFilterFlaggedOnly] = useState(false);

  // Run single test
  const handleSingleInfer = async () => {
    if (!inputText.trim()) return;
    setInferringSingle(true);
    try {
      const res = await api.inferSingle(project.id, inputText, useAdapter);
      setSingleResult(res.result);
    } catch (err: any) {
      alert(err.message || 'Inference failed');
    } finally {
      setInferringSingle(false);
    }
  };

  // Load sample dataset for batch
  const handleLoadSampleBatch = () => {
    // Parse sample CSV into rows
    const lines = SAMPLE_CAFE_CSV.trim().split('\n');
    const headers = lines[0].split(',');
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      const line = lines[i];
      if (!line) continue;
      // Simple regex for CSV parsing preserving quotes
      const match = line.match(/(".*?"|[^",\s]+)(?=\s*,|\s*$)/g);
      const parts = line.split(',');
      rows.push({
        id: parts[0],
        customer_name: parts[1],
        feedback_text: line.includes('"') ? line.split('"')[1] : parts[2],
        visit_date: parts[parts.length - 1],
      });
    }
    setBatchRows(rows);
    setBatchColumns(['id', 'customer_name', 'feedback_text', 'visit_date']);
    setResponseCol('feedback_text');
    setIdCol('id');
  };

  // Run batch inference
  const handleRunBatch = async () => {
    if (batchRows.length === 0) return;
    setInferringBatch(true);
    try {
      const res = await api.inferBatch(project.id, batchRows, responseCol, useAdapter);
      setProcessedBatch(res.processed_rows || []);
    } catch (err: any) {
      alert(err.message || 'Batch inference failed');
    } finally {
      setInferringBatch(false);
    }
  };

  // Export CSV
  const handleExportCsv = async () => {
    if (processedBatch.length === 0) return;
    await api.exportCsv(project.id, processedBatch, batchColumns);
  };

  const displayedBatch = filterFlaggedOnly
    ? processedBatch.filter((r) => r.needs_review === 'YES')
    : processedBatch;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      {/* Header and Active Model Status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800">
              Specialist Deployment
            </span>
            <span className="text-xs text-slate-400">· Project: {project.name}</span>
          </div>
          <h1 className="text-2xl font-bold text-white mt-1">Use the Specialist</h1>
        </div>

        <div className="flex items-center gap-3">
          <div className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 text-xs flex items-center gap-2">
            <Bot className="w-4 h-4 text-blue-400" />
            <span className="text-slate-400">Active Specialist:</span>
            <span className="font-semibold text-white">
              {project.active_adapter_id ? project.active_adapter_id : 'Base Model (Unspecialized)'}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex space-x-2 border-b border-slate-800">
        <button
          onClick={() => setActiveTab('single')}
          className={`px-4 py-2 text-xs font-semibold rounded-t-lg transition border-b-2 ${
            activeTab === 'single'
              ? 'border-blue-500 text-blue-400 bg-slate-900/40'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Single Response Playground
        </button>
        <button
          onClick={() => setActiveTab('batch')}
          className={`px-4 py-2 text-xs font-semibold rounded-t-lg transition border-b-2 ${
            activeTab === 'batch'
              ? 'border-blue-500 text-blue-400 bg-slate-900/40'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Batch CSV Processing & Export
        </button>
      </div>

      {/* Tab 1: Single Response Playground */}
      {activeTab === 'single' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Input Box */}
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
            <div className="flex items-center justify-between">
              <label className="block text-xs font-bold text-white">Enter Survey Response</label>
              <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={useAdapter}
                  onChange={(e) => setUseAdapter(e.target.checked)}
                  className="rounded bg-slate-800 border-slate-700 text-blue-500 focus:ring-0"
                />
                Use Trained LoRA Adapter
              </label>
            </div>

            <textarea
              rows={5}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500 font-mono leading-relaxed"
              placeholder="Paste or type an uncleaned survey comment..."
            />

            <div className="flex flex-wrap gap-2 pt-1 text-[11px] text-slate-400">
              <span className="self-center">Try presets:</span>
              <button
                onClick={() => setInputText('Latte was great but $8 is too much for campus.')}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
              >
                Multi-topic
              </button>
              <button
                onClick={() => setInputText('Found broken glass in my cup and staff ignored me!')}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-rose-300"
              >
                Safety Flag
              </button>
              <button
                onClick={() => setInputText('Quiet and fast wifi. Love doing homework here.')}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-emerald-300"
              >
                Seating / Positive
              </button>
            </div>

            <button
              onClick={handleSingleInfer}
              disabled={inferringSingle}
              className="w-full py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/30 transition flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {inferringSingle ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Running Inference...
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-white" />
                  Run Specialist Inference
                </>
              )}
            </button>
          </div>

          {/* Structured Output Card */}
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider text-slate-400">
              Structured Output Schema
            </h3>

            {singleResult ? (
              <div className="space-y-4 font-mono text-xs">
                {/* Visual badges */}
                <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <span className="text-slate-400 font-sans">Sentiment:</span>
                    <span className="font-bold uppercase text-white bg-slate-800 px-2 py-0.5 rounded">
                      {singleResult.sentiment}
                    </span>
                  </div>

                  <div className="space-y-1">
                    <span className="text-slate-400 font-sans">Assigned Topics:</span>
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {singleResult.topics.length === 0 ? (
                        <span className="text-slate-500 italic">None</span>
                      ) : (
                        singleResult.topics.map((t) => (
                          <span key={t} className="px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800">
                            {t}
                          </span>
                        ))
                      )}
                    </div>
                  </div>

                  <div className="space-y-1 pt-1">
                    <span className="text-slate-400 font-sans">Summary:</span>
                    <p className="text-slate-200 font-sans text-xs italic bg-slate-900/60 p-2 rounded">
                      "{singleResult.summary}"
                    </p>
                  </div>

                  {singleResult.needs_review && (
                    <div className="p-2.5 rounded bg-rose-950/40 border border-rose-800 text-rose-300 text-[11px] font-sans">
                      <div className="font-bold flex items-center gap-1">
                        <AlertTriangle className="w-3.5 h-3.5" /> Flagged for Supervisor Review
                      </div>
                      <p className="mt-1">{singleResult.review_reason}</p>
                    </div>
                  )}

                  <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-[10px] text-slate-500">
                    <span>Model: {singleResult.model_used}</span>
                    <span>Adapter: {singleResult.adapter_used || 'None (baseline)'}</span>
                  </div>
                </div>

                {/* Raw JSON */}
                <div className="space-y-1">
                  <span className="text-[11px] font-semibold text-slate-400 font-sans">Raw JSON Contract:</span>
                  <pre className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-[11px] text-emerald-400 overflow-x-auto">
                    {JSON.stringify(singleResult, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="p-8 rounded-lg border border-dashed border-slate-800 text-center space-y-1 text-slate-500 text-xs">
                <p>Run inference on the left to see structured record outputs.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 2: Batch CSV Processing & Export */}
      {activeTab === 'batch' && (
        <div className="space-y-6">
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <FileSpreadsheet className="w-4 h-4 text-purple-400" />
                  Batch Survey Processing
                </h3>
                <p className="text-xs text-slate-400">
                  Run specialist inference across full CSV callsets with original fields preserved.
                </p>
              </div>

              <div className="flex items-center gap-2">
                {batchRows.length === 0 && (
                  <button
                    onClick={handleLoadSampleBatch}
                    className="px-3 py-1.5 rounded-lg bg-blue-950 text-blue-300 border border-blue-800 hover:bg-blue-900 text-xs font-semibold"
                  >
                    Load Sample Batch (8 rows)
                  </button>
                )}
                {batchRows.length > 0 && (
                  <button
                    onClick={handleRunBatch}
                    disabled={inferringBatch}
                    className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/30 transition flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {inferringBatch ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <Play className="w-3.5 h-3.5 fill-white" />
                        Run Batch ({batchRows.length} rows)
                      </>
                    )}
                  </button>
                )}
                {processedBatch.length > 0 && (
                  <button
                    onClick={handleExportCsv}
                    className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/30 transition flex items-center gap-1.5"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Export Cleaned CSV
                  </button>
                )}
              </div>
            </div>

            {/* Batch Table */}
            {processedBatch.length > 0 ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs pt-2">
                  <span className="font-semibold text-slate-300">
                    Processed Records ({processedBatch.length} total)
                  </span>
                  <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={filterFlaggedOnly}
                      onChange={(e) => setFilterFlaggedOnly(e.target.checked)}
                      className="rounded bg-slate-800 border-slate-700 text-rose-500 focus:ring-0"
                    />
                    Show Flagged Only ({processedBatch.filter((r) => r.needs_review === 'YES').length})
                  </label>
                </div>

                <div className="overflow-x-auto border border-slate-800 rounded-lg">
                  <table className="w-full text-[11px] text-left">
                    <thead className="bg-slate-950 text-slate-400 uppercase font-mono">
                      <tr>
                        <th className="px-3 py-2 border-b border-slate-800">ID</th>
                        <th className="px-3 py-2 border-b border-slate-800">Original Response</th>
                        <th className="px-3 py-2 border-b border-slate-800">Topics</th>
                        <th className="px-3 py-2 border-b border-slate-800">Sentiment</th>
                        <th className="px-3 py-2 border-b border-slate-800">Review?</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                      {displayedBatch.map((row, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/40">
                          <td className="px-3 py-2 text-slate-400">{row.id}</td>
                          <td className="px-3 py-2 font-sans max-w-[260px] truncate" title={row.feedback_text}>
                            {row.feedback_text}
                          </td>
                          <td className="px-3 py-2 text-blue-400">{row.predicted_topics || 'None'}</td>
                          <td className="px-3 py-2 uppercase text-[10px]">{row.predicted_sentiment}</td>
                          <td className="px-3 py-2">
                            {row.needs_review === 'YES' ? (
                              <span className="px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 text-[10px]">
                                FLAG ({row.review_reason})
                              </span>
                            ) : (
                              <span className="text-slate-500 text-[10px]">OK</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : batchRows.length > 0 ? (
              <div className="p-8 rounded-lg border border-slate-800 text-center space-y-2 text-slate-400 text-xs">
                <p>{batchRows.length} rows loaded from dataset.</p>
                <p className="text-[11px] text-slate-500">Click "Run Batch" to process all rows with the specialist.</p>
              </div>
            ) : (
              <div className="p-8 rounded-lg border border-dashed border-slate-800 text-center space-y-2 text-slate-400 text-xs">
                <p>No dataset loaded. Click "Load Sample Batch" or upload a CSV in step 3.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
