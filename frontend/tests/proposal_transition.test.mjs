import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';
import { FailureAnalysisPanel } from '../src/components/FailureAnalysisPanel';
import { api } from '../src/api/client';

const mockBatch1 = {
  id: 'batch_1',
  project_id: 'proj_1',
  dataset_id: 'sample_dev_60',
  status: 'completed',
  model_name: 'qwen2.5-coder:3b',
  model_endpoint: 'http://localhost:11434',
  job_version: '0.1.0',
  concurrency: 1,
  total_rows: 10,
  processed_rows: 10,
  error_count: 0,
  blank_count: 0,
  elapsed_seconds: 5,
  throughput_items_per_sec: 2,
  snapshot: { source_batch_id: 'batch_1' },
  metrics: null,
  error_message: null,
  created_at: '2026-11-15T10:00:00.000Z',
  updated_at: '2026-11-15T10:01:00.000Z',
  completed_at: '2026-11-15T10:01:00.000Z',
};

const mockBatch2 = {
  id: 'batch_2',
  project_id: 'proj_1',
  dataset_id: 'sample_dev_60',
  status: 'completed',
  model_name: 'qwen2.5-coder:3b',
  model_endpoint: 'http://localhost:11434',
  job_version: '0.1.0',
  concurrency: 1,
  total_rows: 10,
  processed_rows: 10,
  error_count: 0,
  blank_count: 0,
  elapsed_seconds: 5,
  throughput_items_per_sec: 2,
  snapshot: { source_batch_id: 'batch_2' },
  metrics: null,
  error_message: null,
  created_at: '2026-11-15T10:02:00.000Z',
  updated_at: '2026-11-15T10:03:00.000Z',
  completed_at: '2026-11-15T10:03:00.000Z',
};

