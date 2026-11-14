import React, { useState } from 'react';
import { JobDefinition, Project } from '../types';
import { ArrowRight, CheckCircle2, Clock, Plus, Sparkles, Database, FileSpreadsheet, Layers } from 'lucide-react';

interface HomeScreenProps {
  jobs: JobDefinition[];
  futurePresets: any[];
  projects: Project[];
  selectedProject: Project | null;
  onSelectProject: (proj: Project) => void;
  onCreateProject: (name: string, description: string) => Promise<void>;
  onNavigate: (screen: string) => void;
}

export const HomeScreen: React.FC<HomeScreenProps> = ({
  jobs,
  futurePresets,
  projects,
  selectedProject,
  onSelectProject,
  onCreateProject,
  onNavigate,
}) => {
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState('Campus Café Feedback');
  const [description, setDescription] = useState('Clean and categorize customer feedback for university coffee shops.');
  const [loading, setLoading] = useState(false);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await onCreateProject(name, description);
      setShowModal(false);
      onNavigate('config');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-10">
      {/* Hero Section */}
      <div className="text-center max-w-3xl mx-auto space-y-4">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-950/60 text-blue-400 border border-blue-800/60 text-xs font-semibold">
          <Sparkles className="w-3.5 h-3.5" />
          Hackathon Edition · Local AI Specialization
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white">
          Teach local AI a job.
        </h1>
        <p className="text-base sm:text-lg text-slate-400 leading-relaxed">
          Transform a general local language model into a reliable, consistent specialist for specific tasks.
          A supervising LLM guides data preparation and training without touching your private raw weights.
        </p>
      </div>

      {/* Available Job Presets */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Layers className="w-5 h-5 text-blue-400" />
              Available Job Presets
            </h2>
            <p className="text-xs text-slate-400">Choose a job definition contract to train your model</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/20 transition"
          >
            <Plus className="w-4 h-4" />
            New Project
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Active Job: Survey Cleaner */}
          {jobs.map((job) => (
            <div
              key={job.id}
              className="relative rounded-xl border-2 border-blue-500/50 bg-gradient-to-b from-blue-950/30 to-slate-900/80 p-6 flex flex-col justify-between shadow-xl shadow-blue-950/50 hover:border-blue-400 transition"
            >
              <div className="absolute top-4 right-4">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  <CheckCircle2 className="w-3 h-3 text-blue-400" />
                  Active Preset
                </span>
              </div>
              <div className="space-y-3">
                <div className="w-10 h-10 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
                  <FileSpreadsheet className="w-5 h-5" />
                </div>
                <h3 className="text-lg font-bold text-white">{job.title}</h3>
                <p className="text-xs text-slate-300 leading-relaxed">{job.description}</p>
                
                <div className="pt-2 border-t border-slate-800 space-y-1">
                  <div className="text-[11px] font-mono text-slate-400">Version: {job.version}</div>
                  <div className="text-[11px] text-slate-400">Metrics: Micro-F1, Sentiment, Schema Validity</div>
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-800/80 flex items-center justify-between">
                <button
                  onClick={() => {
                    if (!selectedProject) setShowModal(true);
                    else onNavigate('config');
                  }}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition shadow-md shadow-blue-600/30"
                >
                  Configure This Job
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}

          {/* Future Presets */}
          {futurePresets.map((preset) => (
            <div
              key={preset.id}
              className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 flex flex-col justify-between opacity-60"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="w-10 h-10 rounded-lg bg-slate-800/50 border border-slate-700/50 flex items-center justify-center text-slate-500">
                    <Database className="w-5 h-5" />
                  </div>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                    <Clock className="w-3 h-3" />
                    {preset.badge}
                  </span>
                </div>
                <h3 className="text-lg font-bold text-slate-300">{preset.title}</h3>
                <p className="text-xs text-slate-400 leading-relaxed">{preset.description}</p>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-800/80">
                <button
                  disabled
                  className="w-full py-2 rounded-lg bg-slate-800/50 text-slate-500 text-xs font-medium cursor-not-allowed"
                >
                  Unbuilt Preset
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Existing Projects Table */}
      <div className="space-y-4 pt-4 border-t border-slate-800/80">
        <h2 className="text-lg font-bold text-white">Your Specialization Projects</h2>
        {projects.length === 0 ? (
          <div className="p-8 rounded-xl border border-dashed border-slate-800 text-center space-y-2">
            <p className="text-sm text-slate-400">No projects created yet.</p>
            <button
              onClick={() => setShowModal(true)}
              className="text-xs text-blue-400 hover:text-blue-300 font-semibold"
            >
              + Create your first project now
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((proj) => {
              const isSelected = selectedProject?.id === proj.id;
              return (
                <div
                  key={proj.id}
                  onClick={() => onSelectProject(proj)}
                  className={`p-4 rounded-xl border cursor-pointer transition flex flex-col justify-between ${
                    isSelected
                      ? 'border-blue-500 bg-blue-950/20'
                      : 'border-slate-800 bg-slate-900/50 hover:border-slate-700'
                  }`}
                >
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white text-sm">{proj.name}</span>
                      {isSelected && (
                        <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider">Active</span>
                      )}
                    </div>
                    <p className="text-xs text-slate-400 line-clamp-2">{proj.survey_context || proj.description}</p>
                  </div>
                  <div className="mt-4 pt-3 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-500">
                    <span>{proj.taxonomy.length} categories</span>
                    <span className="text-blue-400 hover:text-blue-300">Open &rarr;</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* New Project Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-white">Create Specialization Project</h3>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Project Name</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500"
                  placeholder="e.g. Campus Café Feedback"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Description</label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500"
                  placeholder="Brief summary of what this model will learn..."
                />
              </div>
              <div className="p-3 rounded-lg bg-slate-800/60 border border-slate-700/60 text-xs text-slate-300 space-y-1">
                <div className="font-semibold text-slate-200">Preset: Survey Cleaner (v1.0.0)</div>
                <p className="text-slate-400 text-[11px]">
                  Initializes with café demonstration categories (drink quality, price, service, seating) and customizable coding rules.
                </p>
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/30 transition disabled:opacity-50"
                >
                  {loading ? 'Creating...' : 'Create Project'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
