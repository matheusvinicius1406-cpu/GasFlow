/**
 * Broadcast Worker — processes campaign message queue.
 *
 * Each campaign recipient is a discrete job. The worker polls for PENDING
 * recipients, claims them atomically, sends via the provider, and records
 * the result. Supports pause/cancel via campaign status checks.
 *
 * Patterns adapted from mature projects (no code copied):
 * - Atomic claim (SELECT ... FOR UPDATE pattern via UPDATE WHERE status = 'PENDING')
 * - Cooldown between sends (rate-limiting pattern used by WAHA and WPPConnect)
 * - Protection mode on abnormal failure rate (inspired by Evolution API safety)
 *
 * Anti-ban hygiene (src/anti-ban): caps por minuto/hora/dia, warmup progressivo,
 * cooldown por destinatário, quiet hours e pacing gaussiano.
 */

import { db, claimNextRecipient, getCampaignById, getCustomerWithContact, getPreference, markRecipientFailed, markRecipientSent, recoverStaleProcessing, updateCampaignStatus, setCampaignProtection } from './db';
import { providerManager } from './provider/provider-manager';
import { checkRate, recordSend, hasDailyBudget, recordSent, isQuietHour, nextAllowedTime, gaussianDelayMs } from './anti-ban';
import { logger } from './log';

// Pacing gaussiano: média 3s, desvio 1s (env WA_SEND_MEAN_MS / WA_SEND_STDEV_MS).
// WA_SEND_MIN/MAX_INTERVAL_MS continuam válidos como piso/teto para compatibilidade.
const SEND_MIN_INTERVAL_MS = Number(process.env.WA_SEND_MIN_INTERVAL_MS || 2_000);
const SEND_MAX_INTERVAL_MS = Number(process.env.WA_SEND_MAX_INTERVAL_MS || 10_000);
const SEND_MEAN_MS = Number(process.env.WA_SEND_MEAN_MS || 3_000);
const SEND_STDEV_MS = Number(process.env.WA_SEND_STDEV_MS || 1_000);
const PROTECTION_FAILURE_THRESHOLD = 5; // consecutive failures to trigger protection mode
const PROTECTION_RATE_THRESHOLD = 0.5; // 50% failure rate triggers protection
// Cap diário pleno (pós-warmup). Durante o warmup o limite é a rampa 50→1000.
const DAILY_CAP = Math.max(1, Number(process.env.WA_DAILY_CAP || 1_000));
// Kill-switch: com o Cloud API no ar para campanhas, defina WA_BROADCAST_ENABLED=false
// para reservar este serviço ao tráfego conversacional (incoming.ts).
const BROADCAST_ENABLED = process.env.WA_BROADCAST_ENABLED !== 'false';

function nextSendIntervalMs(): number {
  const floor = Math.max(500, SEND_MIN_INTERVAL_MS);
  const ceiling = Math.max(floor, SEND_MAX_INTERVAL_MS);
  return Math.min(gaussianDelayMs(SEND_MEAN_MS, SEND_STDEV_MS, floor), ceiling);
}

let workerRunning = false;
let workerTimer: NodeJS.Timeout | null = null;
/** Pausa o worker até este timestamp (rate limit/quiet hours) antes do próximo ciclo. */
let pausedUntilMs = 0;

export function startWorker(): void {
  if (!BROADCAST_ENABLED) {
    logger.info('broadcast.disabled');
    return;
  }
  if (workerRunning) return;
  workerRunning = true;
  // Recover stale PROCESSING jobs from previous run
  const recovered = recoverStaleProcessing();
  if (recovered > 0) {
    logger.info('broadcast.stale_jobs_recovered', { recovered });
  }
  logger.info('broadcast.started');
  scheduleNext();
}

export function stopWorker(): void {
  workerRunning = false;
  if (workerTimer) {
    clearTimeout(workerTimer);
    workerTimer = null;
  }
  logger.info('broadcast.stopped');
}

function scheduleNext(delayMs?: number): void {
  if (!workerRunning) return;
  const base = Math.max(0, delayMs ?? nextSendIntervalMs());
  const wait = Math.max(base, pausedUntilMs - Date.now());
  pausedUntilMs = 0;
  workerTimer = setTimeout(() => {
    void processNext().then(() => scheduleNext());
  }, wait);
}

/** Pausa o worker até `untilMs` (teto de 10 min para reavaliar estado). */
function pauseWorkerUntil(untilMs: number, reason: string): void {
  const capped = Math.min(untilMs, Date.now() + 10 * 60_000);
  pausedUntilMs = Math.max(pausedUntilMs, capped);
  logger.info('broadcast.paused', { until: new Date(capped).toISOString(), reason });
}

