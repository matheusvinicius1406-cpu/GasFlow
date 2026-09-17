/**
 * Testes do config de conexão (F2.5) — defaults de dev, override do desktop
 * e formato consumido pelo resolveConnection.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_CONNECTION_CONFIG,
  getConnectionConfig,
  getConnectionTargets,
  setConnectionConfig,
} from "../src/logic/config.ts";

test("config: defaults de dev (LAN emulador, nuvem vazia)", () => {
  const cfg = getConnectionConfig();
  assert.equal(cfg.lanBaseUrl, "http://10.0.2.2:8000");
  assert.equal(cfg.cloudBaseUrl, "");
  assert.deepEqual(cfg, DEFAULT_CONNECTION_CONFIG);
});

test("config: override parcial (desktop injeta relay + token)", () => {
  setConnectionConfig({ cloudBaseUrl: "https://relay.gasflow.app", relayToken: "sec" });
  const cfg = getConnectionConfig();
  assert.equal(cfg.cloudBaseUrl, "https://relay.gasflow.app");
  assert.equal(cfg.relayToken, "sec");
  assert.equal(cfg.lanBaseUrl, DEFAULT_CONNECTION_CONFIG.lanBaseUrl, "LAN preservada");

  const targets = getConnectionTargets();
  assert.equal(targets.lan?.baseUrl, DEFAULT_CONNECTION_CONFIG.lanBaseUrl);
  assert.deepEqual(targets.cloud, { baseUrl: "https://relay.gasflow.app", relayToken: "sec" });
});

test("config: nuvem vazia ⇒ target cloud null (connection cai para LAN/offline)", () => {
  setConnectionConfig({ cloudBaseUrl: "", relayToken: "" });
  const targets = getConnectionTargets();
  assert.equal(targets.cloud, null);
  assert.equal(targets.lan !== null, true);
});
