/**
 * Testes de config (dist/main/config.js): defaults + merge de settings.json.
 * Stub do módulo electron para rodar em node puro (userData → tmp dir).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import Module from "node:module";
import { createRequire } from "node:module";

const origRequire = Module.prototype.require;

/** Roda `fn` com o módulo electron stubulado (app.getPath → tmp). */
function withStubbedElectron(userDataDir: string, fn: () => void) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "gf-cfg-test-"));
  Module.prototype.require = function (this: unknown, id: string) {
    if (id === "electron") {
      return { app: { getPath: () => userDataDir ?? tmp, isPackaged: false } };
    }
    return origRequire.apply(this, arguments as unknown as Parameters<typeof origRequire>);
  };
  try {
    fn();
  }
  finally {
    Module.prototype.require = origRequire;
  }
}

const req = createRequire(__filename);
// eslint-disable-next-line @typescript-eslint/no-var-requires
const cfgPath = path.resolve(__dirname, "../dist/main/config.js");

test("defaults: waEnabled=true, waPort=3101 e merge com settings.json", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "gf-cfg-test-"));
  withStubbedElectron(tmp, () => {
    const cfg = req(cfgPath);
    // Sem settings.json: defaults completos
    const s1 = cfg.loadSettings();
    assert.equal(s1.waEnabled, true, "waEnabled default deve ser true");
    assert.equal(s1.waPort, 3101);
    assert.equal(s1.ollamaTextModel, "llama3.2");
    assert.ok(String(s1.waApiKey).startsWith("wa-"), "waApiKey gerada na 1ª execução");
    assert.ok(s1.backendAdminPassword.length > 0, "senha admin gerada na 1ª execução");
    assert.ok(fs.existsSync(path.join(tmp, "LOGIN.txt")), "LOGIN.txt escrito");

    // settings.json existente: merge respeita valores salvos (mantendo as
    // chaves geradas na 1ª execução — é o que o app grava na prática).
    fs.writeFileSync(
      path.join(tmp, "settings.json"),
      JSON.stringify({
        waPort: 3200,
        waEnabled: false,
        waApiKey: s1.waApiKey,
        backendAdminPassword: s1.backendAdminPassword,
      }),
      "utf-8",
    );
    const s2 = cfg.loadSettings();
    assert.equal(s2.waPort, 3200, "merge deve preservar waPort salvo");
    assert.equal(s2.waEnabled, false, "merge deve preservar waEnabled=false");
    // keys sensíveis persistidas entre loads
    assert.equal(s2.waApiKey, s1.waApiKey);
    assert.equal(s2.backendAdminPassword, s1.backendAdminPassword);
  });
});

test("saveSettings persiste e loadSettings relê o mesmo valor", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "gf-cfg-test-"));
  withStubbedElectron(tmp, () => {
    const cfg = req(cfgPath);
    const s = cfg.loadSettings();
    s.waAutoReply = true;
    s.waEnabled = false;
    cfg.saveSettings(s);
    const again = cfg.loadSettings();
    assert.equal(again.waAutoReply, true);
    assert.equal(again.waEnabled, false);
  });
});

test("settings.json corrompido cai nos defaults e regenera chaves", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "gf-cfg-test-"));
  withStubbedElectron(tmp, () => {
    // Limpa o cache: sem isso o config.js avaliado é o do teste anterior
    // (app.getPath aponta para o tmp antigo — module cache do Node).
    delete req.cache[req.resolve(cfgPath)];
    const cfg = req(cfgPath);
    // JSON inválido
    fs.writeFileSync(path.join(tmp, "settings.json"), "{invalid json!!", "utf-8");
    const s = cfg.loadSettings();
    assert.equal(s.waEnabled, true, "default waEnabled");
    assert.equal(s.waPort, 3101, "default waPort");
    assert.ok(String(s.waApiKey).startsWith("wa-"), "waApiKey regenerada");
    assert.ok(s.backendAdminPassword.length > 0, "backendAdminPassword regenerada");
    // settings.json não-objeto (ex.: string) também cai nos defaults
    fs.writeFileSync(path.join(tmp, "settings.json"), '"apenas string"', "utf-8");
    const s2 = cfg.loadSettings();
    assert.equal(s2.waPort, 3101);
  });
});
