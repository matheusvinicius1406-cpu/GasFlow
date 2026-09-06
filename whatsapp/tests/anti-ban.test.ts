/**
 * Anti-ban hygiene — unit tests.
 *
 * Rate limiter (caps + cooldown), warmup ladder, quiet hours e pacing gaussiano.
 * Usa DATA_DIR temporário para isolar o SQLite do ambiente de dev/prod.
 */

import { describe, it, before, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// Módulos puros (sem db) — import estático.
import { gaussianRandom, gaussianDelayMs } from '../src/anti-ban/gaussian';
import { isQuietHour, nextAllowedTime } from '../src/anti-ban/quiet-hours';

// Módulos com db — import dinâmico após configurar DATA_DIR/caps.
type Limiter = typeof import('../src/anti-ban/limiter');
type Warmup = typeof import('../src/anti-ban/warmup');
type Db = typeof import('../src/db');

let limiter: Limiter;
let warmup: Warmup;
let dbmod: Db;

before(async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gasflow-antiban-'));
  process.env.DATA_DIR = dir;
  process.env.WA_MINUTE_CAP = '5';
  process.env.WA_HOURLY_CAP = '8';
  process.env.WA_RECIPIENT_COOLDOWN_MIN = '60';

  limiter = await import('../src/anti-ban/limiter');
  warmup = await import('../src/anti-ban/warmup');
  dbmod = await import('../src/db');
});

// ── Rate limiter ─────────────────────────────────────────

describe('limiter.checkRate', () => {
  beforeEach(() => {
    dbmod.db.prepare('DELETE FROM send_history').run();
  });

  it('permite envio quando não há histórico', () => {
    const r = limiter.checkRate('acc', '5511999999999', 1_000_000);
    assert.equal(r.allowed, true);
  });

  it('bloqueia no minute cap (5/min)', () => {
    const base = 10 * 60_000;
    for (let i = 0; i < 5; i++) {
      limiter.recordSend('acc', `5511${i}`, `m${i}`, base + i);
    }
    const r = limiter.checkRate('acc', '5599999999999', base + 100);
    assert.equal(r.allowed, false);
    assert.equal(r.reason, 'minute_cap');
  });

  it('libera novamente após a janela de 1 minuto', () => {
    const base = 20 * 60_000;
    for (let i = 0; i < 5; i++) {
      limiter.recordSend('acc2', `5522${i}`, `m${i}`, base + i * 1_000);
    }
    // Ainda dentro da janela de 1 min — bloqueado.
    assert.equal(limiter.checkRate('acc2', 'x', base + 5_000).allowed, false);
    // Fora da janela — liberado (cooldown por destinatário não se aplica: destinatário novo).
    assert.equal(limiter.checkRate('acc2', 'novo-dest', base + 61_000).allowed, true);
  });

  it('bloqueia no hourly cap (8/h)', () => {
    const base = 30 * 60_000;
    for (let i = 0; i < 8; i++) {
      // Espalhados no intervalo de uma hora, mas nunca 5 no mesmo minuto.
      limiter.recordSend('acc3', `5533${i}`, `m${i}`, base + i * 61_000);
    }
    const r = limiter.checkRate('acc3', 'novo', base + 8 * 61_000);
    assert.equal(r.allowed, false);
    assert.equal(r.reason, 'hourly_cap');
  });

  it('aplica cooldown por destinatário (60 min)', () => {
    const base = 40 * 60_000;
    limiter.recordSend('acc4', '5544000000000', 'm1', base);
    const blocked = limiter.checkRate('acc4', '5544000000000', base + 30 * 60_000);
    assert.equal(blocked.allowed, false);
    assert.equal(blocked.reason, 'recipient_cooldown');
    assert.equal(blocked.retryAtMs, base + 60 * 60_000);

    const allowed = limiter.checkRate('acc4', '5544000000000', base + 61 * 60_000);
    assert.equal(allowed.allowed, true);
  });

  it('cooldown é isolado por conta e por destinatário', () => {
    const base = 50 * 60_000;
    limiter.recordSend('acc5', '5555000000000', 'm1', base);
    // Outro destinatário na mesma conta — liberado.
    assert.equal(limiter.checkRate('acc5', '5555111111111', base + 1_000).allowed, true);
    // Mesmo destinatário, outra conta — liberado.
    assert.equal(limiter.checkRate('acc6', '5555000000000', base + 1_000).allowed, true);
  });

  it('currentUsage reporta janelas correntes', () => {
    const base = 60 * 60_000;
    limiter.recordSend('acc7', '5577000000000', 'm1', base);
    const usage = limiter.currentUsage('acc7', base + 1_000);
    assert.equal(usage.lastMinute, 1);
    assert.equal(usage.lastHour, 1);
    assert.equal(usage.minuteCap, 5);
    assert.equal(usage.hourlyCap, 8);
  });
});

