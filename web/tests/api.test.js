import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

// Browser APIs are mocked in memory. These tests never contact or modify the database.
const stored = new Map();
globalThis.sessionStorage = { getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value), removeItem: key => stored.delete(key) };
globalThis.window = { dispatchEvent() {} };
const { request, setSession, createMutationAttempt } = await import('../src/api.js');
const ok = data => new Response(JSON.stringify({ success: true, data }), { status: 200, headers: { 'Content-Type': 'application/json' } });
const unauthorized = () => new Response(JSON.stringify({ success: false, message: 'Expired access' }), { status: 401, headers: { 'Content-Type': 'application/json' } });
beforeEach(() => { setSession(null); });

for (const [name, path, options] of [
  ['create form', 'work-orders', { method: 'POST', body: { Description: 'Repair', EquipmentId: 1 } }],
  ['status transition', 'work-orders/5/transition', { method: 'POST', body: { status: 'в работе' } }],
  ['material writeoff', 'work-orders/5/materials', { method: 'POST', body: { MaterialId: 2, Quantity: 3 } }],
]) {
  test(`${name}: lost response + manual retry does not commit twice`, async () => {
    const attempt = createMutationAttempt(); const committed = new Map(); const keys = []; let dropResponse = true;
    globalThis.fetch = async (_url, init) => {
      const key = init.headers['Idempotency-Key']; keys.push(key);
      if (!committed.has(key)) committed.set(key, { Id: committed.size + 1 });
      if (dropResponse) { dropResponse = false; throw new Error('Connection lost after commit'); }
      return ok(committed.get(key));
    };
    await assert.rejects(attempt.run(path, options), error => error.code === 'NETWORK');
    assert.deepEqual(await attempt.run(path, options), { Id: 1 });
    assert.equal(keys[0], keys[1]); assert.equal(committed.size, 1);
    // A deliberate new submission after confirmed success is a different operation.
    assert.deepEqual(await attempt.run(path, options), { Id: 2 });
    assert.notEqual(keys[1], keys[2]);
  });
}

test('changed payload and cancellation reset the pending key', async () => {
  const attempt = createMutationAttempt(); const keys = [];
  globalThis.fetch = async (_url, init) => { keys.push(init.headers['Idempotency-Key']); throw new Error('Offline'); };
  const send = body => attempt.run('work-orders/3/materials/7', { method: 'PUT', body });
  await assert.rejects(send({ Quantity: 1, Comment: 'same' }));
  await assert.rejects(send({ Comment: 'same', Quantity: 1 }));
  assert.equal(keys[0], keys[1], 'Object property order does not change a logical payload');
  await assert.rejects(send({ Quantity: 2, Comment: 'same' }));
  assert.notEqual(keys[1], keys[2]);
  attempt.reset(); // Form closed/cancelled or a new object opened.
  await assert.rejects(send({ Quantity: 2, Comment: 'same' }));
  assert.notEqual(keys[2], keys[3]);
});

test('another object/path gets a new pending key', async () => {
  const attempt = createMutationAttempt(); const keys = [];
  globalThis.fetch = async (_url, init) => { keys.push(init.headers['Idempotency-Key']); throw new Error('Offline'); };
  await assert.rejects(attempt.run('work-orders/3', { method: 'DELETE' }));
  await assert.rejects(attempt.run('work-orders/4', { method: 'DELETE' }));
  assert.notEqual(keys[0], keys[1]);
});

test('file import retries keep a key for identical bytes and change it for different bytes', async () => {
  const attempt = createMutationAttempt(); const keys = [];
  globalThis.fetch = async (_url, init) => { keys.push(init.headers['Idempotency-Key']); throw new Error('Offline'); };
  const send = content => attempt.run('import/equipment?filename=equipment.csv', { method: 'POST', raw: true, body: new Blob([content]) });
  await assert.rejects(send('A;B')); await assert.rejects(send('A;B')); await assert.rejects(send('A;C'));
  assert.equal(keys[0], keys[1]); assert.notEqual(keys[1], keys[2]);
});

test('automatic 401 retry preserves the mutation key', async () => {
  setSession({ access_token: 'expired', refresh_token: 'old-refresh' });
  const calls = []; let first = true;
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    if (url.endsWith('/refresh')) return ok({ access_token: 'new-access', refresh_token: 'new-refresh' });
    if (first) { first = false; return unauthorized(); }
    return ok({ Id: 1 });
  };
  await request('work-orders', { method: 'POST', body: { Description: 'same' } });
  assert.equal(calls[0].init.headers['Idempotency-Key'], calls[2].init.headers['Idempotency-Key']);
  assert.equal(calls[2].init.headers.Authorization, 'Bearer new-access');
});

