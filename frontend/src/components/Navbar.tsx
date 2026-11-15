import React from 'react';
import { AppMode, Project } from '../types';
import { StatusBadge } from './StatusBadge';
import { Sparkles, Terminal, Settings2, Sliders, PlayCircle, BarChart3, Bot, CheckSquare } from 'lucide-react';

interface NavbarProps {
  activeScreen: string;
  setActiveScreen: (screen: string) => void;
  appMode: AppMode;
  onToggleMode: (mode: AppMode) => void;
  projects: Project[];
  selectedProject: Project | null;
  onSelectProject: (proj: Project) => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeScreen,
  setActiveScreen,
  appMode,
  onToggleMode,
  projects,
  selectedProject,
  onSelectProject,
}) => {
  const screens = [
    { id: 'jobs', label: '1. Jobs', icon: Bot },
    { id: 'setup', label: '2. Setup', icon: Settings2 },
    { id: 'config', label: '3. Configure & Import', icon: Sliders },
    { id: 'baseline', label: '4. Baseline & Coach', icon: CheckSquare, highlight: true },
    { id: 'experiment', label: '5. LoRA Training', icon: Terminal },
    { id: 'results', label: '6. Results', icon: BarChart3 },
    { id: 'inference', label: '7. Playground', icon: PlayCircle },
  ];

  return (
    <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Product Title */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base tracking-tight text-white">Apprentice</span>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">v0.2.0</span>
              </div>
              <p className="text-xs text-slate-400">Teach local AI a job</p>
            </div>
          </div>

          {/* Project Switcher */}
          {selectedProject && (
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/80">
              <span className="text-xs text-slate-400">Project:</span>
              <select
                aria-label="Active Project"
                value={selectedProject.id}
                onChange={(e) => {
                  const p = projects.find((x) => x.id === e.target.value);
                  if (p) onSelectProject(p);
                }}
                className="bg-transparent text-xs font-medium text-blue-400 focus:outline-none cursor-pointer"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id} className="bg-slate-900 text-white">
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Mode Switcher Badge */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800">
              <button
                onClick={() => onToggleMode('preview')}
                className={`px-2.5 py-1 rounded text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer ${
                  appMode === 'preview'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Preview mode uses deterministic fixtures. No API keys or model downloads required."
              >
                {appMode === 'preview' && <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>}
                Preview Mode
              </button>
              <button
                onClick={() => onToggleMode('connected')}
                className={`px-2.5 py-1 rounded text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer ${
                  appMode === 'connected'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Connected mode queries your real local Ollama model (qwen2.5-coder:3b)."
              >
                {appMode === 'connected' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>}
                Connected Mode
              </button>
            </div>
          </div>
        </div>

        {/* Step Navigation Bar */}
        <nav className="flex space-x-1 overflow-x-auto py-2 border-t border-slate-800/60 no-scrollbar">
          {screens.map((s) => {
            const Icon = s.icon;
            const isActive = activeScreen === s.id;
            return (
              <button
                key={s.id}
                onClick={() => setActiveScreen(s.id)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30 font-semibold'
                    : s.highlight
                    ? 'text-blue-300 hover:text-white bg-blue-950/30 border border-blue-900/50'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-blue-400' : s.highlight ? 'text-blue-400' : 'text-slate-500'}`} />
                {s.label}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
};
