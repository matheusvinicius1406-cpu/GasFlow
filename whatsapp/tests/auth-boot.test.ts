/**
 * SEC-02 — Fail-closed no boot: o serviço NÃO sobe sem proteção.
 *
 * Cenários (processo filho via `node --import tsx`, ENV controlado):
 *   A) sem chave e sem bypass                → exit 1
 *   B) sem chave + bypass + produção         → exit 1 (bypass ignorado em prod)
 *   C) com chave                             → exit 0 (sobe normalmente)
 *   D) sem chave + bypass em dev             → exit 0 (modo dev preservado)
 *
 * O exit 0 de C/D prova que a maquinaria (tsx + import de auth.ts) funciona;
 * o exit 1 de A/B prova que a recusa vem da validação de chave, não de crash.
 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const AUTH_URL = new URL('../src/auth.ts', import.meta.url).href;
const EVAL_CODE = `import(${JSON.stringify(AUTH_URL)}).then(() => process.exit(0), () => process.exit(2));`;

function baseEnv(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env };
  delete env.MARCOS_GAS_API_KEY;
  delete env.ALLOW_INSECURE_AUTH;
  delete env.ENVIRONMENT;
  return env;
}

function runAuthBoot(env: NodeJS.ProcessEnv): Promise<{ code: number | null; out: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['--import', 'tsx', '--eval', EVAL_CODE], {
      cwd: ROOT,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let out = '';
    child.stdout.on('data', (d: Buffer) => { out += d.toString(); });
    child.stderr.on('data', (d: Buffer) => { out += d.toString(); });
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error(`boot timeout. output:\n${out}`));
    }, 30_000);
    child.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ code, out });
    });
  });
}

describe('SEC-02 boot fail-closed (child process)', () => {
  it('A: sem chave e sem bypass → exit 1', async () => {
    const { code, out } = await runAuthBoot(baseEnv());
    assert.equal(code, 1, `esperava exit 1, obteve ${code}. output:\n${out}`);
  });

  it('B: sem chave + ALLOW_INSECURE_AUTH em produção → exit 1', async () => {
    const env = { ...baseEnv(), ALLOW_INSECURE_AUTH: 'true', ENVIRONMENT: 'production' };
    const { code, out } = await runAuthBoot(env);
    assert.equal(code, 1, `esperava exit 1, obteve ${code}. output:\n${out}`);
  });

  it('C: com chave → exit 0', async () => {
    const env = { ...baseEnv(), MARCOS_GAS_API_KEY: 'sec02-boot-key-0123456789' };
    const { code, out } = await runAuthBoot(env);
    assert.equal(code, 0, `esperava exit 0, obteve ${code}. output:\n${out}`);
  });

  it('D: sem chave + bypass em dev → exit 0 (modo dev preservado)', async () => {
    const env = { ...baseEnv(), ALLOW_INSECURE_AUTH: 'true', ENVIRONMENT: 'development' };
    const { code, out } = await runAuthBoot(env);
    assert.equal(code, 0, `esperava exit 0, obteve ${code}. output:\n${out}`);
  });
});
