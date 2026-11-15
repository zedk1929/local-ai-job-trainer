import test from 'node:test';
import assert from 'node:assert/strict';

/**
 * State manager replicating the exact transition and polling logic
 * implemented in FailureAnalysisPanel.tsx.
 */
class FailureAnalysisStateManager {
  constructor() {
    this.reset();
  }

  reset() {
    this.analysis = null;
    this.editableRules = [];
    this.approved = false;
    this.acknowledgedRemoval = false;
    this.saveError = null;
    this.savingRules = false;
    this.lastSavedRules = null;
  }

  switchBatch(newBatchId) {
    this.reset();
    this.currentBatchId = newBatchId;
  }

  hasUnsavedEdits() {
    return this.lastSavedRules !== null &&
      JSON.stringify(this.editableRules) !== JSON.stringify(this.lastSavedRules);
  }

  onPollResponse(response) {
    this.analysis = response.analysis;
    const incomingRules = response.analysis?.report?.proposed_rules;
    if (incomingRules && !this.savingRules) {
      const isDirty = this.hasUnsavedEdits();
      if (!isDirty && !this.saveError) {
        this.editableRules = [...incomingRules];
        this.lastSavedRules = [...incomingRules];
      }
    }
  }

  onUserEditRule(index, newText) {
    this.editableRules = [...this.editableRules];
    this.editableRules[index] = newText;
    this.approved = false;
    this.acknowledgedRemoval = false;
    this.saveError = null;
  }

  onSaveSuccess(savedRules, newRevision) {
    this.editableRules = [...savedRules];
    this.lastSavedRules = [...savedRules];
    this.saveError = null;
    if (this.analysis?.report) {
      this.analysis.report.proposed_rules = [...savedRules];
      this.analysis.report.rule_revision = newRevision;
    }
  }

  onRevert() {
    const target = this.lastSavedRules || this.analysis?.report?.proposed_rules || [];
    this.editableRules = [...target];
    this.saveError = null;
    this.approved = false;
    this.acknowledgedRemoval = false;
  }
}

test('1. Asynchronous proposal first arrival populates empty rule editor', () => {
  const manager = new FailureAnalysisStateManager();
  manager.switchBatch('batch_1');

  // Initially analyzing, no proposed rules yet
  assert.equal(manager.editableRules.length, 0);
  assert.equal(manager.lastSavedRules, null);
  assert.equal(manager.hasUnsavedEdits(), false);

  // Poll 1: still analyzing
  manager.onPollResponse({
    analysis: { status: 'analyzing', report: null }
  });
  assert.equal(manager.editableRules.length, 0);
  assert.equal(manager.lastSavedRules, null);

  // Poll 2: analysis finishes, ready status with proposed rules arrives
  const proposed = [
    'Assign only explicitly supported taxonomy IDs.',
    'Distinguish missed review flags from ordinary complaints.'
  ];
  manager.onPollResponse({
    analysis: {
      status: 'ready',
      report: { proposed_rules: proposed, rule_revision: 1 }
    }
  });

  // Editor must now be populated with the arriving proposal
  assert.deepEqual(manager.editableRules, proposed);
  assert.deepEqual(manager.lastSavedRules, proposed);
  assert.equal(manager.hasUnsavedEdits(), false);
});

test('2. Preserves actual user edits during subsequent background polling', () => {
  const manager = new FailureAnalysisStateManager();
  manager.switchBatch('batch_1');

  // Proposal arrives
  const originalProposed = [
    'Assign only explicitly supported taxonomy IDs.',
    'Rule 2 original'
  ];
  manager.onPollResponse({
    analysis: {
      status: 'ready',
      report: { proposed_rules: originalProposed, rule_revision: 1 }
    }
  });

  // User makes an edit in the rule editor
  manager.onUserEditRule(1, 'Rule 2 customized by user');
  assert.equal(manager.hasUnsavedEdits(), true);
  assert.equal(manager.editableRules[1], 'Rule 2 customized by user');

  // Next poll arrives while candidate comparison is starting or background tick runs
  manager.onPollResponse({
    analysis: {
      status: 'ready',
      report: { proposed_rules: originalProposed, rule_revision: 1 }
    }
  });

  // User edit must be strictly preserved
  assert.equal(manager.editableRules[1], 'Rule 2 customized by user');
  assert.equal(manager.hasUnsavedEdits(), true);
});

test('3. Resetting state on source batch switch', () => {
  const manager = new FailureAnalysisStateManager();
  manager.switchBatch('batch_1');

  manager.onPollResponse({
    analysis: {
      status: 'ready',
      report: { proposed_rules: ['Rule A', 'Rule B'], rule_revision: 1 }
    }
  });
  manager.onUserEditRule(0, 'Rule A edited');
  manager.approved = true;
  manager.acknowledgedRemoval = true;

  // Switch to batch_2
  manager.switchBatch('batch_2');

  assert.equal(manager.currentBatchId, 'batch_2');
  assert.deepEqual(manager.editableRules, []);
  assert.equal(manager.lastSavedRules, null);
  assert.equal(manager.approved, false);
  assert.equal(manager.acknowledgedRemoval, false);
  assert.equal(manager.saveError, null);
  assert.equal(manager.hasUnsavedEdits(), false);
});

test('4. Reverting dirty edits restores saved revision without re-populating on poll', () => {
  const manager = new FailureAnalysisStateManager();
  manager.switchBatch('batch_1');

  const savedRules = ['Original Rule 1', 'Original Rule 2'];
  manager.onPollResponse({
    analysis: {
      status: 'ready',
      report: { proposed_rules: savedRules, rule_revision: 1 }
    }
  });

  manager.onUserEditRule(0, 'Dirty modification');
  assert.equal(manager.hasUnsavedEdits(), true);

  manager.onRevert();
  assert.equal(manager.hasUnsavedEdits(), false);
  assert.deepEqual(manager.editableRules, savedRules);

  // Poll arrives - clean state remains in sync
  manager.onPollResponse({
    analysis: {
      status: 'ready',
      report: { proposed_rules: savedRules, rule_revision: 1 }
    }
  });
  assert.deepEqual(manager.editableRules, savedRules);
});
