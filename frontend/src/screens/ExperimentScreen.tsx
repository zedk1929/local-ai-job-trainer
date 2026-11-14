import React, { useState, useEffect, useRef } from 'react';
import { Project, Run, RunEvent, AppMode } from '../types';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { Play, Square, CheckCircle2, AlertCircle, RefreshCw, Terminal, Clock, ChevronRight, Lock } from 'lucide-react';

interface ExperimentScreenProps {
  project: Project | null;
  appMode: AppMode;
  onNavigate: (screen: string) => void;
  onRunCompleted: (run: Run) => void;
}

const STAGES = [
  { id: 'check_setup', label: '1. Check Setup', desc: 'Verify local model runtime & training capabilities' },
  { id: 'prepare_examples', label: '2. Prepare Examples', desc: 'Partition human data & generate synthetic pairs' },
  { id: 'measure_baseline', label: '3. Measure Baseline', desc: 'Evaluate unspecialized base model zero-shot prompt' },
  { id: 'train_adapter', label: '4. Train Adapter', desc: 'Fine-tune task-specific LoRA adapter weights' },
  { id: 'evaluate_candidate', label: '5. Evaluate Candidate', desc: 'Score candidate specialist on held-out validation set' },
  { id: 'save_result', label: '6. Save Result', desc: 'Persist run metrics, logs, and adapter candidate' },
];

