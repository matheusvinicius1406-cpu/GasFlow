"use strict";
/**
 * Harness de evidência — gera o PDF da Central Financeira pelo printToPDF REAL.
 *
 * Entra como `main` do Electron (`electron <este arquivo>`) e só então carrega
 * `dist/main/index.js`, o app de verdade: mesma preload, mesmo handler
 * `reports:export-pdf`, mesma barreira de permissão (finance.export_pdf).
 *
 * O que o harness ajusta (e só isso):
 *   1. userData isolado em %TEMP%\gasflow-evidence-userdata — o app real do
 *      usuário (settings.json, gasflow.db, sessão do WhatsApp) não é tocado e
 *      o lock de instância única não conflita;
 *   2. settings.json do isolado aponta para o stack E2E em :8080 (mesmo
 *      frontend/API com dado real das evidências) e desliga WhatsApp e
 *      impressora para não subir serviço nenhum;
 *   3. o gate de permissão IPC consulta o backend do stack (:8080) — em
 *      produção ele fixa 127.0.0.1:8000, que é o backend local do app;
 *   4. diálogo nativo (consentimento da IA local) não pode travar a
 *      automação: responde "Agora não" e registra a mensagem;
 *   5. shell.openPath não abre o visualizador de PDF — o caminho gravado fica
 *      em globalThis.__openedPdf para a captura.
 */
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { app, dialog, shell } = require("electron");

const STACK_URL = process.env.EVIDENCE_STACK_URL || "http://localhost:8080";
const USER_DATA = path.join(os.tmpdir(), "gasflow-evidence-userdata");

// 1 + 2 — userData isolado (apagado a cada run: estado determinístico de
// "primeira execução", sem sessão antiga nem settings do app real).
fs.rmSync(USER_DATA, { recursive: true, force: true });
fs.mkdirSync(USER_DATA, { recursive: true });
fs.writeFileSync(
  path.join(USER_DATA, "settings.json"),
  JSON.stringify(
    {
      gasflowApiUrl: STACK_URL,
      gasflowToken: "",
      waEnabled: false,
      waAutoReply: false,
      printerEnabled: false,
      printerName: "",
      waWebPanel: { enabled: false },
    },
    null,
    2,
  ),
  "utf-8",
);
app.setPath("userData", USER_DATA);
try {
  app.setPath("sessionData", USER_DATA);
} catch {
  /* versões antigas não expõem sessionData */
}

// 4 — diálogos nativos nunca bloqueiam a automação.
globalThis.__evidenceDialogs = [];
dialog.showMessageBox = async (...args) => {
  const opts =
    typeof args[0] === "object" && args[0] !== null && "message" in args[0]
      ? args[0]
      : args[1];
  globalThis.__evidenceDialogs.push(opts && opts.message ? opts.message : "(sem mensagem)");
  return { response: (opts && opts.cancelId) || 1, checkboxChecked: false };
};
dialog.showErrorBox = (title, content) => {
  globalThis.__evidenceDialogs.push(`${title}: ${content}`);
};

// 5 — o PDF vai para o tmp (mesmo caminho do app); nada de visualizador.
globalThis.__openedPdf = null;
shell.openPath = async (target) => {
  globalThis.__openedPdf = target;
  return "";
};

// App real — daqui pra baixo é o código do desktop, sem alteração.
const mainPath = path.join(__dirname, "..", "dist", "main", "index.js");
require(mainPath);

// 3 — gate IPC no mesmo backend que a janela carregou. Em produção o base é
// 127.0.0.1:8000 (uvicorn direto); aqui o stack passa pelo nginx, que só
// roteia /api/* e /health — /auth/me sem o prefixo cairia no SPA fallback
// (200 com HTML → JSON.parse falha → permissões vazias → gate nega tudo).
const permissions = require(path.join(__dirname, "..", "dist", "main", "ipc-permissions.js"));
permissions.forTesting().setBackendBaseUrl(`${STACK_URL.replace(/\/$/, "")}/api`);