test('logout after expired access refreshes and revokes the newly rotated session', async () => {
  setSession({ access_token: 'expired', refresh_token: 'old-refresh' });
  const calls = []; let firstLogout = true; let revoked = null;
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    if (url.endsWith('/refresh')) return ok({ access_token: 'new-access', refresh_token: 'new-refresh' });
    if (firstLogout) { firstLogout = false; return unauthorized(); }
    revoked = JSON.parse(init.body).refresh_token;
    return ok(null);
  };
  await request('auth/logout', { method: 'POST', body: { refresh_token: 'old-refresh' } });
  assert.deepEqual(calls.map(x => x.url), ['/api/auth/logout', '/api/auth/refresh', '/api/auth/logout']);
  assert.equal(calls[2].init.headers.Authorization, 'Bearer new-access');
  assert.equal(revoked, 'new-refresh');
});

test('auth/me also refreshes expired access', async () => {
  setSession({ access_token: 'expired', refresh_token: 'old-refresh' });
  const urls = []; let first = true;
  globalThis.fetch = async url => {
    urls.push(url);
    if (url.endsWith('/refresh')) return ok({ access_token: 'new-access', refresh_token: 'new-refresh' });
    if (first) { first = false; return unauthorized(); }
    return ok({ Id: 1 });
  };
  assert.deepEqual(await request('/api/auth/me'), { Id: 1 });
  assert.deepEqual(urls, ['/api/auth/me', '/api/auth/refresh', '/api/auth/me']);
});

for (const endpoint of ['auth/login', 'auth/refresh']) {
  test(`${endpoint} never recursively refreshes on 401`, async () => {
    setSession({ access_token: 'expired', refresh_token: 'old-refresh' });
    const urls = [];
    globalThis.fetch = async url => { urls.push(url); return unauthorized(); };
    await assert.rejects(request(endpoint, { method: 'POST', body: {} }), error => error.status === 401);
    assert.deepEqual(urls, [`/api/${endpoint}`]);
  });
}

for (const status of [400, 403, 404, 409, 429, 500]) {
  test(`HTTP ${status} is handled with readable feedback and sanitized context`, async () => {
    const output = []; const original = console.error;
    console.error = (...args) => output.push(args);
    try {
      setSession({ access_token: 'must-not-log-access', refresh_token: 'must-not-log-refresh' });
      globalThis.fetch = async () => new Response(JSON.stringify({ success: false, error_code: 'TEST_ERROR' }), { status, headers: { 'Content-Type': 'application/json' } });
      await assert.rejects(request('equipment?search=private-name', { method: 'POST', body: { Password: 'must-not-log-password' } }), error => error.status === status && error.message.length > 10);
      const logged = JSON.stringify(output);
      assert.ok(logged.includes('equipment'));
      assert.ok(logged.includes('stack'));
      for (const secret of ['must-not-log-access', 'must-not-log-refresh', 'must-not-log-password', 'private-name']) assert.ok(!logged.includes(secret));
    } finally { console.error = original; }
  });
}

test('intentional request cancellation remains AbortError, not a misleading network alert', async () => {
  globalThis.fetch = async () => { throw new DOMException('Aborted', 'AbortError'); };
  await assert.rejects(request('dashboard'), error => error.name === 'AbortError');
});
test('invalid JSON response produces a readable error rather than leaking parser internals', async () => {
  const original = console.error; console.error = () => {};
  try {
    globalThis.fetch = async () => new Response('{bad-json', { headers: { 'Content-Type': 'application/json' } });
    await assert.rejects(request('equipment'), error => error.code === 'INVALID_RESPONSE' && error.message.includes('некорректный ответ'));
  } finally { console.error = original; }
});
test('download capability tokens are redacted from diagnostic logs', async () => {
  const output = []; const original = console.error; console.error = (...args) => output.push(args);
  try {
    globalThis.fetch = async () => new Response('', { status: 404 });
    await assert.rejects(request('download/private-capability-token'));
    assert.ok(!JSON.stringify(output).includes('private-capability-token'));
    assert.ok(JSON.stringify(output).includes('download/:token'));
  } finally { console.error = original; }
});
