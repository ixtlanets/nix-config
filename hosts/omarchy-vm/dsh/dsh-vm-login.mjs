#!/usr/bin/env node
// Compatibility entrypoint for the OAuth seam not exposed by the rc.1 Models UI.
// The installed DSH adapter owns the grant and its locked credential-store write.
import { createRequire } from 'node:module';
import { existsSync, realpathSync } from 'node:fs';
import { isAbsolute, join } from 'node:path';
import { pathToFileURL } from 'node:url';

export async function bootstrap(dshHome) {
  if (!dshHome || !isAbsolute(dshHome)) throw new Error('Explicit absolute DSH_HOME required');
  const binary = process.env.PATH.split(':').map(p => join(p, 'dsh')).find(existsSync);
  if (!binary) throw new Error('Pinned DSH is not on PATH');
  const cli = createRequire(createRequire(realpathSync(binary)).resolve('@deepseek-ai/dsh/package.json'));
  const base = createRequire(cli.resolve('@deepseek-ai/dsh-base/package.json'));
  const piRequire = createRequire(base.resolve('@deepseek-ai/dsh-llm-pi-ai'));
  const load = async (require, id) => import(pathToFileURL(require.resolve(id)).href);
  const { Context } = await load(cli, '@deepseek-ai/cordis');
  const { default: Credentials } = await load(base, '@deepseek-ai/dsh-credentials-local');
  const { default: Authorization, AuthorizationDeclinedError } = await load(piRequire, '@deepseek-ai/dsh-authorization');
  const { default: Llm } = await load(base, '@deepseek-ai/dsh-llm');
  const pi = await load(base, '@deepseek-ai/dsh-llm-pi-ai');
  const ctx = new Context();
  try {
    await ctx.plugin(Credentials, { dshHome, watch: false }).await();
    await ctx.plugin(Authorization).await();
    await ctx.plugin(Llm).await();
    await ctx.plugin(pi, {}).await();
    const key = pi.recordKeyFor('openai-codex');
    if (!ctx.authorization.describe(key)?.methods.some(m => m.id === 'oauth')) {
      throw new Error('Installed DSH has no Codex OAuth flow');
    }
    return { ctx, key, AuthorizationDeclinedError };
  } catch (error) {
    await ctx.fiber.dispose();
    throw error;
  }
}

export function devicePrompt(prompt) {
  if (prompt.kind === 'select' && prompt.options.some(o => o.id === 'device_code')) {
    return 'device_code';
  }
  throw new Error('Unexpected OAuth prompt; refusing browser/token-input fallback');
}

async function main() {
  const mode = process.argv[2];
  if (!['login', 'status'].includes(mode) || process.argv.length !== 3) {
    throw new Error('Use via dsh-vm login or dsh-vm login-status');
  }
  const { ctx, key } = await bootstrap(process.env.DSH_HOME);
  const controller = new AbortController();
  const cancel = () => controller.abort();
  process.on('SIGINT', cancel);
  process.on('SIGTERM', cancel);
  try {
    if (mode === 'status') {
      const info = await ctx.credentials.describeRecord(key);
      console.log(JSON.stringify(info)); // Redacted metadata only; never readRecord().
      return;
    }
    console.log('Sign in to the VM instance. Never share the displayed device code.');
    const result = await ctx.authorization.begin({
      key, method: 'oauth', signal: controller.signal,
      interaction: {
        prompt: async prompt => devicePrompt(prompt),
        notify: notice => {
          console.log(notice.message);
          if (notice.url) console.log(notice.url);
          if (notice.code) console.log('Device code: ' + notice.code);
        },
      },
    });
    if (result.status !== 'authorized') throw new Error('Authorization cancelled');
    console.log('Codex authorized on VM; stored through the DSH credential service.');
  } finally {
    process.off('SIGINT', cancel);
    process.off('SIGTERM', cancel);
    await ctx.fiber.dispose();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => {
    // Provider error objects can contain request data; do not dump them.
    console.error('Codex authorization failed/cancelled. Retry dsh-vm login; no credentials were printed.');
    process.exitCode = 1;
  });
}
