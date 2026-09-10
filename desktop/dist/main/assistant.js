// @ts-nocheck
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * AssistantEngine — assistente WhatsApp do GasFlow Desktop.
 *
 * Loop: backend (/whatsapp/conversations) → novas mensagens INCOMING →
 * Ollama (classifica intenção + gera resposta) → WhatsAppBridge.sendMessage.
 *
 * O backend também tem pipeline de IA em /whatsapp/incoming — por isso o
 * auto-reply é opt-in (settings.waAutoReply) e só responde a mensagem cuja
 * conversa está no estado AI_ACTIVE (sem operador humano assumido).
 * Sugestões manuais ("Sugerir resposta da IA") não dependem desse gate.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.AssistantEngine = void 0;
const logger_1 = require("./logger");
const CLASSIFY_PROMPT = "Você classifica mensagens de clientes de uma revenda de gás e água. " +
    "Responda APENAS um JSON: {\"intent\":\"order|status|sync|greeting|other\"," +
    "\"confidence\":0.0,\"reason\":\"...\"}. " +
    'Significados: "order" = cliente quer fazer/pedir algo (compra, agendamento); ' +
    '"status" = pergunta sobre andamento de pedido; "sync" = pedido para sincronizar ' +
    "o site; \"greeting\" = saudação; \"other\" = qualquer outra coisa.";
const REPLY_PROMPT = "Você é o assistente de vendas de uma revenda de gás e água. Responda de forma " +
    "curta, simpática e útil em português do Brasil, usando as informações da " +
    "conversa. Não invente preços ou prazos: se não souber, diga que vai confirmar. " +
    "Não use markdown. Responda apenas com o texto da mensagem.";
class AssistantEngine {
    deps;
    timer = null;
    seen = new Set();
    busy = false;
    constructor(deps) {
        this.deps = deps;
    }
    start() {
        if (this.timer)
            return;
        const interval = this.deps.pollIntervalMs ?? 8000;
        this.timer = setInterval(() => {
            void this.tick();
        }, interval);
        this.timer.unref?.();
    }
    stop() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }
    msgKey(convId, msgId) {
        return `${convId}:${msgId}`;
    }
    /** Roda uma varredura (pública para testes). */
    async tick() {
        if (this.busy)
            return;
        this.busy = true;
        try {
            const { conversations } = await this.deps.client.listConversations(20, 0);
            for (const conv of conversations) {
                // Auto-reply só em conversas com a IA ativa (sem takeover humano).
                if (!this.deps.autoReply() || conv.state === "HUMAN_ACTIVE")
                    continue;
                const detail = await this.deps.client.getConversation(conv.id);
                const lastIncoming = [...detail.messages].reverse().find((m) => m.direction === "INCOMING");
                if (!lastIncoming)
                    continue;
                const key = this.msgKey(conv.id, lastIncoming.id);
                if (this.seen.has(key))
                    continue;
                this.seen.add(key);
                await this.handleNewMessage(detail, lastIncoming);
            }
        }
        catch (e) {
            logger_1.logger.warn("assistant", `varredura falhou: ${e.message}`);
        }
        finally {
            this.busy = false;
        }
    }
    async handleNewMessage(detail, msg) {
        const intent = await this.classify(msg.content);
        logger_1.logger.info("assistant", `mensagem de ${detail.customer_phone}: intenção=${intent.intent} (${intent.reason})`);
        const reply = await this.deps.chat(msg.content, {
            system: `${REPLY_PROMPT}\nIntenção detectada: ${intent.intent}.`,
        });
        if (reply.error || !reply.content.trim()) {
            logger_1.logger.warn("assistant", `IA não gerou resposta: ${reply.error ?? "vazia"}`);
            return;
        }
        const sent = await this.deps.bridge.sendMessage(detail.account_id, detail.customer_phone, reply.content.trim());
        if (sent.success) {
            logger_1.logger.info("assistant", `resposta enviada para ${detail.customer_phone}`);
        }
        else {
            logger_1.logger.error("assistant", `falha ao enviar resposta: ${sent.error}`);
        }
    }
    /** Classifica a intenção via Ollama, com fallback heurístico se IA falhar. */
    async classify(text) {
        const heuristic = this.classifyHeuristic(text);
        const result = await this.deps.chat(text, { system: CLASSIFY_PROMPT });
        if (result.error)
            return heuristic;
        try {
            const parsed = JSON.parse(result.content);
            const valid = ["order", "status", "sync", "greeting", "other"];
            if (valid.includes(parsed.intent)) {
                return {
                    intent: parsed.intent,
                    confidence: Number(parsed.confidence) || 0.5,
                    reason: parsed.reason ?? "ia",
                };
            }
        }
        catch {
            /* JSON inválido → heurística */
        }
        return heuristic;
    }
    /** Classificador local (sem rede) — usado como fallback e em testes. */
    classifyHeuristic(text) {
        const t = text.toLowerCase();
        if (/(bom dia|boa tarde|boa noite|ol[áa]|oi|tudo bem)/.test(t) && t.length < 60) {
            return { intent: "greeting", confidence: 0.7, reason: "heurística: saudação curta" };
        }
        if (/(sincroniz|sync|atualiza r o site|atualizar o site)/.test(t)) {
            return { intent: "sync", confidence: 0.8, reason: "heurística: pedido de sincronização" };
        }
        if (/(andamento|status|saiu para entrega|chegou|entregue)/.test(t)) {
            return { intent: "status", confidence: 0.7, reason: "heurística: consulta de status" };
        }
        if (/(quero|preciso|manda|traz|pedir|pedido|botij|água|agua|galão|galao|g[áa]s)/.test(t)) {
            return { intent: "order", confidence: 0.6, reason: "heurística: palavras de pedido" };
        }
        return { intent: "other", confidence: 0.3, reason: "heurística: sem palavras-chave" };
    }
    /** Sugestão de resposta baseada no histórico (usada pelo botão da UI). */
    async suggestReply(detail) {
        const history = detail.messages
            .slice(-12)
            .map((m) => `${m.direction === "INCOMING" ? "Cliente" : "Atendente"}: ${m.content}`)
            .join("\n");
        const result = await this.deps.chat(`Histórico da conversa com ${detail.customer_phone}:\n${history}\n\nEscreva a próxima resposta do atendente.`, { system: REPLY_PROMPT });
        if (result.error)
            throw new Error(result.error);
        return result.content.trim();
    }
}
exports.AssistantEngine = AssistantEngine;
//# sourceMappingURL=assistant.js.map