async function processNext(): Promise<void> {
  // Find the first RUNNING campaign
  const campaigns = db
    .prepare("SELECT id FROM campaigns WHERE status = 'RUNNING'")
    .all() as Array<{ id: number }>;

  if (campaigns.length === 0) return;

  for (const { id: campaignId } of campaigns) {
    // Check campaign is still running
    const campaign = getCampaignById(campaignId);
    if (!campaign || campaign.status !== 'RUNNING') continue;

    // Check if provider is connected
    if (!providerManager.getAccount("primary")?.isConnected()) {
      logger.warn('broadcast.account_not_connected');
      return;
    }

    // ── Anti-ban gates (nível conta) ──
    if (isQuietHour()) {
      pauseWorkerUntil(nextAllowedTime(), 'quiet hours');
      return;
    }
    if (!hasDailyBudget('primary', DAILY_CAP)) {
      // Reavalia à meia-noite UTC (teto de 10 min mantém o loop responsivo).
      pauseWorkerUntil(Date.now() + 10 * 60_000, 'daily cap atingido (warmup/cap)');
      return;
    }

    // Claim next pending recipient
    const recipient = claimNextRecipient(campaignId);
    if (!recipient) {
      // No more pending recipients — campaign complete
      logger.info('broadcast.campaign_completed', { campaignId });
      updateCampaignStatus(campaignId, 'COMPLETED');
      continue;
    }

    // === Eligibility chain ===
    // 1. Customer exists?
    const customer = getCustomerWithContact(recipient.customer_id);
    if (!customer) {
      markRecipientFailed(campaignId, recipient.customer_id, 'Customer not found');
      continue;
    }

    // 2. Contact exists?
    if (!customer.contact) {
      markRecipientFailed(campaignId, recipient.customer_id, 'Contact not found for customer');
      continue;
    }

    // 3. Phone valid?
    const phone = customer.contact.phone ?? customer.contact.jid?.split('@')[0] ?? null;
    if (!phone || phone.length < 8) {
      markRecipientFailed(campaignId, recipient.customer_id, 'No valid phone number');
      continue;
    }

    // 4. OPTED_OUT / SUPPRESSED / BLOCKED?
    const pref = getPreference(recipient.customer_id);
    if (pref) {
      if (pref.marketing_status === 'OPTED_OUT' || pref.marketing_status === 'SUPPRESSED' || pref.marketing_status === 'BLOCKED') {
        markRecipientFailed(campaignId, recipient.customer_id, `Excluded: ${pref.marketing_status}`);
        continue;
      }
    }

    // 5. Already processed? (atomic claim already ensures PENDING only)
    // The claimNextRecipient only returns PENDING jobs, so this is guaranteed.

    // 6. Rate limits (minuto/hora) + cooldown por destinatário.
    const rate = checkRate('primary', phone);
    if (!rate.allowed) {
      // Devolve o job para a fila e pausa o worker até o limite abrir.
      unclaimRecipient(campaignId, recipient.customer_id);
      pauseWorkerUntil(rate.retryAtMs ?? Date.now() + 60_000, `rate limit: ${rate.reason}`);
      return;
    }

    // Send message via provider
    try {
      logger.info('broadcast.message_sending', { phone, campaignId, customerId: recipient.customer_id });

      const result = await providerManager.getAccount("primary")?.sendMessage(phone, { text: campaign.message }) || { success: false, error: "Primary account not found" };

      if (result.success) {
        markRecipientSent(campaignId, recipient.customer_id, result.messageId ?? 'unknown');
        // Registra nas janelas de rate limit (minuto/hora/cooldown) e no contador de warmup.
        recordSend('primary', phone, result.messageId);
        recordSent('primary');
        logger.info('broadcast.message_sent', { phone, campaignId, customerId: recipient.customer_id });
      } else {
        markRecipientFailed(campaignId, recipient.customer_id, result.error ?? 'Unknown error');
        logger.warn('broadcast.message_failed', { phone, campaignId, error: result.error });

        // Check protection mode
        if (shouldActivateProtection(campaignId)) {
          logger.error('broadcast.protection_mode', { campaignId });
          setCampaignProtection(campaignId, 'Too many consecutive failures');
          updateCampaignStatus(campaignId, 'FAILED');
          return;
        }
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      markRecipientFailed(campaignId, recipient.customer_id, errorMsg);
      logger.error('broadcast.message_error', { phone, campaignId, error: errorMsg });

      if (shouldActivateProtection(campaignId)) {
        logger.error('broadcast.protection_mode', { campaignId });
        setCampaignProtection(campaignId, 'Too many consecutive failures');
        updateCampaignStatus(campaignId, 'FAILED');
        return;
      }
    }

    // Only process one message per cycle to respect cooldown
    return;
  }
}

/** Devolve um job PROCESSING para PENDING (usado quando o rate limit bloqueia o envio). */
function unclaimRecipient(campaignId: number, customerId: number): void {
  db.prepare(
    `UPDATE campaign_recipients
     SET status = 'PENDING', lease_until = NULL, started_at = NULL
     WHERE campaign_id = ? AND customer_id = ?`,
  ).run(campaignId, customerId);
}

function shouldActivateProtection(campaignId: number): boolean {
  const results = db
    .prepare(
      `SELECT
         COUNT(*) AS total,
         SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
         SUM(CASE WHEN status = 'SENT' THEN 1 ELSE 0 END) AS sent
       FROM campaign_recipients WHERE campaign_id = ?`,
    )
    .get(campaignId) as { total: number; failed: number; sent: number } | undefined;

  if (!results || results.total === 0) return false;

  const failedCount = Number(results.failed ?? 0);
  const totalCount = Number(results.total ?? 0);

  // Protection on consecutive failures (check last N outcomes)
  if (failedCount >= PROTECTION_FAILURE_THRESHOLD) {
    const recentFailures = db
      .prepare(
        `SELECT COUNT(*) AS cnt FROM (
           SELECT status FROM campaign_recipients
           WHERE campaign_id = ? AND status IN ('FAILED', 'SENT')
           ORDER BY created_at DESC LIMIT ?
         ) WHERE status = 'FAILED'`,
      )
      .get(campaignId, PROTECTION_FAILURE_THRESHOLD) as { cnt: number } | undefined;

    if (Number(recentFailures?.cnt ?? 0) >= PROTECTION_FAILURE_THRESHOLD) {
      return true;
    }
  }

  // Protection on high failure rate (only after enough data)
  if (totalCount >= 10) {
    const failureRate = failedCount / totalCount;
    if (failureRate >= PROTECTION_RATE_THRESHOLD) {
      return true;
    }
  }

  return false;
}
