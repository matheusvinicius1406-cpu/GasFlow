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

import {
  db,
  claimNextRecipient,
  getCampaignById,
  getCustomerWithContact,
  getPreference,
  markRecipientCancelled,
  markRecipientFailed,
  markRecipientSent,
  recoverStaleProcessing,
  releaseRecipientClaim,
  updateCampaignStatus,
  setCampaignProtection,
} from './db';
import { jidUser, normalizePhone } from './normalize';
import { whatsappProvider } from './provider/wwebjs-provider';

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

/** Exportado para testes: executa um ciclo da fila (drain + 1 envio). */
export async function processNext(): Promise<void> {
  // Find the first RUNNING campaign
  const campaigns = db
    .prepare("SELECT id FROM campaigns WHERE status = 'RUNNING'")
    .all() as Array<{ id: number }>;

  if (campaigns.length === 0) return;

  for (const { id: campaignId } of campaigns) {
    // Check campaign is still running
    const campaign = getCampaignById(campaignId);
    if (!campaign || campaign.status !== 'RUNNING') continue;

    let offlineWarned = false;

    // Drena destinatários não elegíveis sem esperar o cooldown (só envios
    // respeitam o intervalo de 2s). O claim marca PROCESSING, então o loop
    // sempre progride.
    for (;;) {
      const recipient = claimNextRecipient(campaignId);
      if (!recipient) {
        // No more pending recipients — campaign complete
        console.log(`[broadcast] Campanha ${campaignId} concluída — sem destinatários pendentes.`);
        updateCampaignStatus(campaignId, 'COMPLETED');
        break;
      }

      // Campanha pode ter sido pausada/cancelada enquanto drenávamos.
      if (getCampaignById(campaignId)?.status !== 'RUNNING') break;

      // === Eligibility chain ===
      // 1. Customer exists?
      const customer = getCustomerWithContact(recipient.customer_id);
      if (!customer) {
        markRecipientCancelled(campaignId, recipient.customer_id, 'Excluded: Customer not found');
        continue;
      }

      // 2. Contact exists?
      if (!customer.contact) {
        markRecipientCancelled(campaignId, recipient.customer_id, 'Excluded: Contact not found for customer');
        continue;
      }

      // 3. Phone valid? (só dígitos, 8+ — nunca enviar para fragmento de jid)
      const phone = normalizePhone(customer.contact.phone ?? jidUser(customer.contact.jid ?? ''));
      if (!phone) {
        markRecipientCancelled(campaignId, recipient.customer_id, 'Excluded: No valid phone number');
        continue;
      }

      // 4. OPTED_OUT / SUPPRESSED / BLOCKED?
      const pref = getPreference(recipient.customer_id);
      if (
        pref &&
        (pref.marketing_status === 'OPTED_OUT' ||
          pref.marketing_status === 'SUPPRESSED' ||
          pref.marketing_status === 'BLOCKED')
      ) {
        markRecipientCancelled(campaignId, recipient.customer_id, `Excluded: ${pref.marketing_status}`);
        continue;
      }

      // Elegível: só aqui o provider é necessário.
      if (!whatsappProvider.isConnected()) {
        releaseRecipientClaim(campaignId, recipient.customer_id);
        if (!offlineWarned) {
          console.warn('[broadcast] WhatsApp não conectado. Aguardando reconexão...');
          offlineWarned = true;
        }
        break;
      }

      await sendOne(campaignId, recipient.customer_id, phone, campaign.message);
      return;
    }
  }
}

async function sendOne(campaignId: number, customerId: number, phone: string, message: string): Promise<void> {
  try {
    console.log(`[broadcast] Enviando para ${phone} (campanha ${campaignId}, customer ${customerId})`);

    const result = await whatsappProvider.sendMessage(phone, { text: message });

    if (result.success) {
      markRecipientSent(campaignId, customerId, result.messageId ?? 'unknown');
      console.log(`[broadcast] Enviado com sucesso para ${phone}`);
    } else {
      markRecipientFailed(campaignId, customerId, result.error ?? 'Unknown error');
      console.warn(`[broadcast] Falha ao enviar para ${phone}: ${result.error}`);

      // Check protection mode
      if (shouldActivateProtection(campaignId)) {
        console.error(`[broadcast] PROTECTION_MODE ativado para campanha ${campaignId}`);
        setCampaignProtection(campaignId, 'Too many consecutive failures');
        updateCampaignStatus(campaignId, 'FAILED');
      }
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : 'Unknown error';
    markRecipientFailed(campaignId, customerId, errorMsg);
    console.error(`[broadcast] Erro ao enviar para ${phone}: ${errorMsg}`);

    if (shouldActivateProtection(campaignId)) {
      console.error(`[broadcast] PROTECTION_MODE ativado para campanha ${campaignId}`);
      setCampaignProtection(campaignId, 'Too many consecutive failures');
      updateCampaignStatus(campaignId, 'FAILED');
    }
  }
}

/** Exportado para testes: avalia a política de proteção da campanha. */
export function shouldActivateProtection(campaignId: number): boolean {
  // Apenas tentativas reais de envio contam: SENT/FAILED.
  // CANCELLED (não elegível) e PENDING/PROCESSING não devem distorcer a taxa.
  const results = db
    .prepare(
      `SELECT
         COUNT(*) AS total,
         SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
         SUM(CASE WHEN status = 'SENT' THEN 1 ELSE 0 END) AS sent
       FROM campaign_recipients
       WHERE campaign_id = ? AND status IN ('SENT', 'FAILED')`,
    )
    .get(campaignId) as { total: number; failed: number; sent: number } | undefined;

  if (!results || Number(results.total ?? 0) === 0) return false;

  const failedCount = Number(results.failed ?? 0);
  const totalCount = Number(results.total ?? 0);

  // Protection on consecutive failures (check last N outcomes)
  if (failedCount >= PROTECTION_FAILURE_THRESHOLD) {
    const recentFailures = db
      .prepare(
        `SELECT COUNT(*) AS cnt FROM (
           SELECT status FROM campaign_recipients
           WHERE campaign_id = ? AND status IN ('FAILED', 'SENT')
           ORDER BY COALESCE(completed_at, created_at) DESC LIMIT ?
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