export const ExperimentScreen: React.FC<ExperimentScreenProps> = ({
  project,
  appMode,
  onNavigate,
  onRunCompleted,
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

  const [runs, setRuns] = useState<Run[]>([]);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [starting, setStarting] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Poll active run
  const pollActiveRun = async (runId: string) => {
    try {
      const [updatedRun, eventsData] = await Promise.all([
        api.getRun(runId),
        api.getRunEvents(runId),
      ]);
      setActiveRun(updatedRun);
      setEvents(eventsData.events || []);

      if (updatedRun.status === 'completed') {
        onRunCompleted(updatedRun);
      }
    } catch (err) {
      console.error('Error polling run:', err);
    }
  };

  // Fetch initial runs
  const fetchRuns = async () => {
    try {
      const res = await fetch(`/api/runs?project_id=${project.id}`);
      const data: Run[] = await res.json();
      setRuns(data);
      if (data.length > 0 && !activeRun) {
        setActiveRun(data[0]);
        const eventsData = await api.getRunEvents(data[0].id);
        setEvents(eventsData.events || []);
      }
    } catch (err) {
      console.error('Error fetching runs:', err);
    }
  };

  useEffect(() => {
    fetchRuns();
  }, [project.id]);

  // Polling loop for active runs
  useEffect(() => {
    if (!activeRun) return;
    if (activeRun.status !== 'running' && activeRun.status !== 'queued') return;

    const interval = setInterval(() => {
      pollActiveRun(activeRun.id);
    }, 1000);

    return () => clearInterval(interval);
  }, [activeRun?.id, activeRun?.status]);

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [events]);

  // Start new run
  const handleStartRun = async () => {
    setStarting(true);
    try {
      const newRun = await api.startRun(project.id, {
        epochs: 3,
        learning_rate: 2e-4,
        batch_size: 4,
      });
      setActiveRun(newRun);
      setEvents([]);
      fetchRuns();
    } catch (err: any) {
      alert(err.message || 'Failed to start run');
    } finally {
      setStarting(false);
    }
  };

  // Cancel active run
  const handleCancelRun = async () => {
    if (!activeRun) return;
    setCanceling(true);
    try {
      await api.cancelRun(activeRun.id);
      await pollActiveRun(activeRun.id);
    } finally {
      setCanceling(false);
    }
  };

  const getStageStatus = (stageId: string) => {
    if (!activeRun) return 'queued';
    const activeStageIndex = STAGES.findIndex((s) => s.id === activeRun.current_stage);
    const thisStageIndex = STAGES.findIndex((s) => s.id === stageId);

    if (activeRun.status === 'completed') return 'completed';
    if (activeRun.status === 'canceled' || activeRun.status === 'interrupted' || activeRun.status === 'failed') {
      if (thisStageIndex === activeStageIndex) return activeRun.status;
      if (thisStageIndex < activeStageIndex) return 'completed';
      return 'queued';
    }

    if (thisStageIndex < activeStageIndex) return 'completed';
    if (thisStageIndex === activeStageIndex) return 'running';
    return 'queued';
  };

  const isConnectedMode = appMode === 'connected';

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800">
              Training Pipeline (Milestone Gate)
            </span>
            <span className="text-xs text-slate-400">· Project: {project.name}</span>
          </div>
          <h1 className="text-2xl font-bold text-white mt-1">LoRA Specialist Training</h1>
        </div>

        <div className="flex items-center gap-3">
          {isConnectedMode ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => onNavigate('baseline')}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/30 transition"
              >
                Go to Baseline Evaluation &rarr;
              </button>
            </div>
          ) : activeRun && (activeRun.status === 'running' || activeRun.status === 'queued') ? (
            <button
              onClick={handleCancelRun}
              disabled={canceling}
              className="px-4 py-2 rounded-lg bg-rose-600/80 hover:bg-rose-600 text-white text-xs font-semibold shadow-md shadow-rose-600/30 transition flex items-center gap-1.5 disabled:opacity-50"
            >
              <Square className="w-3.5 h-3.5" />
              {canceling ? 'Canceling...' : 'Cancel Run'}
            </button>
          ) : (
            <button
              onClick={handleStartRun}
              disabled={starting}
              className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition flex items-center gap-2 disabled:opacity-50"
            >
              <Play className="w-4 h-4 fill-white" />
              {starting ? 'Starting Run...' : 'Start Simulated Run (Preview)'}
            </button>
          )}

          {activeRun?.status === 'completed' && !isConnectedMode && (
            <button
              onClick={() => onNavigate('results')}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/30 transition flex items-center gap-1.5"
            >
              View Results &rarr;
            </button>
          )}
        </div>
      </div>

      {/* Connected Mode Honesty Notice */}
      {isConnectedMode && (
        <div className="p-4 rounded-xl border border-amber-800/80 bg-amber-950/20 text-xs text-amber-200 space-y-2">
          <div className="flex items-center gap-2 font-bold text-sm text-amber-300">
            <Lock className="w-4 h-4" />
            LoRA Training Disabled in Connected Mode for this Milestone
          </div>
          <p className="text-slate-300 leading-relaxed">
            Per project milestones, we do not perform simulated or unverified training in Connected Mode.
            Our current focus is <strong>real batch baseline evaluation</strong> of your local unspecialized model (<code>qwen2.5-coder:3b</code> on Ollama) to establish whether fine-tuning is necessary.
          </p>
          <div className="pt-1 flex items-center gap-3">
            <button
              onClick={() => onNavigate('baseline')}
              className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold shadow transition"
            >
              Open Real Baseline Evaluation &rarr;
            </button>
            <span className="text-[11px] text-slate-400">
              (Switch to Preview Mode from top right if you wish to inspect the simulated pipeline).
            </span>
          </div>
        </div>
      )}

      {/* Main Grid: Staged Workflow & Event Log */}
      <div className={`grid grid-cols-1 lg:grid-cols-12 gap-6 ${isConnectedMode ? 'opacity-60 pointer-events-none' : ''}`}>
        {/* Left: Staged Workflow Pipeline (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-white">Staged Training Workflow</h2>
              {activeRun && (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono text-slate-400">ID: {activeRun.id}</span>
                  <StatusBadge status={activeRun.status} type="stage" />
                </div>
              )}
            </div>

            <div className="space-y-3">
              {STAGES.map((s, idx) => {
                const status = getStageStatus(s.id);
                return (
                  <div
                    key={s.id}
                    className={`p-3 rounded-lg border transition-all ${
                      status === 'running'
                        ? 'border-blue-500/80 bg-blue-950/30 shadow-md shadow-blue-950/50'
                        : status === 'completed'
                        ? 'border-emerald-800/60 bg-emerald-950/20'
                        : 'border-slate-800 bg-slate-950/40 opacity-70'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {status === 'completed' ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        ) : status === 'running' ? (
                          <RefreshCw className="w-4 h-4 text-blue-400 animate-spin shrink-0" />
                        ) : (
                          <div className="w-4 h-4 rounded-full border border-slate-700 flex items-center justify-center text-[10px] text-slate-500 font-mono">
                            {idx + 1}
                          </div>
                        )}
                        <span className="text-xs font-semibold text-white">{s.label}</span>
                      </div>
                      <StatusBadge status={status} type="stage" />
                    </div>
                    <p className="text-[11px] text-slate-400 mt-1 pl-6 leading-tight">{s.desc}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Past Runs Selector */}
          {runs.length > 1 && (
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 space-y-2">
              <span className="text-xs font-semibold text-slate-300">Run History</span>
              <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                {runs.map((r) => (
                  <div
                    key={r.id}
                    onClick={() => {
                      setActiveRun(r);
                      api.getRunEvents(r.id).then((res) => setEvents(res.events || []));
                    }}
                    className={`p-2 rounded-lg text-xs cursor-pointer flex items-center justify-between border ${
                      activeRun?.id === r.id
                        ? 'border-blue-500 bg-blue-950/30 text-white'
                        : 'border-slate-800 bg-slate-950/40 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <span className="font-mono text-[11px]">{r.id}</span>
                    <StatusBadge status={r.status} type="stage" />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: Live Event Log Terminal (7 cols) */}
        <div className="lg:col-span-7 flex flex-col space-y-4">
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-950 flex-1 flex flex-col shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-xs">
              <div className="flex items-center gap-2 text-slate-300 font-medium">
                <Terminal className="w-4 h-4 text-emerald-400" />
                <span>Live Event Stream & Provenance Log</span>
              </div>
              <span className="text-[11px] font-mono text-slate-500">
                {events.length} events logged
              </span>
            </div>

            {/* Terminal log output */}
            <div
              ref={logContainerRef}
              className="mt-3 flex-1 overflow-y-auto space-y-1 font-mono text-[11px] min-h-[360px] max-h-[500px] pr-2"
            >
              {events.length === 0 ? (
                <div className="text-slate-600 italic py-8 text-center">
                  Waiting to start run... Click "Start Simulated Run" above to begin.
                </div>
              ) : (
                events.map((ev) => {
                  let color = 'text-slate-300';
                  if (ev.level === 'warning') color = 'text-amber-400';
                  if (ev.level === 'error') color = 'text-rose-400';
                  return (
                    <div key={ev.id} className="flex items-start gap-2 py-0.5 leading-relaxed">
                      <span className="text-slate-600 shrink-0 text-[10px]">
                        {ev.timestamp.split('T')[1]?.slice(0, 8)}
                      </span>
                      <span className="text-blue-400/90 shrink-0 uppercase text-[10px]">
                        [{ev.stage}]
                      </span>
                      <span className={color}>{ev.message}</span>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
