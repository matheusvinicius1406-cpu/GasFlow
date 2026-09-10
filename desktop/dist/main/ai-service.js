"use strict";
/**
 * Serviço de IA local (Ollama) — extração multimodal de pedidos.
 *
 * Mesmas convenções do backend (app/infrastructure/ai/ollama_provider.py):
 * POST /api/chat com stream:false e options.temperature/num_predict.
 * Extrações:
 *   - HTML complexo que as heurísticas do detector não resolvem;
 *   - print de tela da página de pedidos (modelo vision);
 *   - texto transcrito de áudio de WhatsApp (via whisper, transcriber.ts).
 *
 * O modelo sempre devolve JSON {"orders":[...]}; aqui parseamos de forma
 * defensiva (o modelo pode colocar fences/texto em volta) e normalizamos
 * para o formato NormalizedOrder aceito pelo backend.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.AiService = void 0;
exports.extractJsonBlock = extractJsonBlock;
exports.parseMoney = parseMoney;
exports.coerceOrder = coerceOrder;
exports.parseOrdersJson = parseOrdersJson;
const SYSTEM_PROMPT = "Você é um extrator de pedidos para uma revenda de gás e água. " +
    "Receba conteúdo (HTML, imagem ou texto) e devolva APENAS um JSON válido, " +
    'sem texto adicional, no formato: {"orders":[{"external_id":"","client_name":"",' +
    '"client_phone":"","client_email":"","address":"","items":[{"product_name":"",' +
    '"quantity":1,"unit_price":0}],"total":0,"delivery_fee":0,"payment_method":"",' +
    '"status":"","notes":""}]}. ' +
    "Use null em campos ausentes, quantity como inteiro ≥ 1 e valores monetários " +
    "como número (pt-BR: vírgula é decimal). Não invente pedidos: só extraia o que " +
    "estiver explícito no conteúdo.";
/** HTML grande estoura o contexto do modelo local — corta com aviso. */
const MAX_HTML_CHARS = 120_000;
class AiService {
    baseUrl;
    textModel;
    visionModel;
    timeoutMs;
    fetchFn;
    constructor(deps) {
        this.baseUrl = deps.baseUrl.replace(/\/+$/, "");
        this.textModel = deps.textModel;
        this.visionModel = deps.visionModel;
        this.timeoutMs = deps.timeoutMs ?? 180_000; // modelos locais são lentos
        this.fetchFn = deps.fetchFn ?? fetch;
    }
    /** GET /api/tags — lista modelos instalados (usado na tela de settings). */
    async listModels() {
        try {
            const res = await this.fetchFn(`${this.baseUrl}/api/tags`);
            if (!res.ok)
                return { ok: false, models: [], error: `HTTP ${res.status}` };
            const body = (await res.json());
            const models = (body.models ?? []).map((m) => m.name ?? "").filter(Boolean);
            return { ok: true, models };
        }
        catch (e) {
            return { ok: false, models: [], error: `Ollama indisponível em ${this.baseUrl}: ${e.message}` };
        }
    }
    /** POST /api/chat — uma chamada genérica (o backend usa o mesmo endpoint). */
    async chat(prompt, opts = {}) {
        const model = opts.model ?? this.textModel;
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeoutMs);
        try {
            const res = await this.fetchFn(`${this.baseUrl}/api/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                signal: controller.signal,
                body: JSON.stringify({
                    model,
                    stream: false,
                    format: "json",
                    messages: [
                        { role: "system", content: opts.system ?? SYSTEM_PROMPT },
                        { role: "user", content: prompt, ...(opts.images?.length ? { images: opts.images } : {}) },
                    ],
                    options: {
                        temperature: opts.temperature ?? 0.1,
                        num_predict: opts.numPredict ?? 4096,
                    },
                }),
            });
            if (!res.ok) {
                const detail = await res.text().catch(() => "");
                return { content: "", error: `Ollama HTTP ${res.status}: ${detail.slice(0, 300)}` };
            }
            const body = (await res.json());
            if (body.error)
                return { content: "", error: `Ollama: ${body.error}` };
            return { content: body.message?.content ?? "" };
        }
        catch (e) {
            const msg = e.name === "AbortError" ? "timeout aguardando o modelo" : e.message;
            return { content: "", error: `Ollama indisponível ou lento (${msg})` };
        }
        finally {
            clearTimeout(timer);
        }
    }
    /** Extração a partir de HTML (modelo de texto). */
    async extractFromHtml(html, model) {
        const trimmed = html.length > MAX_HTML_CHARS
            ? `${html.slice(0, MAX_HTML_CHARS)}\n<!-- HTML truncado para caber no contexto do modelo -->`
            : html;
        const prompt = "Extraia todos os pedidos do HTML abaixo (página de pedidos de uma revenda). " +
            "Ignore menus, navegação e rodapé.\n\n```html\n" + trimmed + "\n```";
        return this.run(prompt, { model: model ?? this.textModel }, "html");
    }
    /** Extração a partir de imagem (print de tela) — exige modelo vision. */
    async extractFromImage(base64, model) {
        const chosen = model ?? this.visionModel;
        if (!chosen) {
            return errResult("Nenhum modelo de visão configurado. Instale um em Settings/modelos ou rode: ollama pull llama3.2-vision", "image");
        }
        const prompt = "Esta imagem é um print da página de pedidos de uma revenda (tabela ou lista). " +
            "Extraia todos os pedidos visíveis.";
        return this.run(prompt, { model: chosen, images: [base64] }, "image");
    }
    /** Extração a partir de texto livre (ex.: transcrição de áudio de WhatsApp). */
    async extractFromText(text, model) {
        const prompt = "O texto abaixo é a transcrição de uma mensagem de voz de um cliente fazendo um pedido " +
            "(pode citar produtos, quantidades, endereço e forma de pagamento de forma informal). " +
            "Extraia o pedido; se não houver external_id, use null (o backend gera).\n\n```\n" +
            text.slice(0, 20_000) + "\n```";
        return this.run(prompt, { model: model ?? this.textModel }, "audio");
    }
    async run(prompt, opts, source) {
        const result = await this.chat(prompt, opts);
        if (result.error) {
            return { orders: [], errors: [{ message: result.error }], model: opts.model ?? this.textModel, source };
        }
        const { orders, errors } = parseOrdersJson(result.content);
        return { orders, errors, model: opts.model ?? this.textModel, source };
    }
}
exports.AiService = AiService;
function errResult(message, source) {
    return { orders: [], errors: [{ message }], model: "", source };
}
/** Remove fences ```json e devolve o primeiro objeto/array JSON balanceado. */
function extractJsonBlock(raw) {
    let text = raw.trim();
    const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
    if (fence)
        text = fence[1].trim();
    const start = text.search(/[[{]/);
    if (start === -1)
        return null;
    const open = text[start];
    const close = open === "{" ? "}" : "]";
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let i = start; i < text.length; i++) {
        const ch = text[i];
        if (inString) {
            if (escaped)
                escaped = false;
            else if (ch === "\\")
                escaped = true;
            else if (ch === '"')
                inString = false;
            continue;
        }
        if (ch === '"')
            inString = true;
        else if (ch === open)
            depth++;
        else if (ch === close) {
            depth--;
            if (depth === 0)
                return text.slice(start, i + 1);
        }
    }
    return null;
}
/** parseMoney pt-BR — mesmo comportamento do normalizer do agente. */
function parseMoney(value) {
    if (typeof value === "number")
        return Number.isFinite(value) ? value : null;
    if (value === null || value === undefined)
        return null;
    let text = String(value).trim();
    if (!text)
        return null;
    text = text.replace(/[^\d,.]/g, "");
    if (!text)
        return null;
    if (text.includes(",") && text.includes(".")) {
        if (text.lastIndexOf(",") > text.lastIndexOf("."))
            text = text.replace(/\./g, "").replace(",", ".");
        else
            text = text.replace(/,/g, "");
    }
    else if (text.includes(",")) {
        text = text.replace(",", ".");
    }
    const n = Number.parseFloat(text);
    return Number.isFinite(n) ? n : null;
}
function toInt(value, fallback) {
    const n = typeof value === "number" ? value : Number.parseInt(String(value ?? ""), 10);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}
function strOrNull(value) {
    if (value === null || value === undefined)
        return "";
    const s = String(value).trim();
    return s.toLowerCase() === "null" ? "" : s;
}
/** Aceita aliases comuns que os modelos costumam devolver. */
function pick(obj, keys) {
    for (const k of keys) {
        if (obj[k] !== undefined && obj[k] !== null)
            return obj[k];
    }
    return undefined;
}
function hash(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++)
        h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
    return h;
}
/** Coerção de um pedido "solto" do modelo → NormalizedOrder (ou erro controlado). */
function coerceOrder(raw, index) {
    if (typeof raw !== "object" || raw === null) {
        return { error: { message: `pedido #${index}: formato inesperado (${typeof raw})` } };
    }
    const obj = raw;
    const itemsRaw = pick(obj, ["items", "itens", "products", "produtos"]);
    const items = [];
    if (Array.isArray(itemsRaw)) {
        itemsRaw.forEach((it, i) => {
            if (typeof it !== "object" || it === null)
                return;
            const o = it;
            const name = strOrNull(pick(o, ["product_name", "nome", "produto", "name", "item"]));
            if (!name)
                return;
            items.push({
                product_name: name,
                quantity: toInt(pick(o, ["quantity", "quantidade", "qtd", "qty"]), 1),
                unit_price: parseMoney(pick(o, ["unit_price", "preco_unitario", "price", "valor_unitario"])),
            });
        });
    }
    if (items.length === 0) {
        // modelo às vezes coloca produto direto no pedido
        const single = strOrNull(pick(obj, ["product", "produto", "item"]));
        if (single)
            items.push({ product_name: single, quantity: toInt(pick(obj, ["quantity", "quantidade", "qtd"]), 1) });
    }
    if (items.length === 0) {
        return { error: { message: `pedido #${index}: sem itens reconhecíveis` } };
    }
    const externalId = strOrNull(pick(obj, ["external_id", "id", "pedido", "numero", "order_id"]));
    const clientName = strOrNull(pick(obj, ["client_name", "cliente", "nome", "client"]));
    if (!externalId && !clientName) {
        return { error: { message: `pedido #${index}: sem external_id nem client_name` } };
    }
    const total = parseMoney(pick(obj, ["total", "valor", "valor_total", "amount"]));
    const fingerprint = `${externalId}|${clientName}|${items.map((i) => `${i.quantity}x${i.product_name}`).join(",")}`;
    return {
        order: {
            external_id: externalId || `ai-${Math.abs(hash(fingerprint))}`,
            client_name: clientName,
            client_phone: strOrNull(pick(obj, ["client_phone", "telefone", "phone", "whatsapp"])),
            client_email: strOrNull(pick(obj, ["client_email", "email"])).includes("@")
                ? strOrNull(pick(obj, ["client_email", "email"]))
                : "",
            address: strOrNull(pick(obj, ["address", "endereco", "entrega"])),
            items,
            total,
            delivery_fee: parseMoney(pick(obj, ["delivery_fee", "frete", "entrega_taxa"])),
            payment_method: strOrNull(pick(obj, ["payment_method", "pagamento", "forma_pagamento"])) || null,
            status: strOrNull(pick(obj, ["status", "situacao"])),
            notes: "extraído via IA local (Ollama) no GasFlow Desktop",
        },
    };
}
/** Parse defensivo da resposta do modelo → pedidos + erros. */
function parseOrdersJson(raw) {
    const orders = [];
    const errors = [];
    const block = extractJsonBlock(raw);
    if (!block) {
        return { orders, errors: [{ message: `modelo não devolveu JSON reconhecível: "${raw.slice(0, 200)}"` }] };
    }
    let parsed;
    try {
        parsed = JSON.parse(block);
    }
    catch (e) {
        return { orders, errors: [{ message: `JSON inválido do modelo: ${e.message}` }] };
    }
    const list = Array.isArray(parsed)
        ? parsed
        : typeof parsed === "object" && parsed !== null && Array.isArray(parsed.orders)
            ? parsed.orders
            : null;
    if (!list) {
        return { orders, errors: [{ message: 'JSON do modelo não contém "orders" (array)' }] };
    }
    list.forEach((entry, i) => {
        const res = coerceOrder(entry, i);
        if (res.order)
            orders.push(res.order);
        else if (res.error)
            errors.push(res.error);
    });
    return { orders, errors };
}
//# sourceMappingURL=ai-service.js.map