// ── Warmup ───────────────────────────────────────────────

describe('warmup', () => {
  beforeEach(() => {
    dbmod.db.prepare('DELETE FROM send_counters').run();
  });

  it('conta nova começa no degrau 1 (50/dia)', () => {
    assert.equal(warmup.dailyLimit('w1', 1_000), 50);
    assert.equal(warmup.sentToday('w1'), 0);
    assert.equal(warmup.hasDailyBudget('w1', 1_000), true);
  });

  it('avança na rampa conforme os dias passam', () => {
    // Primeiro envio há 3 dias → degrau 4 (350).
    const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);
    dbmod.db
      .prepare('INSERT INTO send_counters (account_id, day, sent_count) VALUES (?, ?, 1)')
      .run('w2', daysAgo(3));
    assert.equal(warmup.dailyLimit('w2', 1_000), 350);
    assert.equal(warmup.warmupDayNumber('w2'), 3);
  });

  it('após o dia 7 usa o cap pleno', () => {
    const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);
    dbmod.db
      .prepare('INSERT INTO send_counters (account_id, day, sent_count) VALUES (?, ?, 1)')
      .run('w3', daysAgo(10));
    assert.equal(warmup.dailyLimit('w3', 1_000), 1_000);
  });

  it('respeita o orçamento diário consumido', () => {
    for (let i = 0; i < 50; i++) warmup.recordSent('w4');
    assert.equal(warmup.sentToday('w4'), 50);
    assert.equal(warmup.hasDailyBudget('w4', 1_000), false);
  });
});

// ── Quiet hours ──────────────────────────────────────────

describe('quiet-hours', () => {
  // Janela padrão: 22:00 → 07:00 (end exclusive).
  it('bloqueia durante a noite', () => {
    assert.equal(isQuietHour(new Date(2026, 8, 6, 23, 0)), true);
    assert.equal(isQuietHour(new Date(2026, 8, 6, 3, 30)), true);
  });

  it('permite durante o dia', () => {
    assert.equal(isQuietHour(new Date(2026, 8, 6, 8, 0)), false);
    assert.equal(isQuietHour(new Date(2026, 8, 6, 12, 0)), false);
  });

  it('limites exatos: 22:00 bloqueia, 07:00 libera', () => {
    assert.equal(isQuietHour(new Date(2026, 8, 6, 22, 0)), true);
    assert.equal(isQuietHour(new Date(2026, 8, 6, 7, 0)), false);
  });

  it('nextAllowedTime aponta para as 07:00', () => {
    const at23 = new Date(2026, 8, 6, 23, 0);
    const next = new Date(nextAllowedTime(at23));
    assert.equal(next.getHours(), 7);
    assert.equal(next.getDate(), 7); // dia seguinte
  });
});

// ── Gaussian pacing ──────────────────────────────────────

describe('gaussian pacing', () => {
  it('média converge para o valor esperado', () => {
    const n = 20_000;
    let sum = 0;
    for (let i = 0; i < n; i++) sum += gaussianRandom(3_000, 1_000);
    const mean = sum / n;
    assert.ok(Math.abs(mean - 3_000) < 100, `média ${mean} fora da tolerância`);
  });

  it('delay respeita o piso configurado', () => {
    for (let i = 0; i < 1_000; i++) {
      const d = gaussianDelayMs(100, 50, 500);
      assert.ok(d >= 500, `delay ${d} abaixo do piso`);
    }
  });

  it('stdev 0 degrada para a média', () => {
    assert.equal(gaussianRandom(3_000, 0), 3_000);
  });
});
