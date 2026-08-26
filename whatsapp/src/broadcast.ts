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
 */

import { db, claimNextRecipient, getCampaignById, getCustomerWithContact, getContactById, getPreference, markRecipientFailed, markRecipientSent, recoverStaleProcessing, updateCampaignStatus, setCampaignProtection } from './db';
import { providerManager } from './provider/provider-manager';

const SEND_INTERVAL_MS = 2_000; // 2 seconds between sends
const PROTECTION_FAILURE_THRESHOLD = 5; // consecutive failures to trigger protection mode
const PROTECTION_RATE_THRESHOLD = 0.5; // 50% failure rate triggers protection

let workerRunning = false;
let workerTimer: NodeJS.Timeout | null = null;

export function startWorker(): void {
  if (workerRunning) return;
  workerRunning = true;
  // Recover stale PROCESSING jobs from previous run
  const recovered = recoverStaleProcessing();
  if (recovered > 0) {
    console.log(`[broadcast] ${recovered} jobs PROCESSING expirados recuperados para PENDING.`);
  }
  console.log('[broadcast] Worker iniciado.');
  scheduleNext();
}

export function stopWorker(): void {
  workerRunning = false;
  if (workerTimer) {
    clearTimeout(workerTimer);
    workerTimer = null;
  }
  console.log('[broadcast] Worker parado.');
}

function scheduleNext(): void {
  if (!workerRunning) return;
  workerTimer = setTimeout(() => {
    void processNext().then(() => scheduleNext());
  }, SEND_INTERVAL_MS);
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
      console.warn('[broadcast] WhatsApp não conectado. Aguardando reconexão...');
      return;
    }

    // Claim next pending recipient
    const recipient = claimNextRecipient(campaignId);
    if (!recipient) {
      // No more pending recipients — campaign complete
      console.log(`[broadcast] Campanha ${campaignId} concluída — sem destinatários pendentes.`);
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

    // Send message via provider
    try {
      console.log(`[broadcast] Enviando para ${phone} (campanha ${campaignId}, customer ${recipient.customer_id})`);

      const result = await providerManager.getAccount("primary")?.sendMessage(phone, { text: campaign.message }) || { success: false, error: "Primary account not found" };

      if (result.success) {
        markRecipientSent(campaignId, recipient.customer_id, result.messageId ?? 'unknown');
        console.log(`[broadcast] Enviado com sucesso para ${phone}`);
      } else {
        markRecipientFailed(campaignId, recipient.customer_id, result.error ?? 'Unknown error');
        console.warn(`[broadcast] Falha ao enviar para ${phone}: ${result.error}`);

        // Check protection mode
        if (shouldActivateProtection(campaignId)) {
          console.error(`[broadcast] PROTECTION_MODE ativado para campanha ${campaignId}`);
          setCampaignProtection(campaignId, 'Too many consecutive failures');
          updateCampaignStatus(campaignId, 'FAILED');
          return;
        }
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      markRecipientFailed(campaignId, recipient.customer_id, errorMsg);
      console.error(`[broadcast] Erro ao enviar para ${phone}: ${errorMsg}`);

      if (shouldActivateProtection(campaignId)) {
        console.error(`[broadcast] PROTECTION_MODE ativado para campanha ${campaignId}`);
        setCampaignProtection(campaignId, 'Too many consecutive failures');
        updateCampaignStatus(campaignId, 'FAILED');
        return;
      }
    }

    // Only process one message per cycle to respect cooldown
    return;
  }
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
