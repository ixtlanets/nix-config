// Run with the exact mise Node + DSH runtime; all stores are temporary fixtures.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, access, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { bootstrap, devicePrompt } from '../dsh-vm-login.mjs';

const noNetwork = async () => { throw new Error('Network forbidden in login tests'); };

test('real Codex flow offers device login; cancellation writes nothing', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dsh-login-test-'));
  const fetch = globalThis.fetch;
  globalThis.fetch = noNetwork;
  let ctx;
  try {
    const boot = await bootstrap(dir);
    ctx = boot.ctx;
    let prompted = false;
    const result = await ctx.authorization.begin({
      key: boot.key, method: 'oauth',
      interaction: {
        notify() { assert.fail('No network notices expected'); },
        async prompt(prompt) {
          assert.equal(devicePrompt(prompt), 'device_code');
          prompted = true;
          throw new boot.AuthorizationDeclinedError();
        },
      },
    });
    assert.equal(prompted, true);
    assert.equal(result.status, 'cancelled');
    await assert.rejects(access(join(dir, '.credentials.yaml')));
  } finally {
    if (ctx) await ctx.fiber.dispose();
    globalThis.fetch = fetch;
    await rm(dir, { recursive: true, force: true }); // Only this mkdtemp fixture.
  }
});

test('authorization commit preserves unrelated refs and records with private mode', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dsh-login-test-'));
  let ctx;
  try {
    ({ ctx } = await bootstrap(dir));
    await ctx.credentials.set('TEST_API_KEY', 'synthetic-api-key');
    await ctx.credentials.modifyRecord('test-login/existing', async () => ({kind: 'grant', payload: {fixture: true}}));
    const key = 'test-login/new-grant';
    ctx.authorization.registerFlow({
      key, label: 'Synthetic fixture', methods: [{id: 'fixture', label: 'Fixture'}],
      async run() {
        await ctx.credentials.modifyRecord(key, async () => ({kind: 'grant', payload: {synthetic: true}}));
      },
    });
    const result = await ctx.authorization.begin({key, interaction: {notify() {}, async prompt() {assert.fail();}}});
    assert.equal(result.status, 'authorized');
    assert.equal((await ctx.credentials.resolve('TEST_API_KEY')).value, 'synthetic-api-key');
    assert.deepEqual(await ctx.credentials.readRecord('test-login/existing'), {kind: 'grant', payload: {fixture: true}});
    assert.deepEqual(await ctx.credentials.readRecord(key), {kind: 'grant', payload: {synthetic: true}});
    assert.equal((await stat(join(dir, '.credentials.yaml'))).mode & 0o777, 0o600);
  } finally {
    if (ctx) await ctx.fiber.dispose();
    await rm(dir, { recursive: true, force: true }); // Only this mkdtemp fixture.
  }
});

test('never silently falls back to browser or secret entry', async () => {
  assert.throws(() => devicePrompt({kind: 'secret', message: 'Token'}));
  assert.throws(() => devicePrompt({kind: 'select', options: [{id: 'browser'}]}));
  await assert.rejects(bootstrap(undefined));
  await assert.rejects(bootstrap('relative'));
});
