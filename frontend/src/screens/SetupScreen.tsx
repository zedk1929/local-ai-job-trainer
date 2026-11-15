import React, { useState } from 'react';
import { SystemCapabilities, AppMode } from '../types';
import { api } from '../api/client';
import { Cpu, Key, ShieldCheck, AlertCircle, CheckCircle2, Server, HelpCircle, HardDrive } from 'lucide-react';

interface SetupScreenProps {
  capabilities: SystemCapabilities | null;
  onRefreshCapabilities: () => Promise<void>;
  appMode: AppMode;
  onToggleMode: (mode: AppMode) => void;
}

export const SetupScreen: React.FC<SetupScreenProps> = ({
  capabilities,
  onRefreshCapabilities,
  appMode,
  onToggleMode,
}) => {
  // Model state
  const [modelPath, setModelPath] = useState(capabilities?.model_inference.model_path || '');
  const [endpointUrl, setEndpointUrl] = useState(capabilities?.model_inference.endpoint_url || 'http://127.0.0.1:11434');
  const [modelName, setModelName] = useState(capabilities?.model_inference.model_name || '');
  const [savingModel, setSavingModel] = useState(false);

  // Supervisor state
  const [provider, setProvider] = useState(capabilities?.supervisor_api.provider || 'gemini');
  const [supervisorModel, setSupervisorModel] = useState(capabilities?.supervisor_api.model || 'gemini-3.8-flash');
  const [apiKey, setApiKey] = useState('');
  const [testingSupervisor, setTestingSupervisor] = useState(false);
  const [testResult, setTestResult] = useState<{ connected: boolean; message: string } | null>(null);


  const handleSaveModel = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingModel(true);
    try {
      await api.updateModelConfig({
        model_path: modelPath,
        endpoint_url: endpointUrl,
        model_name: modelName,
      });
      await onRefreshCapabilities();
    } finally {
      setSavingModel(false);
    }
  };

  const handleTestSupervisor = async () => {
    setTestingSupervisor(true);
    setTestResult(null);
    try {
      await api.updateSupervisorConfig({ provider, model: supervisorModel, ...(apiKey ? { api_key: apiKey } : {}) });
      setApiKey('');
      const res = await api.testSupervisor();
      setTestResult(res);
      await onRefreshCapabilities();
    } catch (err: any) {
      setTestResult({ connected: false, message: err.message || 'Connection test failed' });
    } finally {
      setTestingSupervisor(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">
      {/* Screen Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Model and Supervisor Setup</h1>
        <p className="text-sm text-slate-400">
          Configure the local model and the parent AI that reviews failures and proposes coding rules.
        </p>
      </div>

      {/* Operating Mode Banner */}
      <div className={`p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
        appMode === 'preview'
          ? 'bg-amber-950/20 border-amber-600/40 text-amber-200'
          : 'bg-emerald-950/20 border-emerald-600/40 text-emerald-200'
      }`}>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm">
              Current Mode: {appMode === 'preview' ? 'Preview Mode (Deterministic Fixtures)' : 'Connected Mode'}
            </span>
          </div>
          <p className="text-xs text-slate-300">
            {appMode === 'preview'
              ? 'Works out-of-the-box without API keys, downloads, or GPU setup. All scores and outputs are visibly labeled sample fixtures.'
              : 'Directly communicates with your verified local model runtime and supervisor API key.'}
          </p>
        </div>
        <button
          onClick={() => onToggleMode(appMode === 'preview' ? 'connected' : 'preview')}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700 hover:bg-slate-800 text-white transition self-start sm:self-center"
        >
          Switch to {appMode === 'preview' ? 'Connected Mode' : 'Preview Mode'}
        </button>
      </div>

      {/* Capability Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 1. Local Model Inference */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase text-slate-400">Model Inference</span>
            {capabilities?.model_inference.available ? (
              <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5" /> Ready
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] text-slate-400 font-medium">
                <AlertCircle className="w-3.5 h-3.5" /> Preview Fixture
              </span>
            )}
          </div>
          <div className="text-sm font-bold text-white flex items-center gap-2">
            <Cpu className="w-4 h-4 text-blue-400" />
            {capabilities?.model_inference.model_name || 'Unconfigured (Sample)'}
          </div>
          <p className="text-xs text-slate-400">
            {capabilities?.model_inference.endpoint_url || capabilities?.model_inference.model_path || 'No local weights loaded'}
          </p>
        </div>

        {/* 2. Supervisor API */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase text-slate-400">Supervisor API</span>
            {capabilities?.supervisor_api.configured ? (
              <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5" /> Configured
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] text-amber-400 font-medium">
                <AlertCircle className="w-3.5 h-3.5" /> No Key
              </span>
            )}
          </div>
          <div className="text-sm font-bold text-white flex items-center gap-2">
            <Key className="w-4 h-4 text-amber-400" />
            {capabilities?.supervisor_api.provider?.toUpperCase()} ({capabilities?.supervisor_api.model})
          </div>
          <p className="text-xs text-slate-400">
            {capabilities?.supervisor_api.configured ? 'API key active for synthetic generation' : 'Using pre-computed synthetic fixtures'}
          </p>
        </div>

        {/* 3. Adapter Training */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase text-slate-400">Adapter Training</span>
            {capabilities?.adapter_training.supported ? (
              <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5" /> Verified
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] text-amber-400 font-medium">
                <AlertCircle className="w-3.5 h-3.5" /> Simulated
              </span>
            )}
          </div>
          <div className="text-sm font-bold text-white flex items-center gap-2">
            <Server className="w-4 h-4 text-purple-400" />
            Backend: {capabilities?.adapter_training.backend}
          </div>
          <p className="text-xs text-slate-400">
            {capabilities?.adapter_training.message}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Section 1: Local Model Setup */}
        <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
          <div className="flex items-center gap-2">
            <HardDrive className="w-5 h-5 text-blue-400" />
            <h2 className="text-base font-bold text-white">Local Model Connection</h2>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            Connect the existing model on your machine. We do not download models automatically.
            GGUF formats support inference; PEFT/LoRA training requires unquantized source weights (e.g. safetensors).
          </p>

          <form onSubmit={handleSaveModel} className="space-y-4 pt-2">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Local Inference Endpoint URL</label>
              <input
                type="text"
                value={endpointUrl}
                onChange={(e) => setEndpointUrl(e.target.value)}
                placeholder="http://127.0.0.1:11434 (e.g. Ollama, llama.cpp, vLLM)"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs font-mono focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Or Explicit Local File / Directory Path</label>
              <input
                type="text"
                value={modelPath}
                onChange={(e) => setModelPath(e.target.value)}
                placeholder="/Users/lcooney/models/mistral-7b.gguf"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs font-mono focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Model Name / Alias</label>
              <input
                type="text"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                placeholder="e.g. llama3.2:3b or mistral"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500"
              />
            </div>

            {capabilities?.model_inference.notes && (
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 space-y-1">
                <span className="text-[11px] font-semibold text-slate-400">Diagnostics:</span>
                {capabilities.model_inference.notes.map((note, idx) => (
                  <p key={idx} className="text-[11px] text-slate-400 font-mono leading-tight">
                    • {note}
                  </p>
                ))}
              </div>
            )}

            <button
              type="submit"
              disabled={savingModel}
              className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition disabled:opacity-50"
            >
              {savingModel ? 'Verifying...' : 'Save & Verify Model Connection'}
            </button>
          </form>
        </div>

        {/* Section 2: Supervisor Setup */}
        <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-amber-400" />
            <h2 className="text-base font-bold text-white">Supervisor LLM Configuration</h2>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            The parent AI analyzes approved development examples and proposes revised coding rules.
            It never executes system commands or accesses local model weights directly.
          </p>

          <div className="space-y-4 pt-2">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Supervisor Provider</label>
              <select
                aria-label="Supervisor Provider"
                value={provider}
                onChange={(e) => {
                  const selected = e.target.value;
                  setProvider(selected);
                  setSupervisorModel(selected === 'anthropic' ? 'claude-sonnet-5-5' : 'gemini-3.8-flash');
                  setApiKey(''); setTestResult(null);
                }}
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs focus:outline-none focus:border-blue-500"
              >
                <option value="gemini">Google Gemini</option>
                <option value="openai" disabled>OpenAI (not connected yet)</option>
                <option value="anthropic">Anthropic Claude</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Model Name</label>
              <input
                type="text"
                value={supervisorModel}
                onChange={(e) => setSupervisorModel(e.target.value)}
                placeholder={provider === 'anthropic' ? 'claude-sonnet-5-5' : 'gemini-3.8-flash'}
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs font-mono focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Supervisor API Key</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Paste API key here (kept in local memory/env only)"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs font-mono focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Privacy boundary note */}
            <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                Data Privacy Boundary
              </div>
              <p className="text-[11px] text-slate-400 leading-normal">
                By default, the supervisor synthesizes examples strictly from your survey description and category definitions.
                Failure analysis shares a development subset only after separate, explicit consent on the Baseline Batch screen. Comparison rows are not sent for analysis.
              </p>
              <p className="text-[11px] text-slate-400">API keys stay in backend memory and are not saved to browser storage or returned by the API. Re-enter the key after a backend restart. Gemini checks key and model access without generating text; Claude sends a small paid test request.</p>
            </div>

            {testResult && (
              <div
                className={`p-3 rounded-lg text-xs font-medium border ${
                  testResult.connected
                    ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
                    : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
                }`}
              >
                {testResult.message}
              </div>
            )}

            <button
              onClick={handleTestSupervisor}
              disabled={testingSupervisor}
              className="w-full py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold transition disabled:opacity-50"
            >
              {testingSupervisor ? 'Testing Connection...' : 'Save & Test Parent Connection'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
