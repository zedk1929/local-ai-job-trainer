import React, { useState, useEffect } from 'react';
import { AppMode, JobDefinition, Project, SystemCapabilities, Run } from './types';
import { api } from './api/client';
import { Navbar } from './components/Navbar';
import { HomeScreen } from './screens/HomeScreen';
import { SetupScreen } from './screens/SetupScreen';
import { ConfigScreen } from './screens/ConfigScreen';
import { BaselineScreen } from './screens/BaselineScreen';
import { ExperimentScreen } from './screens/ExperimentScreen';
import { ResultsScreen } from './screens/ResultsScreen';
import { InferenceScreen } from './screens/InferenceScreen';

export const App: React.FC = () => {
  const [activeScreen, setActiveScreen] = useState('jobs');
  const [appMode, setAppMode] = useState<AppMode>('preview');
  const [capabilities, setCapabilities] = useState<SystemCapabilities | null>(null);
  const [jobs, setJobs] = useState<JobDefinition[]>([]);
  const [futurePresets, setFuturePresets] = useState<any[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [latestRun, setLatestRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true);

  const loadInitialData = async () => {
    try {
      const [caps, jobsData, projs] = await Promise.all([
        api.getCapabilities(),
        api.listJobs(),
        api.listProjects(),
      ]);
      setCapabilities(caps);
      setAppMode(caps.app_mode);
      setJobs(jobsData.jobs || []);
      setFuturePresets(jobsData.future_presets || []);

      if (projs.length > 0) {
        setProjects(projs);
        setSelectedProject(projs[0]);
      } else {
        const initialProj = await api.createProject({
          name: 'Campus Café Feedback',
          description: 'Turn messy campus coffee feedback into structured, flagged survey records.',
          job_id: 'survey-cleaner',
        });
        setProjects([initialProj]);
        setSelectedProject(initialProj);
      }
    } catch (err) {
      console.error('Failed to load initial data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  const handleToggleMode = async (mode: AppMode) => {
    try {
      await api.setAppMode(mode);
      setAppMode(mode);
      const caps = await api.getCapabilities();
      setCapabilities(caps);
    } catch (err) {
      console.error('Failed to change app mode:', err);
    }
  };

  const handleCreateProject = async (name: string, description: string) => {
    const proj = await api.createProject({ name, description, job_id: 'survey-cleaner' });
    setProjects([proj, ...projects]);
    setSelectedProject(proj);
  };

  const handleUpdateProject = (updated: Project) => {
    setProjects((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    setSelectedProject((curr) => (curr && curr.id === updated.id ? updated : curr));
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0b0f19] flex items-center justify-center text-slate-400 font-mono text-xs">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-blue-500 animate-ping"></div>
          Initializing Apprentice...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-100 flex flex-col font-sans selection:bg-blue-600 selection:text-white">
      <Navbar
        activeScreen={activeScreen}
        setActiveScreen={setActiveScreen}
        appMode={appMode}
        onToggleMode={handleToggleMode}
        projects={projects}
        selectedProject={selectedProject}
        onSelectProject={setSelectedProject}
      />

      <main className="flex-1 pb-16">
        {activeScreen === 'jobs' && (
          <HomeScreen
            jobs={jobs}
            futurePresets={futurePresets}
            projects={projects}
            selectedProject={selectedProject}
            onSelectProject={setSelectedProject}
            onCreateProject={handleCreateProject}
            onNavigate={setActiveScreen}
          />
        )}

        {activeScreen === 'setup' && (
          <SetupScreen
            capabilities={capabilities}
            onRefreshCapabilities={async () => {
              const caps = await api.getCapabilities();
              setCapabilities(caps);
            }}
            appMode={appMode}
            onToggleMode={handleToggleMode}
          />
        )}

        {activeScreen === 'config' && (
          <ConfigScreen
            key={selectedProject?.id || 'none'}
            project={selectedProject}
            onUpdateProject={handleUpdateProject}
            onNavigate={setActiveScreen}
          />
        )}

        {activeScreen === 'baseline' && (
          <BaselineScreen
            key={selectedProject?.id || 'none'}
            project={selectedProject}
            appMode={appMode}
            capabilities={capabilities}
            onNavigate={setActiveScreen}
            onUpdateProject={handleUpdateProject}
          />
        )}

        {activeScreen === 'experiment' && (
          <ExperimentScreen
            project={selectedProject}
            appMode={appMode}
            onNavigate={setActiveScreen}
            onRunCompleted={(run) => {
              setLatestRun(run);
            }}
          />
        )}

        {activeScreen === 'results' && (
          <ResultsScreen
            project={selectedProject}
            latestRun={latestRun}
            onUpdateProject={handleUpdateProject}
            onNavigate={setActiveScreen}
          />
        )}

        {activeScreen === 'inference' && (
          <InferenceScreen
            project={selectedProject}
            onNavigate={setActiveScreen}
          />
        )}
      </main>
    </div>
  );
};
