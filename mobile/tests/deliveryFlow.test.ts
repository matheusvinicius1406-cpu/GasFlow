/**
 * Testes do fluxo de entrega do app (frente MOBILE-P0) — espelho das regras
 * reais do backend (driver_api.py can_* / handle_*_delivery):
 *
 *   ASSIGNED/DISPATCHED --start--> EN_ROUTE --arrive--> ARRIVED --complete--> DELIVERED
 *
 * O P0 da auditoria era justamente a ausência do `arrive`: o backend recusa
 * `complete` fora de ARRIVED, então o entregador nunca concluía pelo app.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { enabledActions, isActionEnabled, nextStatusAfter } from "../src/logic/deliveryFlow.ts";

test("fluxo feliz: ASSIGNED → start → EN_ROUTE → arrive → ARRIVED → complete → DELIVERED", () => {
  let status = "ASSIGNED";
  assert.ok(isActionEnabled(status, "start"));
  status = nextStatusAfter(status, "start");
  assert.equal(status, "EN_ROUTE");

  assert.ok(isActionEnabled(status, "arrive"));
  status = nextStatusAfter(status, "arrive");
  assert.equal(status, "ARRIVED");

  assert.ok(isActionEnabled(status, "complete"));
  status = nextStatusAfter(status, "complete");
  assert.equal(status, "DELIVERED");
});

test("DISPATCHED também pode iniciar (mesmo can_start do backend)", () => {
  assert.ok(isActionEnabled("DISPATCHED", "start"));
  assert.equal(nextStatusAfter("DISPATCHED", "start"), "EN_ROUTE");
});

test("complete só libera em ARRIVED — nunca antes da chegada", () => {
  for (const status of ["ASSIGNED", "DISPATCHED", "EN_ROUTE", "DELIVERED", "FAILED"]) {
    assert.equal(isActionEnabled(status, "complete"), false, `complete deveria estar bloqueado em ${status}`);
  }
  assert.ok(isActionEnabled("ARRIVED", "complete"));
});

test("arrive só libera em EN_ROUTE (fora disso, 400 INVALID_STATE no servidor)", () => {
  for (const status of ["ASSIGNED", "DISPATCHED", "ARRIVED", "DELIVERED"]) {
    assert.equal(isActionEnabled(status, "arrive"), false, `arrive deveria estar bloqueado em ${status}`);
  }
  assert.ok(isActionEnabled("EN_ROUTE", "arrive"));
});

test("fail libera em EN_ROUTE e ARRIVED (espelho de can_fail); não inventa status", () => {
  assert.ok(isActionEnabled("EN_ROUTE", "fail"));
  assert.ok(isActionEnabled("ARRIVED", "fail"));
  assert.equal(isActionEnabled("ASSIGNED", "fail"), false);
  assert.equal(nextStatusAfter("EN_ROUTE", "fail"), "EN_ROUTE", "a tela mantém o status e mostra o motivo");
});

test("enabledActions cobre exatamente o estado atual", () => {
  assert.deepEqual(enabledActions("ASSIGNED"), ["start"]);
  assert.deepEqual(enabledActions("EN_ROUTE"), ["arrive", "fail"]);
  assert.deepEqual(enabledActions("ARRIVED"), ["complete", "fail"]);
  assert.deepEqual(enabledActions("DELIVERED"), []);
});
