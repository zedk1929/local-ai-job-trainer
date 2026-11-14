import React from 'react';

interface StatusBadgeProps {
  status: string;
  type?: 'stage' | 'mode' | 'outcome' | 'capability';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, type = 'stage' }) => {
  let bg = 'bg-slate-800 text-slate-300 border-slate-700';

  if (type === 'mode') {
    if (status === 'preview') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-950/70 text-amber-300 border border-amber-700/50">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
          PREVIEW MODE (FIXTURES)
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950/70 text-emerald-300 border border-emerald-700/50">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          CONNECTED MODE
        </span>
      );
    }
  }

  if (type === 'stage') {
    switch (status) {
      case 'completed':
        bg = 'bg-emerald-950/60 text-emerald-400 border-emerald-800/60';
        break;
      case 'running':
        bg = 'bg-blue-950/60 text-blue-400 border-blue-800/60 animate-pulse';
        break;
      case 'queued':
        bg = 'bg-slate-800 text-slate-400 border-slate-700';
        break;
      case 'failed':
      case 'canceled':
      case 'interrupted':
        bg = 'bg-rose-950/60 text-rose-400 border-rose-800/60';
        break;
    }
  }

  if (type === 'outcome') {
    switch (status) {
      case 'improved':
        bg = 'bg-emerald-950/70 text-emerald-300 border-emerald-700/60';
        break;
      case 'neutral':
        bg = 'bg-slate-800 text-slate-300 border-slate-700';
        break;
      case 'regressed':
        bg = 'bg-rose-950/70 text-rose-300 border-rose-700/60';
        break;
    }
  }

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${bg}`}>
      {status.toUpperCase()}
    </span>
  );
};