describe('FailureAnalysisPanel component transition & polling tests', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('1. Asynchronous proposal first arrival populates empty rule editor', async () => {
    let pollCount = 0;
    const proposed = [
      'Assign only explicitly supported taxonomy IDs.',
      'Distinguish missed review flags from ordinary complaints.'
    ];

    vi.spyOn(api, 'failureAnalysis').mockImplementation(async (batchId, action) => {
      pollCount++;
      if (pollCount === 1) {
        // Poll 1: still analyzing
        return {
          analysis: {
            id: 'fa_1',
            source_batch_id: 'batch_1',
            status: 'analyzing',
            report: null,
            error_message: null,
            comparison_batch_id: null,
            comparison: null,
            created_at: new Date().toISOString(),
          }
        };
      }
      // Poll 2: ready status with proposed rules arrives
      return {
        analysis: {
          id: 'fa_1',
          source_batch_id: 'batch_1',
          status: 'ready',
          error_message: null,
          comparison_batch_id: null,
          comparison: null,
          created_at: new Date().toISOString(),
          report: {
            summary: 'Disagreements identified and proposed rules generated.',
            groups: [],
            original_rules: ['Rule 1 original'],
            proposed_rules: proposed,
            rule_revision: 1,
            development_row_indices: [0, 1],
            evaluation_row_indices: [2, 3],
            development_failure_count: 1,
            reference_metrics: {},
            is_simulated: true,
            parent_model: 'Gemini',
            source_mode: 'preview',
            source_model: 'qwen2.5-coder:3b',
            disclaimer: 'Development proposal only.'
          }
        }
      };
    });

    render(React.createElement(FailureAnalysisPanel, {
      batch: mockBatch1,
      appMode: 'preview',
      onInspectBatch: vi.fn(),
    }));

    // Initially analyzing running state is displayed
    await waitFor(() => {
      expect(screen.getByRole('status')).toBeDefined();
    });
    expect(screen.queryByPlaceholderText('Enter coding rule...')).toBeNull();

    // Advance timer past polling interval (1500ms) to trigger poll 2
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });

    // Proposed rules must now arrive and populate textareas in the editor
    await waitFor(() => {
      const textareas = screen.getAllByPlaceholderText('Enter coding rule...');
      expect(textareas.length).toBe(2);
      expect(textareas[0].value).toBe(proposed[0]);
      expect(textareas[1].value).toBe(proposed[1]);
    });
  });

  it('2. Preserves actual user edits during subsequent background polling', async () => {
    const originalProposed = [
      'Assign only explicitly supported taxonomy IDs.',
      'Rule 2 original'
    ];

    vi.spyOn(api, 'failureAnalysis').mockResolvedValue({
      analysis: {
        id: 'fa_1',
        source_batch_id: 'batch_1',
        status: 'ready',
        error_message: null,
        comparison_batch_id: null,
        comparison: null,
        created_at: new Date().toISOString(),
        report: {
          summary: 'Diagnostic summary',
          groups: [],
          original_rules: ['Rule 1'],
          proposed_rules: originalProposed,
          rule_revision: 1,
          development_row_indices: [0, 1],
          evaluation_row_indices: [2, 3],
          development_failure_count: 1,
          reference_metrics: {},
          is_simulated: true,
          parent_model: 'Gemini',
          source_mode: 'preview',
          source_model: 'qwen2.5-coder:3b',
          disclaimer: 'Development proposal only.'
        }
      }
    });

    render(React.createElement(FailureAnalysisPanel, {
      batch: mockBatch1,
      appMode: 'preview',
      onInspectBatch: vi.fn(),
    }));

    // Wait for textareas to appear
    await waitFor(() => {
      const textareas = screen.getAllByPlaceholderText('Enter coding rule...');
      expect(textareas.length).toBe(2);
    });

    const textareas = screen.getAllByPlaceholderText('Enter coding rule...');

    // User makes an edit in rule 2
    fireEvent.change(textareas[1], { target: { value: 'Rule 2 customized by user' } });
    expect(textareas[1].value).toBe('Rule 2 customized by user');

    // Unsaved changes banner must appear
    expect(screen.getByText(/Unsaved changes in editor/i)).toBeDefined();

    // Trigger subsequent background polling tick
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });

    // The user's edit must be strictly preserved
    expect(textareas[1].value).toBe('Rule 2 customized by user');
  });

  it('3. Resetting state on source batch switch', async () => {
    vi.spyOn(api, 'failureAnalysis').mockImplementation(async (batchId) => {
      const isBatch1 = batchId === 'batch_1';
      return {
        analysis: {
          id: `fa_${batchId}`,
          source_batch_id: batchId,
          status: 'ready',
          error_message: null,
          comparison_batch_id: null,
          comparison: null,
          created_at: new Date().toISOString(),
          report: {
            summary: `Summary for ${batchId}`,
            groups: [],
            original_rules: ['Original'],
            proposed_rules: isBatch1 ? ['Rule A', 'Rule B'] : ['Rule X for batch 2'],
            rule_revision: 1,
            development_row_indices: [0, 1],
            evaluation_row_indices: [2, 3],
            development_failure_count: 1,
            reference_metrics: {},
            is_simulated: true,
            parent_model: 'Gemini',
            source_mode: 'preview',
            source_model: 'qwen2.5-coder:3b',
            disclaimer: ''
          }
        }
      };
    });

    const { rerender } = render(React.createElement(FailureAnalysisPanel, {
      batch: mockBatch1,
      appMode: 'preview',
      onInspectBatch: vi.fn(),
    }));

    await waitFor(() => {
      const textareas = screen.getAllByPlaceholderText('Enter coding rule...');
      expect(textareas.length).toBe(2);
      expect(textareas[0].value).toBe('Rule A');
    });

    // User edits rule 0 in batch 1
    const textareas = screen.getAllByPlaceholderText('Enter coding rule...');
    fireEvent.change(textareas[0], { target: { value: 'Rule A edited' } });
    expect(textareas[0].value).toBe('Rule A edited');

    // Switch to batch_2
    rerender(React.createElement(FailureAnalysisPanel, {
      batch: mockBatch2,
      appMode: 'preview',
      onInspectBatch: vi.fn(),
    }));

    // State must reset: batch 2 rules loaded, previous edits cleared
    await waitFor(() => {
      const newTextareas = screen.getAllByPlaceholderText('Enter coding rule...');
      expect(newTextareas.length).toBe(1);
      expect(newTextareas[0].value).toBe('Rule X for batch 2');
    });

    expect(screen.queryByText(/Unsaved changes in editor/i)).toBeNull();
  });

  it('4. Saving dirty edits updates saved revision and clears dirty state', async () => {
    vi.spyOn(api, 'failureAnalysis').mockResolvedValue({
      analysis: {
        id: 'fa_1',
        source_batch_id: 'batch_1',
        status: 'ready',
        error_message: null,
        comparison_batch_id: null,
        comparison: null,
        created_at: new Date().toISOString(),
        report: {
          summary: 'Diagnostic summary',
          groups: [],
          original_rules: ['Rule 1'],
          proposed_rules: ['Rule 1', 'Rule 2'],
          rule_revision: 1,
          development_row_indices: [0, 1],
          evaluation_row_indices: [2, 3],
          development_failure_count: 1,
          reference_metrics: {},
          is_simulated: true,
          parent_model: 'Gemini',
          source_mode: 'preview',
          source_model: 'qwen2.5-coder:3b',
          disclaimer: ''
        }
      }
    });

    const updateSpy = vi.spyOn(api, 'updateProposedRules').mockResolvedValue({
      analysis: {
        id: 'fa_1',
        source_batch_id: 'batch_1',
        status: 'ready',
        error_message: null,
        comparison_batch_id: null,
        comparison: null,
        created_at: new Date().toISOString(),
        report: {
          summary: 'Diagnostic summary',
          groups: [],
          original_rules: ['Rule 1'],
          proposed_rules: ['Rule 1 updated', 'Rule 2'],
          rule_revision: 2,
          development_row_indices: [0, 1],
          evaluation_row_indices: [2, 3],
          development_failure_count: 1,
          reference_metrics: {},
          is_simulated: true,
          parent_model: 'Gemini',
          source_mode: 'preview',
          source_model: 'qwen2.5-coder:3b',
          disclaimer: ''
        }
      }
    });

    render(React.createElement(FailureAnalysisPanel, {
      batch: mockBatch1,
      appMode: 'preview',
      onInspectBatch: vi.fn(),
    }));

    await waitFor(() => {
      const textareas = screen.getAllByPlaceholderText('Enter coding rule...');
      expect(textareas.length).toBe(2);
    });

    const textareas = screen.getAllByPlaceholderText('Enter coding rule...');
    fireEvent.change(textareas[0], { target: { value: 'Rule 1 updated' } });

    // Click "Save Rules"
    const saveButton = screen.getByRole('button', { name: /Save Rules/i });
    expect(saveButton.disabled).toBe(false);

    await act(async () => {
      fireEvent.click(saveButton);
    });

    expect(updateSpy).toHaveBeenCalledWith('batch_1', ['Rule 1 updated', 'Rule 2'], 1);

    await waitFor(() => {
      expect(screen.getByText(/Rule edits saved as Revision #2!/i)).toBeDefined();
    });

    // Unsaved changes banner is gone
    expect(screen.queryByText(/Unsaved changes in editor/i)).toBeNull();
  });

  it('5. Reverting dirty edits restores saved revision without re-populating on poll', async () => {
    const savedRules = ['Original Rule 1', 'Original Rule 2'];

    vi.spyOn(api, 'failureAnalysis').mockResolvedValue({
      analysis: {
        id: 'fa_1',
        source_batch_id: 'batch_1',
        status: 'ready',
        error_message: null,
        comparison_batch_id: null,
        comparison: null,
        created_at: new Date().toISOString(),
        report: {
          summary: 'Diagnostic summary',
          groups: [],
          original_rules: ['Rule 1'],
          proposed_rules: savedRules,
          rule_revision: 1,
          development_row_indices: [0, 1],
          evaluation_row_indices: [2, 3],
          development_failure_count: 1,
          reference_metrics: {},
          is_simulated: true,
          parent_model: 'Gemini',
          source_mode: 'preview',
          source_model: 'qwen2.5-coder:3b',
          disclaimer: ''
        }
      }
    });

    render(React.createElement(FailureAnalysisPanel, {
      batch: mockBatch1,
      appMode: 'preview',
      onInspectBatch: vi.fn(),
    }));

    await waitFor(() => {
      const textareas = screen.getAllByPlaceholderText('Enter coding rule...');
      expect(textareas.length).toBe(2);
    });

    const textareas = screen.getAllByPlaceholderText('Enter coding rule...');
    fireEvent.change(textareas[0], { target: { value: 'Dirty modification' } });

    const revertButton = screen.getByRole('button', { name: /Revert/i });
    fireEvent.click(revertButton);

    // Should be restored to original rule 1
    expect(textareas[0].value).toBe('Original Rule 1');
    expect(screen.queryByText(/Unsaved changes in editor/i)).toBeNull();

    // Poll tick occurs
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });

    expect(textareas[0].value).toBe('Original Rule 1');
  });

  it('6. Empty analysis report ({}) displays running state without crashing', async () => {
    vi.spyOn(api, 'failureAnalysis').mockResolvedValue({
      analysis: {
        id: 'fa_empty',
        source_batch_id: 'batch_1',
        status: 'analyzing',
        report: {}, // empty analysis report
        error_message: null,
        comparison_batch_id: null,
        comparison: null,
        created_at: new Date().toISOString(),
      }
    });

    render(React.createElement(FailureAnalysisPanel, {
      batch: mockBatch1,
      appMode: 'preview',
      onInspectBatch: vi.fn(),
    }));

    // Must render running state and NOT crash
    await waitFor(() => {
      const statusEl = screen.getByRole('status');
      expect(statusEl).toBeDefined();
      expect(statusEl.textContent).toContain('analyzing');
    });

    // Should not crash and should not render broken report fields
    expect(screen.queryByText(/Cannot read properties of undefined/i)).toBeNull();
  });
});
