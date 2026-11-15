import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { AppMode, BaselineBatch, FailureAnalysis } from '../types';
import { AlertCircle, AlertTriangle, Check, Plus, Trash2, Undo2 } from 'lucide-react';

function getRuleValidationError(rules: string[]): string | null {
  if (rules.length === 0) return 'At least one proposed rule is required.';
  if (rules.length > 30) return 'At most 30 rules allowed.';
  for (let i = 0; i < rules.length; i++) {
    const trimmed = rules[i].trim();
    if (!trimmed) return `Rule #${i + 1} cannot be empty. Enter rule text or delete the rule.`;
    if (trimmed.length > 1200) return `Rule #${i + 1} exceeds 1200 characters (${trimmed.length} chars).`;
  }
  return null;
}

export function FailureAnalysisPanel({
  batch,
  appMode,
  onInspectBatch
}: {
  batch: BaselineBatch;
  appMode: AppMode;
  onInspectBatch: (batch: BaselineBatch) => void;
}) {
  const sourceId = batch.snapshot.source_batch_id || batch.id;
  const [analysis, setAnalysis] = useState<FailureAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [consent, setConsent] = useState(false);
  const [approved, setApproved] = useState(false);
  const [acknowledgedRemoval, setAcknowledgedRemoval] = useState(false);
  const [error, setError] = useState('');
  const [editableRules, setEditableRules] = useState<string[]>([]);
  const [savingRules, setSavingRules] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [rulesSaveSuccess, setRulesSaveSuccess] = useState(false);
  const mounted = useRef(true);
  const lastSavedRulesRef = useRef<string[] | null>(null);
  const editableRulesRef = useRef<string[]>(editableRules);
  editableRulesRef.current = editableRules;
  const savingRulesRef = useRef<boolean>(savingRules);
  savingRulesRef.current = savingRules;
  const saveErrorRef = useRef<string | null>(saveError);
  saveErrorRef.current = saveError;

  useEffect(() => {
    let active = true;
    mounted.current = true;
    // Reset editor and approval state when switching source batches
    setAnalysis(null);
    setEditableRules([]);
    setApproved(false);
    setAcknowledgedRemoval(false);
    setError('');
    setSaveError(null);
    setRulesSaveSuccess(false);
    setConsent(false);
    setLoading(true);
    lastSavedRulesRef.current = null;

    api.failureAnalysis(sourceId, 'get')
      .then(r => {
        if (active) {
          setAnalysis(r.analysis);
          if (r.analysis?.report?.proposed_rules) {
            setEditableRules(r.analysis.report.proposed_rules);
            lastSavedRulesRef.current = r.analysis.report.proposed_rules;
          }
        }
      })
      .catch(e => { if (active) setError(e.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; mounted.current = false; };
  }, [sourceId, batch.id]);

  const candidate = analysis?.comparison;
  const polling = analysis?.status === 'analyzing' || analysis?.comparison_batch_id === 'starting' ||
    candidate?.status === 'queued' || candidate?.status === 'running';

  useEffect(() => {
    if (!polling) return;
    let active = true;
    const timer = setInterval(() => {
      api.failureAnalysis(sourceId, 'get').then(r => {
        if (active) {
          setAnalysis(r.analysis);
          const incomingRules = r.analysis?.report?.proposed_rules;
          if (incomingRules && !savingRulesRef.current) {
            // Detect unsaved edits against the previously saved rules
            const hasUnsavedEdits = lastSavedRulesRef.current !== null &&
              JSON.stringify(editableRulesRef.current) !== JSON.stringify(lastSavedRulesRef.current);
            // Populate when asynchronous proposal first arrives (lastSavedRulesRef is null),
            // or preserve actual user edits during later polling if dirty
            if (!hasUnsavedEdits && !saveErrorRef.current) {
              setEditableRules(incomingRules);
              lastSavedRulesRef.current = incomingRules;
            }
          }
        }
      }).catch(e => { if (active) setError(e.message); });
    }, 1500);
    return () => { active = false; clearInterval(timer); };
  }, [sourceId, polling]);

  const report = analysis?.report || null;
  const savedRules = report?.proposed_rules || [];
  const savedRevision = report?.rule_revision || 1;
  const isRulesDirty = JSON.stringify(editableRules) !== JSON.stringify(savedRules);
  const ruleValidationError = getRuleValidationError(editableRules);
  const hasSaveFailed = Boolean(saveError);
  const isInvalidProposal = analysis?.status === 'invalid_proposal' || Boolean(report?.has_blocking_errors);
  const removedOriginalRules = report?.removed_original_rules || [];
  const hasRemovedRules = removedOriginalRules.length > 0;
  const canApprove = !isRulesDirty && !ruleValidationError && !savingRules && !hasSaveFailed && !isInvalidProposal && (!hasRemovedRules || acknowledgedRemoval);

  async function act(action: 'analyze' | 'compare') {
    setBusy(true); setError('');
    try {
      const options = action === 'compare'
        ? {
            rule_revision: savedRevision,
            approved_rules: savedRules,
            acknowledged_removed_rules: removedOriginalRules
          }
        : { consent };
      const result = await api.failureAnalysis(sourceId, action, options);
      if (mounted.current) {
        setAnalysis(result.analysis);
        if (result.analysis?.report?.proposed_rules) {
          setEditableRules(result.analysis.report.proposed_rules);
          lastSavedRulesRef.current = result.analysis.report.proposed_rules;
        }
      }
    } catch (e: any) {
      if (mounted.current) setError(e.message || 'Request failed.');
    } finally { if (mounted.current) setBusy(false); }
  }

  async function handleSaveRules(rulesToSave?: string[]) {
    const rules = rulesToSave || editableRules;
    const valErr = getRuleValidationError(rules);
    if (valErr) {
      setSaveError(valErr);
      setApproved(false);
      setAcknowledgedRemoval(false);
      return;
    }
    const cleaned = rules.map(r => r.trim()).filter(Boolean);
    setSavingRules(true);
    setSaveError(null);
    setApproved(false);
    setAcknowledgedRemoval(false);
    try {
      const res = await api.updateProposedRules(sourceId, cleaned, savedRevision);
      if (mounted.current && res.analysis) {
        setAnalysis(res.analysis);
        const saved = res.analysis.report.proposed_rules;
        setEditableRules(saved);
        lastSavedRulesRef.current = saved;
        setRulesSaveSuccess(true);
        setTimeout(() => {
          if (mounted.current) setRulesSaveSuccess(false);
        }, 3000);
      }
    } catch (e: any) {
      if (mounted.current) {
        setSaveError(e.message || 'Failed to save rule edits.');
        setApproved(false);
      }
    } finally {
      if (mounted.current) setSavingRules(false);
    }
  }

  const handleRuleChange = (idx: number, newVal: string) => {
    const updated = [...editableRules];
    updated[idx] = newVal;
    setEditableRules(updated);
    setApproved(false);
    setAcknowledgedRemoval(false);
    setSaveError(null);
  };

  const handleAddRule = () => {
    const updated = [...editableRules, ''];
    setEditableRules(updated);
    setApproved(false);
    setAcknowledgedRemoval(false);
    setSaveError(null);
  };

  const handleDeleteRule = (idx: number) => {
    if (editableRules.length <= 1) return;
    const updated = editableRules.filter((_, i) => i !== idx);
    setEditableRules(updated);
    setApproved(false);
    setAcknowledgedRemoval(false);
    setSaveError(null);
    handleSaveRules(updated);
  };

  const handleRestoreOriginalRule = (origRule: string) => {
    if (editableRules.includes(origRule)) return;
    const updated = [...editableRules, origRule];
    setEditableRules(updated);
    setApproved(false);
    setAcknowledgedRemoval(false);
    setSaveError(null);
    handleSaveRules(updated);
  };

  const handleRevertToSaved = () => {
    const target = lastSavedRulesRef.current || savedRules;
    setEditableRules([...target]);
    setSaveError(null);
    setApproved(false);
    setAcknowledgedRemoval(false);
    setRulesSaveSuccess(false);
  };

  const elapsed = analysis?.status === 'analyzing' ? Math.max(0, Math.floor((Date.now() - Date.parse(analysis.created_at)) / 1000)) : 0;
  const completed = candidate?.status === 'completed';
  const comparisonStarted = Boolean(analysis?.comparison_batch_id);
  const buttons = 'px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-sm font-semibold';
  const metricKeys = [
    ['topic_micro_f1', 'Topic F1'], ['sentiment_accuracy', 'Sentiment accuracy'],
    ['review_flag_accuracy', 'Review accuracy'], ['schema_validity_pct', 'Schema validity'],
  ] as const;

  return (
    <section className="rounded-xl border border-indigo-900 bg-slate-900/50 p-5 space-y-4" aria-label="Parent AI failure analysis">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-white">Understand failures. Review better rules.</h2>
          <p className="text-xs text-slate-400 mt-1">A proposal first. Your project rules and original results stay unchanged.</p>
        </div>
        <span className="text-xs font-mono text-indigo-300">
          {report ? (report.is_simulated ? 'PREVIEW RULE SUGGESTION' : 'PARENT AI ANALYSIS') : (appMode === 'preview' ? 'OFFLINE PREVIEW' : 'PARENT AI')}
        </span>
      </div>

      <p className="text-xs text-slate-400">
        We choose a fixed development subset (half the labeled rows, up to 20) for analysis. The remaining labeled rows are reserved for this comparison. This is development data, not an untouched final test. Requires 4–200 recorded rows with at least four valid labeled responses.
      </p>

      {error && <p role="alert" className="text-sm text-rose-300 flex items-center gap-1.5"><AlertCircle className="w-4 h-4 shrink-0" /> {error}</p>}
      {analysis?.status === 'failed' && <p role="alert" className="text-sm text-amber-300">{analysis.error_message}</p>}
      {analysis?.status === 'analyzing' && <p role="status" className="text-sm text-indigo-200">Parent analysis is running · {elapsed}s elapsed. This can take up to about three minutes. You can leave this page or refresh; the job continues and its status is saved. No automatic retry or duplicate request will be sent.</p>}

      {!report && analysis?.status !== 'analyzing' && (
        <>
          {appMode === 'connected' && (
            <label className="flex items-start gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />
              <span>I agree to send up to 20 development response excerpts (up to 4,000 characters each), their human labels and predictions, and this batch’s context, taxonomy, and rules to my configured parent provider (Gemini or Anthropic Claude, selected in Setup). Other CSV columns and comparison rows are not sent.</span>
            </label>
          )}
          <button className={buttons} disabled={loading || busy || (appMode === 'connected' && !consent)} onClick={() => act('analyze')}>
            {busy ? 'Analyzing failures…' : appMode === 'preview' ? 'Analyze Failures — Preview' : 'Analyze Failures'}
          </button>
          <p className="text-xs text-slate-500">Preview uses an explicitly labeled offline suggestion. Connected analysis requires a configured parent API key and never substitutes a fixture on failure.</p>
        </>
      )}

      {/* Invalid Proposal State */}
      {isInvalidProposal && (
        <div className="rounded-lg border border-rose-800 bg-rose-950/40 p-4 space-y-3" role="alert">
          <div className="flex items-center gap-2 text-rose-300 font-bold text-sm">
            <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
            <span>Invalid Proposal: Contradictory Evidence Detected</span>
          </div>
          <p className="text-xs text-rose-200">
            {analysis?.error_message || 'The parent analysis cited contradictory evidence or unsupported failure types. Comparison approval is disabled until a valid proposal is generated.'}
          </p>
          {report?.validation_errors && report.validation_errors.length > 0 && (
            <div className="space-y-1">
              <p className="text-[11px] font-semibold text-rose-300">Contradictory Claims:</p>
              <ul className="list-disc pl-5 space-y-1 text-xs text-rose-200">
                {report.validation_errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="pt-2">
            {appMode === 'connected' && (
              <label className="flex items-start gap-2 text-xs text-slate-300 mb-2">
                <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />
                <span>I agree to send up to 20 development responses to regenerate the analysis.</span>
              </label>
            )}
            <button
              className={buttons}
              disabled={busy || (appMode === 'connected' && !consent)}
              onClick={() => act('analyze')}
            >
              {busy ? 'Regenerating analysis…' : 'Deliberately Regenerate Analysis'}
            </button>
          </div>
        </div>
      )}

      {report && (
        <>
          <div className="text-xs text-slate-400 flex flex-wrap items-center gap-2">
            <span>Parent: {report.parent_model}</span>
            <span>·</span>
            <span>{report.development_row_indices.length} development rows</span>
            <span>·</span>
            <span>{report.evaluation_row_indices.length} comparison rows</span>
            <span>·</span>
            <span>{report.development_failure_count} development disagreements</span>
            <span>·</span>
            <span className="font-mono text-indigo-300">Rule Revision #{savedRevision}</span>
          </div>

          <p className="text-sm text-slate-200 whitespace-pre-wrap">{report.summary}</p>

          {/* Advisory Evidence Warnings */}
          {report.validation_warnings && report.validation_warnings.length > 0 && (
            <div className="rounded-lg border border-amber-800/80 bg-amber-950/30 p-3.5 space-y-2">
              <h4 className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Advisory Evidence Notes ({report.validation_warnings.length})
              </h4>
              <ul className="list-disc pl-5 space-y-1 text-xs text-amber-200">
                {report.validation_warnings.map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Removed Original Rules Warning */}
          {hasRemovedRules && (
            <div className="rounded-lg border border-amber-800/80 bg-amber-950/30 p-3.5 space-y-2">
              <h4 className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Removed Original Rules ({removedOriginalRules.length})
              </h4>
              <p className="text-[11px] text-amber-200/80">
                The following original rule(s) are omitted from proposed Revision #{savedRevision}. You must explicitly acknowledge their removal before approving comparison:
              </p>
              <ul className="list-disc pl-5 space-y-1.5 text-xs text-amber-200">
                {removedOriginalRules.map((rule, idx) => (
                  <li key={idx} className="flex items-center justify-between gap-2">
                    <span className="flex-1 font-mono text-xs">{rule}</span>
                    {!comparisonStarted && (
                      <button
                        type="button"
                        onClick={() => handleRestoreOriginalRule(rule)}
                        className="text-[10px] px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-indigo-300 transition shrink-0"
                      >
                        Restore Rule
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Requirement Warnings */}
          {report.requirement_warnings && report.requirement_warnings.length > 0 && (
            <div className="rounded-lg border border-rose-800/80 bg-rose-950/30 p-3.5 space-y-2">
              <h4 className="text-xs font-bold text-rose-300 flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-rose-400" />
                Advisory Requirement Heuristic Notes ({report.requirement_warnings.length})
              </h4>
              <ul className="list-disc pl-5 space-y-1.5 text-xs text-rose-200">
                {report.requirement_warnings.map((w, idx) => (
                  <li key={idx} className="leading-relaxed">{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Failure Groups */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Identified Failure Groups</h3>
            {report.groups.map((group, i) => (
              <div key={i} className="border-l-2 border-indigo-500 pl-3.5 py-1 space-y-1 bg-slate-950/30 rounded-r-lg p-2.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <h4 className="text-sm font-semibold text-white">{group.title}</h4>
                  {group.failure_type && group.failure_type !== 'other' && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-950 text-indigo-300 border border-indigo-800">
                      {group.failure_type.replace(/_/g, ' ')}
                    </span>
                  )}
                </div>
                <p className="text-sm text-slate-300 whitespace-pre-wrap">{group.explanation}</p>
                <p className="text-xs text-slate-500 font-mono">
                  Cited row indices (0-based): {group.row_indices.join(', ')} (Data rows: {group.row_indices.map(n => n + 1).join(', ')})
                </p>
              </div>
            ))}
          </div>

          {/* Side-by-Side: Original Rules vs Editable Proposed Rules */}
          <div className="grid md:grid-cols-2 gap-4">
            {/* Frozen Original Rules */}
            <div className="rounded-lg border border-slate-700 bg-slate-950/50 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-sm text-slate-200">Frozen Original Rules</h3>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">Immutable</span>
              </div>
              <ol className="list-decimal pl-5 space-y-2.5 text-sm text-slate-300">
                {report.original_rules.map((rule, i) => (
                  <li key={i} className="whitespace-pre-wrap group">
                    <div className="flex items-start justify-between gap-2">
                      <span className="flex-1">{rule}</span>
                      {!comparisonStarted && (
                        <button
                          type="button"
                          onClick={() => handleRestoreOriginalRule(rule)}
                          className="opacity-60 group-hover:opacity-100 text-[10px] px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-indigo-300 transition shrink-0"
                          title="Copy this original rule into the proposed rules"
                        >
                          <Undo2 className="w-3 h-3 inline mr-0.5" /> Copy
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
              {!report.original_rules.length && <p className="text-xs text-slate-500">No original rules configured.</p>}
            </div>

            {/* Editable Proposed Rules */}
            <div className="rounded-lg border border-indigo-700/60 bg-slate-950/70 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-sm text-indigo-200">Editable Proposed Rules</h3>
                  <span className="text-[11px] text-slate-400 font-mono">Revision #{savedRevision}</span>
                </div>
                {comparisonStarted ? (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                    Locked for Comparison
                  </span>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={handleAddRule}
                      className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-indigo-300 text-xs font-medium transition flex items-center gap-1"
                    >
                      <Plus className="w-3.5 h-3.5" /> Add
                    </button>
                    <button
                      type="button"
                      disabled={savingRules || !isRulesDirty}
                      onClick={() => handleSaveRules()}
                      className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition flex items-center gap-1 disabled:opacity-50"
                    >
                      {savingRules ? 'Saving...' : 'Save Rules'}
                    </button>
                  </div>
                )}
              </div>

              {rulesSaveSuccess && (
                <div className="p-2 rounded bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-1.5">
                  <Check className="w-3.5 h-3.5 shrink-0" />
                  <span>Rule edits saved as Revision #{savedRevision}! Re-review before approval.</span>
                </div>
              )}

              {/* Unsaved Changes Banner */}
              {isRulesDirty && !hasSaveFailed && (
                <div className="p-2 rounded bg-amber-950/40 border border-amber-800/80 text-amber-300 text-xs flex items-center justify-between">
                  <span>Unsaved changes in editor. Click "Save Rules" to update revision.</span>
                  <button
                    type="button"
                    onClick={handleRevertToSaved}
                    className="text-[11px] underline text-amber-200 hover:text-white ml-2 shrink-0"
                  >
                    Revert
                  </button>
                </div>
              )}

              {/* Save Failed Error Banner with Recovery Action */}
              {hasSaveFailed && (
                <div role="alert" className="p-2.5 rounded bg-rose-950/40 border border-rose-800 text-rose-300 text-xs space-y-1">
                  <p className="font-semibold flex items-center gap-1.5">
                    <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                    Save Failed: {saveError}
                  </p>
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => handleSaveRules()}
                      className="px-2 py-0.5 rounded bg-rose-900 hover:bg-rose-800 text-rose-200 text-xs font-medium"
                    >
                      Retry Save
                    </button>
                    <button
                      type="button"
                      onClick={handleRevertToSaved}
                      className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs"
                    >
                      Revert to Saved Revision #{savedRevision}
                    </button>
                  </div>
                </div>
              )}

              {/* Rule Validation Error Note */}
              {ruleValidationError && !hasSaveFailed && (
                <p className="text-xs text-rose-400">{ruleValidationError}</p>
              )}

              {/* Editable Rule Inputs */}
              <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                {editableRules.map((rule, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="text-xs font-mono text-slate-500 mt-2 shrink-0">{i + 1}.</span>
                    <textarea
                      rows={2}
                      disabled={comparisonStarted}
                      value={rule}
                      onChange={e => handleRuleChange(i, e.target.value)}
                      onBlur={() => {
                        if (editableRules[i] !== savedRules[i]) {
                          handleSaveRules();
                        }
                      }}
                      className="flex-1 px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-white text-xs focus:outline-none focus:border-indigo-500 disabled:opacity-75 disabled:bg-slate-950"
                      placeholder="Enter coding rule..."
                    />
                    {!comparisonStarted && editableRules.length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleDeleteRule(i)}
                        className="text-slate-500 hover:text-rose-400 p-1 mt-1.5 transition"
                        title="Delete rule"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>

              <p className="text-[11px] text-slate-400">
                You can edit, add, or restore rules. Edits persist across refresh and reset comparison approval.
              </p>
            </div>
          </div>

          <p className="text-xs text-amber-200">{report.disclaimer}</p>

          {/* Comparison Approval & Run */}
          {!analysis?.comparison_batch_id && (
            <div className="p-4 rounded-xl border border-indigo-800/80 bg-indigo-950/20 space-y-3">
              {hasRemovedRules && (
                <label className="flex items-start gap-2 text-xs text-amber-200 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={acknowledgedRemoval}
                    disabled={isRulesDirty || Boolean(ruleValidationError) || savingRules || hasSaveFailed || isInvalidProposal}
                    onChange={e => setAcknowledgedRemoval(e.target.checked)}
                    className="mt-0.5 rounded border-amber-700 bg-slate-900 text-indigo-600 focus:ring-0"
                  />
                  <span>
                    I explicitly acknowledge that {removedOriginalRules.length} original rule(s) were removed in Revision #{savedRevision}.
                  </span>
                </label>
              )}

              <label className="flex items-start gap-2 text-sm text-slate-200 cursor-pointer">
                <input
                  type="checkbox"
                  checked={approved}
                  disabled={!canApprove}
                  onChange={e => setApproved(e.target.checked)}
                  className="mt-0.5 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0"
                />
                <span>
                  I reviewed the proposed rules <strong>(Revision #{savedRevision})</strong> and approve running this exact revision on the evaluation subset.
                </span>
              </label>

              <button
                className={buttons}
                disabled={!approved || !canApprove || busy}
                onClick={() => act('compare')}
              >
                {busy ? 'Starting comparison…' : `Approve & run ${report.source_mode === 'preview' ? 'preview' : 'REAL local'} comparison (${report.evaluation_row_indices.length} rows)`}
              </button>

              {/* Explanatory notes if approval is disabled */}
              {isRulesDirty && (
                <p className="text-xs text-amber-300">Unsaved edits in editor. Click "Save Rules" or "Revert" before approving.</p>
              )}
              {hasSaveFailed && (
                <p className="text-xs text-rose-300">Save failed: {saveError}. Fix errors or revert to enable approval.</p>
              )}
              {ruleValidationError && !hasSaveFailed && (
                <p className="text-xs text-rose-300">Invalid rules: {ruleValidationError}</p>
              )}
              {hasRemovedRules && !acknowledgedRemoval && (
                <p className="text-xs text-amber-300">Acknowledgment of {removedOriginalRules.length} removed original rule(s) is required before approval.</p>
              )}
              {isInvalidProposal && (
                <p className="text-xs text-rose-300">Cannot approve an invalid proposal. Regenerate analysis above to continue.</p>
              )}

              <p className="text-xs text-slate-400">
                Uses source model {report.source_model}, its frozen settings, and no adapter. Only the approved coding rules revision will be executed. Original project configuration remains untouched.
              </p>
            </div>
          )}

          {/* Comparison Status and Metrics */}
          {analysis?.comparison_batch_id && (
            <div className="space-y-3 pt-2 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">Comparison: {candidate?.status || 'starting'}</h3>
                {report.approved_revision && (
                  <span className="text-xs font-mono text-indigo-300 bg-indigo-950 px-2 py-0.5 rounded border border-indigo-800">
                    Ran Rule Revision #{report.approved_revision}
                  </span>
                )}
              </div>
              {candidate && (
                <p className="text-xs text-slate-400">
                  {candidate.processed_rows} / {candidate.total_rows} processed · {candidate.app_mode === 'preview' ? 'SIMULATED PREVIEW' : 'REAL LOCAL INFERENCE'} · {candidate.id}
                </p>
              )}
              {candidate?.error_message && <p className="text-sm text-amber-300">{candidate.error_message}</p>}
              {completed && candidate?.metrics && (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                      <thead className="text-slate-400">
                        <tr>
                          <th className="py-2">Metric</th>
                          <th>Original rules</th>
                          <th>Approved proposed rules</th>
                          <th>Change</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metricKeys.map(([key, label]) => {
                          const before = report.reference_metrics[key];
                          const after = candidate.metrics![key];
                          const delta = before != null && after != null ? Math.round((after - before) * 10) / 10 : null;
                          return (
                            <tr key={key} className="border-t border-slate-800">
                              <td className="py-2">{label}</td>
                              <td>{before == null ? 'N/A' : `${before}%`}</td>
                              <td>{after == null ? 'N/A' : `${after}%`}</td>
                              <td>{delta == null ? 'N/A' : delta === 0 ? 'Unchanged' : `${delta > 0 ? '+' : ''}${delta} points`}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-xs text-slate-400">
                    Both columns use the same {report.evaluation_row_indices.length} comparison responses and human labels. Improvement is not guaranteed; inspect regressions as well as gains.
                  </p>
                </>
              )}
              {candidate && (
                <div className="flex items-center gap-2 pt-2">
                  <button className={buttons} onClick={() => onInspectBatch(candidate)}>
                    Inspect comparison rows
                  </button>
                  {candidate.processed_rows > 0 && (
                    <button
                      className={buttons}
                      onClick={async () => {
                        try {
                          await api.exportBaselineCsv(candidate.id);
                        } catch {
                          setError('Could not export comparison results.');
                        }
                      }}
                    >
                      Export comparison results
                    </button>
                  )}
                </div>
              )}
              {candidate && ['interrupted', 'canceled', 'failed'].includes(candidate.status) && (
                <p className="text-xs text-amber-300">
                  Partial results remain available. Use Inspect comparison rows to inspect or retry it; incomplete runs are not presented as a completed comparison.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
