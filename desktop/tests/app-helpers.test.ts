/**
 * Testes dos helpers puros do main process (dist/main/app-helpers.js).
 * Cobrem as decisões que antes viviam inline em index.ts — porta/URLs do
 * backend, resolução de paths de boot, sanitização de nome de PDF, cupom de
 * teste ESC/POS e o plano de serviços decidido no whenReady.
 * Rodam em node puro, sem Electron.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";

const req = createRequire(__filename);
const helpers = req("../dist/main/app-helpers.js") as typeof import("../dist/main/app-helpers");

// ── backendPort / backendUrl / waBaseUrl ────────────────────────────────

test("backendPort extrai a porta de gasflowApiUrl", () => {
  assert.equal(helpers.backendPort("http://localhost:8000"), 8000);
  assert.equal(helpers.backendPort("http://127.0.0.1:9001"), 9001);
  assert.equal(helpers.backendPort("http://localhost:8000/api"), 8000);
});

test("backendPort cai no default 8000 sem porta válida", () => {
  assert.equal(helpers.backendPort("http://localhost"), 8000);
  assert.equal(helpers.backendPort(""), 8000);
});

test("backendUrl sempre aponta para 127.0.0.1 (não para localhost/IPv6)", () => {
  assert.equal(helpers.backendUrl("http://localhost:8000"), "http://127.0.0.1:8000");
  assert.equal(helpers.backendUrl("http://localhost:9001"), "http://127.0.0.1:9001");
});

test("waBaseUrl usa a porta vinda de settings.waPort", () => {
  assert.equal(helpers.waBaseUrl(3101), "http://127.0.0.1:3101");
  assert.equal(helpers.waBaseUrl("3101"), "http://127.0.0.1:3101");
});

test("sqliteDatabaseUrl normaliza o separador para / (URL SQLAlchemy no Windows)", () => {
  const url = helpers.sqliteDatabaseUrl(path.join("C:", "Users", "me", "AppData", "Roaming", "gasflow-desktop"));
  assert.equal(url, "sqlite:///C:/Users/me/AppData/Roaming/gasflow-desktop/gasflow.db");
  assert.ok(!url.includes("\\"), "não pode sobrar barra invertida na URL");
});

// ── resolveFrontendDist ────────────────────────────────────────────────

test("resolveFrontendDist: empacotado usa resources/frontend", () => {
  const out = helpers.resolveFrontendDist({
    isPackaged: true,
    resourcesPath: "C:/app/resources",
    devDist: "C:/repo/frontend/dist",
    exists: () => false,
  });
  assert.equal(out, path.join("C:/app/resources", "frontend"));
});

test("resolveFrontendDist: dev com dist buildado usa o dist local", () => {
  const out = helpers.resolveFrontendDist({
    isPackaged: false,
    resourcesPath: "",
    devDist: "C:/repo/frontend/dist",
    exists: (p) => p === "C:/repo/frontend/dist",
  });
  assert.equal(out, "C:/repo/frontend/dist");
});

test("resolveFrontendDist: dev sem build devolve vazio (backend serve sem FR_DIST)", () => {
  const out = helpers.resolveFrontendDist({
    isPackaged: false,
    resourcesPath: "",
    devDist: "C:/repo/frontend/dist",
    exists: () => false,
  });
  assert.equal(out, "");
});

// ── resolvePython ──────────────────────────────────────────────────────

const uvicornArgs = ["-m", "uvicorn", "app.main:app"];

test("resolvePython: empacotado com gasflow-backend.exe usa o binário (sem args)", () => {
  const out = helpers.resolvePython({
    isPackaged: true,
    resourcesPath: "C:/app/resources",
    backendDir: "C:/app/resources/backend",
    exists: (p) => p === path.join("C:/app/resources/backend", "gasflow-backend.exe"),
    cwd: "C:/repo",
  });
  assert.deepEqual(out, {
    command: path.join("C:/app/resources/backend", "gasflow-backend.exe"),
    args: [],
    cwd: "C:/app/resources/backend",
  });
});

test("resolvePython: empacotado sem binário cai no venv se existir", () => {
  const backendDir = "C:/app/resources/backend";
  const out = helpers.resolvePython({
    isPackaged: true,
    resourcesPath: "C:/app/resources",
    backendDir,
    exists: (p) => p === path.join(backendDir, ".venv", "Scripts", "python.exe") || p === path.join(backendDir, "app", "main.py"),
    cwd: "C:/repo",
  });
  assert.equal(out.command, path.join(backendDir, ".venv", "Scripts", "python.exe"));
  assert.deepEqual(out.args, uvicornArgs);
  assert.equal(out.cwd, backendDir);
});

test("resolvePython: dev com venv usa o venv e cwd do backend", () => {
  const backendDir = "C:/repo/backend";
  const out = helpers.resolvePython({
    isPackaged: false,
    resourcesPath: "",
    backendDir,
    exists: (p) => p === path.join(backendDir, ".venv", "Scripts", "python.exe") || p === path.join(backendDir, "app", "main.py"),
    cwd: "C:/outro",
  });
  assert.equal(out.command, path.join(backendDir, ".venv", "Scripts", "python.exe"));
  assert.deepEqual(out.args, uvicornArgs);
  assert.equal(out.cwd, backendDir);
});

test("resolvePython: dev sem venv usa python do PATH", () => {
  const backendDir = "C:/repo/backend";
  const out = helpers.resolvePython({
    isPackaged: false,
    resourcesPath: "",
    backendDir,
    exists: (p) => p === path.join(backendDir, "app", "main.py"),
    cwd: "C:/outro",
  });
  assert.equal(out.command, "python");
  assert.deepEqual(out.args, uvicornArgs);
  assert.equal(out.cwd, backendDir);
});

test("resolvePython: sem backend no cwd não existe → cwd do processo (evita uvicorn mudo)", () => {
  const out = helpers.resolvePython({
    isPackaged: false,
    resourcesPath: "",
    backendDir: "C:/inexistente/backend",
    exists: () => false,
    cwd: "C:/atual",
  });
  assert.equal(out.command, "python");
  assert.equal(out.cwd, "C:/atual");
});

// ── sanitizePdfFilename / isSessionToken ───────────────────────────────

test("sanitizePdfFilename mantém apenas [a-zA-Z0-9._-]", () => {
  assert.equal(helpers.sanitizePdfFilename("nota-compra_01.pdf"), "nota-compra_01.pdf");
  const dirty = helpers.sanitizePdfFilename("nota (1) & cia.pdf");
  assert.equal(dirty, "nota__1____cia.pdf");
  assert.match(dirty, /^[a-zA-Z0-9._-]+$/);
});

test("sanitizePdfFilename bloqueia path traversal (sem / nem \\)", () => {
  const out = helpers.sanitizePdfFilename("../../../etc/passwd");
  assert.ok(!out.includes("/"));
  assert.ok(!out.includes("\\"));
  assert.match(out, /^[a-zA-Z0-9._-]+$/);
});

test("sanitizePdfFilename: valor não-string ou vazio cai no fallback", () => {
  assert.equal(helpers.sanitizePdfFilename(undefined), "nota-compra.pdf");
  assert.equal(helpers.sanitizePdfFilename(null), "nota-compra.pdf");
  assert.equal(helpers.sanitizePdfFilename(42), "nota-compra.pdf");
  assert.equal(helpers.sanitizePdfFilename(""), "nota-compra.pdf");
  assert.equal(helpers.sanitizePdfFilename("x.pdf", "outro.pdf"), "x.pdf");
});

test("isSessionToken aceita só string", () => {
  assert.equal(helpers.isSessionToken("abc"), true);
  assert.equal(helpers.isSessionToken(""), true);
  assert.equal(helpers.isSessionToken(null), false);
  assert.equal(helpers.isSessionToken(undefined), false);
  assert.equal(helpers.isSessionToken(123), false);
  assert.equal(helpers.isSessionToken({}), false);
});

// ── cupom de teste ESC/POS ─────────────────────────────────────────────

test("TEST_RECEIPT_ESCPOS é um cupom 80mm válido (init, texto, cut)", () => {
  const receipt = helpers.TEST_RECEIPT_ESCPOS;
  assert.ok(receipt.startsWith("\x1b@"), "deve iniciar com ESC @ (reset)");
  assert.ok(receipt.includes("TESTE DE IMPRESSORA"));
  assert.ok(receipt.endsWith("\x1bi"), "deve terminar com corte parcial ESC i");
  assert.equal(Buffer.from(receipt, "binary").length, receipt.length);
});

// ── planServices (decisões de boot) ────────────────────────────────────

test("planServices: defaults sobem whatsapp e printer; painel/relay/assistant off", () => {
  const plan = helpers.planServices({});
  assert.deepEqual(plan, {
    whatsapp: true,
    assistant: false,
    printer: true,
    waWebPanel: false,
    relay: false,
  });
});

test("planServices: waEnabled=false desliga whatsapp e assistant mesmo com autoReply", () => {
  const plan = helpers.planServices({ waEnabled: false, waAutoReply: true });
  assert.equal(plan.whatsapp, false);
  assert.equal(plan.assistant, false);
});

test("planServices: assistant só quando waAutoReply verdadeiro e whatsapp ativo", () => {
  assert.equal(helpers.planServices({ waAutoReply: true }).assistant, true);
  assert.equal(helpers.planServices({ waAutoReply: false }).assistant, false);
  assert.equal(helpers.planServices({}).assistant, false);
});

test("planServices: printerEnabled=false desliga o worker; ausente = ligado", () => {
  assert.equal(helpers.planServices({ printerEnabled: false }).printer, false);
  assert.equal(helpers.planServices({ printerEnabled: true }).printer, true);
  assert.equal(helpers.planServices({}).printer, true);
});

test("planServices: waWebPanel liga só com enabled === true (default OFF)", () => {
  assert.equal(helpers.planServices({ waWebPanel: { enabled: true } }).waWebPanel, true);
  assert.equal(helpers.planServices({ waWebPanel: { enabled: false } }).waWebPanel, false);
  assert.equal(helpers.planServices({ waWebPanel: {} }).waWebPanel, false);
  assert.equal(helpers.planServices({}).waWebPanel, false);
});

test("planServices: relay exige flag E url (settings antigos sem url ficam off)", () => {
  assert.equal(helpers.planServices({ relayEnabled: true, relayUrl: "https://relay" }).relay, true);
  assert.equal(helpers.planServices({ relayEnabled: true }).relay, false);
  assert.equal(helpers.planServices({ relayUrl: "https://relay" }).relay, false);
  assert.equal(helpers.planServices({ relayEnabled: false, relayUrl: "https://relay" }).relay, false);
});
