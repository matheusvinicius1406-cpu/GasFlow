/**
 * Testes da URL do servidor (frente MOBILE-P0 / Home Server).
 *
 * O Home Server publica o backend atrás do nginx na porta 80 (raiz: /auth/*,
 * /driver/*, /ws) — sem `:8000`. O normalizeServerUrl precisa aceitar
 * `http://IP_DO_SERVIDOR` (sem porta), `https://` para o futuro acesso
 * externo, e rejeitar entradas quebradas.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { normalizeServerUrl } from "../src/logic/serverConfig.ts";

test("URL do Home Server (porta 80, sem :8000) é aceita", () => {
  assert.equal(normalizeServerUrl("http://192.168.0.10"), "http://192.168.0.10");
});

test("HTTPS é aceito (futuro acesso externo)", () => {
  assert.equal(normalizeServerUrl("https://gasflow.exemplo.com.br"), "https://gasflow.exemplo.com.br");
});

test("barra final e espaços são normalizados", () => {
  assert.equal(normalizeServerUrl("  http://192.168.0.10/  "), "http://192.168.0.10");
});

test("emulador com :8000 continua aceito (dev)", () => {
  assert.equal(normalizeServerUrl("http://10.0.2.2:8000"), "http://10.0.2.2:8000");
});

test("entradas quebradas viram null (tela mostra o formato correto)", () => {
  for (const bad of ["", "   ", "192.168.0.10", "ftp://x", "http://", "http:// tem espaço"]) {
    assert.equal(normalizeServerUrl(bad), null, `entrada inválida aceita: ${bad}`);
  }
});
