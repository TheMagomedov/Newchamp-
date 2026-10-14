import { test } from 'node:test';
import assert from 'node:assert/strict';
import { transitionPayload } from '../src/transitions.js';

const staleForm = {
  team_id: '1', actual_start: '2027-01-01T08:00:00',
  actual_end: '2027-01-01T09:00:00', completion_report: 'Работа выполнена',
};

test('status-only action from a stale card cannot revert a concurrently changed team', () => {
  const currentServerRecord = { TeamId: 2, Status: 'в работе' };
  const payload = transitionPayload({ ...staleForm, status: 'ожидает материалов' }, { TeamId: 1 });
  assert.deepEqual(payload, { status: 'ожидает материалов' });
  // Model the backend's optional-field update: omitted team_id preserves the new team.
  const merged = { ...currentServerRecord, Status: payload.status, ...('team_id' in payload ? { TeamId: payload.team_id } : {}) };
  assert.equal(merged.TeamId, 2);
});

test('explicit assignment includes the chosen team and no unrelated hidden fields', () => {
  assert.deepEqual(transitionPayload({ ...staleForm, status: 'назначена', team_id: '3' }, {}), { status: 'назначена', team_id: 3 });
});

test('resuming work preserves existing actual start without sending its stale copy', () => {
  assert.deepEqual(transitionPayload({ ...staleForm, status: 'в работе' }, { ActualStart: '2027-01-01T07:00:00', TeamId: 1 }), { status: 'в работе' });
});

test('first start includes the visible start input but not the old team', () => {
  assert.deepEqual(transitionPayload({ ...staleForm, status: 'в работе' }, { ActualStart: null, TeamId: 1 }), { status: 'в работе', actual_start: staleForm.actual_start });
});

test('completion includes only end and report, never team or previous start', () => {
  assert.deepEqual(transitionPayload({ ...staleForm, status: 'выполнена' }, { TeamId: 1 }), {
    status: 'выполнена', actual_end: staleForm.actual_end, completion_report: staleForm.completion_report,
  });
});

test('close and cancellation do not echo any prepopulated optional fields', () => {
  for (const status of ['закрыта', 'отменена']) assert.deepEqual(transitionPayload({ ...staleForm, status }, { TeamId: 1 }), { status });
});
