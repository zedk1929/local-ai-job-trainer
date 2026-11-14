import React, { useState } from 'react';
import { Project, Run } from '../types';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { CheckCircle2, TrendingUp, AlertTriangle, ShieldCheck, Cpu, ArrowRight, RotateCcw } from 'lucide-react';

interface ResultsScreenProps {
  project: Project | null;
  latestRun: Run | null;
  onUpdateProject: (updated: Project) => void;
  onNavigate: (screen: string) => void;
}

export const ResultsScreen: React.FC<ResultsScreenProps> = ({
  project,
  latestRun,
  onUpdateProject,
  onNavigate,
}) => {
  if (!project || !latestRun || !latestRun.results) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center space-y-4">
        <h2 className="text-xl font-bold text-white">No Completed Run Results</h2>
        <p className="text-sm text-slate-400">
          Run the specialization pipeline on the Build Specialist screen to evaluate baseline vs candidate metrics.
        </p>
        <button
          onClick={() => onNavigate('experiment')}
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold"
        >
          Go to Build Specialist
        </button>
      </div>
    );
  }

  const results = latestRun.results;
  const baseline = results.baseline;
  const candidate = results.candidate;
  const diffs = results.differences;
  const isAdapterActive = project.active_adapter_id === results.adapter_id;

  const [activating, setActivating] = useState(false);

  const handleActivate = async () => {
    setActivating(true);
    try {
      const updated = await api.updateProject(project.id, {
        active_adapter_id: results.adapter_id,
      });
      onUpdateProject(updated);
    } finally {
      setActivating(false);
    }
  };

  const handleDeactivate = async () => {
    setActivating(true);
    try {
      const updated = await api.updateProject(project.id, {
        active_adapter_id: null,
      });
      onUpdateProject(updated);
    } finally {
      setActivating(false);
    }
  };

  const metrics = [
    {
      name: 'Topic Micro-F1',
      baseline: baseline.topic_micro_f1,
      candidate: candidate.topic_micro_f1,
      diff: diffs.topic_micro_f1,
      unit: '%',
    },
    {
      name: 'Sentiment Accuracy',
      baseline: baseline.sentiment_accuracy,
      candidate: candidate.sentiment_accuracy,
      diff: diffs.sentiment_accuracy,
      unit: '%',
    },
    {
      name: 'Schema Validity',
      baseline: baseline.schema_validity,
      candidate: candidate.schema_validity,
      diff: diffs.schema_validity,
      unit: '%',
    },
    {
      name: 'Review Flag Accuracy',
      baseline: baseline.review_flag_accuracy,
      candidate: candidate.review_flag_accuracy,
      diff: diffs.review_flag_accuracy,
      unit: '%',
    },
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      {/* Header and Adapter Activation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800">
              Evaluation & Comparison
            </span>
            <span className="text-xs text-slate-400">· Run ID: {latestRun.id}</span>
          </div>
          <h1 className="text-2xl font-bold text-white mt-1">Specialist vs. Baseline Comparison</h1>
        </div>

        <div className="flex items-center gap-3">
          {isAdapterActive ? (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-700">
                <CheckCircle2 className="w-3.5 h-3.5" /> Specialist Adapter Active
              </span>
              <button
                onClick={handleDeactivate}
                disabled={activating}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition"
                title="Revert to original unspecialized model"
              >
                Revert to Baseline
              </button>
            </div>
          ) : (
            <button
              onClick={handleActivate}
              disabled={activating}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/30 transition flex items-center gap-1.5 disabled:opacity-50"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              {activating ? 'Activating...' : `Activate Specialist (${results.adapter_id})`}
            </button>
          )}

          <button
            onClick={() => onNavigate('inference')}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/30 transition flex items-center gap-1.5"
          >
            Use Specialist &rarr;
          </button>
        </div>
      </div>

      {/* Outcome Banner */}
      <div
        className={`p-5 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
          results.outcome === 'improved'
            ? 'bg-emerald-950/20 border-emerald-600/40 text-emerald-200'
            : results.outcome === 'regressed'
            ? 'bg-rose-950/20 border-rose-600/40 text-rose-200'
            : 'bg-slate-900 border-slate-700 text-slate-300'
        }`}
      >
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <StatusBadge status={results.outcome} type="outcome" />
            <span className="font-bold text-sm text-white">{results.summary}</span>
          </div>
          <p className="text-xs text-slate-400">
            Evaluated on {baseline.sample_size} validation samples ({baseline.eval_split}).
            {results.is_simulated_fixture && ' [PROVENANCE: Visibly labeled Preview Mode Fixture Data].'}
          </p>
        </div>
        <div className="text-right">
          <span className="text-xs text-slate-400">Net Metric Delta:</span>
          <div className="text-xl font-bold font-mono text-white">
            {diffs.net_score > 0 ? `+${diffs.net_score}%` : `${diffs.net_score}%`}
          </div>
        </div>
      </div>

      {/* Metrics Head-to-Head Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map((m) => (
          <div key={m.name} className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3">
            <span className="text-xs font-medium text-slate-400">{m.name}</span>
            <div className="flex items-baseline justify-between">
              <div>
                <span className="text-2xl font-bold text-white font-mono">{m.candidate}{m.unit}</span>
                <span className="text-[11px] text-slate-500 ml-1">Specialist</span>
              </div>
              <div
                className={`text-xs font-mono font-semibold px-2 py-0.5 rounded ${
                  m.diff > 0
                    ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800'
                    : m.diff < 0
                    ? 'bg-rose-950/80 text-rose-400 border border-rose-800'
                    : 'bg-slate-800 text-slate-400'
                }`}
              >
                {m.diff > 0 ? `+${m.diff}` : m.diff}{m.unit}
              </div>
            </div>
            <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-500 font-mono">
              <span>Baseline:</span>
              <span>{m.baseline}{m.unit}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Individual Before/After Examples */}
      <div className="space-y-4">
        <h2 className="text-base font-bold text-white">Individual Prediction Comparison</h2>
        <p className="text-xs text-slate-400">
          Inspect how the specialized model handles multi-topic edge cases and subtle rules compared to the unspecialized prompt baseline.
        </p>

        <div className="space-y-4">
          {results.example_comparisons?.map((ex, idx) => (
            <div key={idx} className="p-4 rounded-xl border border-slate-800 bg-slate-900/40 space-y-3">
              <div className="text-xs font-medium text-slate-200 italic bg-slate-950/60 p-2.5 rounded-lg border border-slate-800">
                "{ex.input}"
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                {/* Baseline Box */}
                <div className="p-3 rounded-lg border border-slate-800 bg-slate-950/40 space-y-2">
                  <div className="flex items-center justify-between text-slate-400 text-[11px]">
                    <span className="font-bold">Original Model (Prompted Baseline)</span>
                    <span>Sentiment: {ex.baseline.sentiment}</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {ex.baseline.topics.map((t: string) => (
                      <span key={t} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300">
                        {t}
                      </span>
                    ))}
                  </div>
                  <p className="text-slate-400 text-[11px] italic">"{ex.baseline.summary}"</p>
                  {ex.baseline.needs_review && (
                    <span className="text-[10px] text-rose-400 block">Needs review: {ex.baseline.review_reason}</span>
                  )}
                </div>

                {/* Specialist Box */}
                <div className="p-3 rounded-lg border border-blue-500/30 bg-blue-950/20 space-y-2">
                  <div className="flex items-center justify-between text-blue-300 text-[11px]">
                    <span className="font-bold">Model + LoRA Specialist Adapter</span>
                    <span>Sentiment: {ex.specialist.sentiment}</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {ex.specialist.topics.map((t: string) => (
                      <span key={t} className="px-1.5 py-0.5 rounded text-[10px] bg-blue-900/60 text-blue-200 border border-blue-700/50">
                        {t}
                      </span>
                    ))}
                  </div>
                  <p className="text-slate-300 text-[11px] italic">"{ex.specialist.summary}"</p>
                  {ex.specialist.needs_review && (
                    <span className="text-[10px] text-rose-300 bg-rose-950/60 px-1.5 py-0.5 rounded border border-rose-800 block">
                      ⚠ Needs review: {ex.specialist.review_reason}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
