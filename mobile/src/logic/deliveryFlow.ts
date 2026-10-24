/**
 * deliveryFlow — mapa de ações do entregador espelhando o contrato real do
 * backend (driver_api.py: can_* e os handlers handle_*_delivery).
 *
 * Motivo: a tela e o contêiner wired calculavam `disabled`/status otimista com
 * ifs espalhados, e o `/arrive` (EN_ROUTE → ARRIVED) não existia no app — o
 * backend recusa `complete` fora de ARRIVED, então o entregador não conseguia
 * concluir nada. Este módulo puro concentra as regras e é testado com
 * node --test (sem React Native).
 *
 * Cadeia canônica do domínio:
 *   ASSIGNED/DISPATCHED --start--> EN_ROUTE --arrive--> ARRIVED --complete--> DELIVERED
 */

/** Ações que mudam o status da entrega (o `accept` é tratado pela rota da rota). */
export type DeliveryFlowAction = "start" | "arrive" | "complete" | "fail";

/** Status atual → ações que o backend aceita (espelho de driver_api.can_*). */
const ENABLED_FROM: Record<DeliveryFlowAction, readonly string[]> = {
  start: ["ASSIGNED", "DISPATCHED"],
  arrive: ["EN_ROUTE"],
  complete: ["ARRIVED"],
  fail: ["EN_ROUTE", "ARRIVED"],
};

/** Status resultante de cada ação (espelho dos handlers handle_*_delivery). */
const NEXT_STATUS: Record<DeliveryFlowAction, string> = {
  start: "EN_ROUTE",
  arrive: "ARRIVED",
  complete: "DELIVERED",
  fail: "FAILED",
};

/** Ação habilitada para o status atual — mesma regra de validação do servidor. */
export function isActionEnabled(status: string, action: DeliveryFlowAction): boolean {
  return ENABLED_FROM[action].includes(status);
}

/**
 * Status otimista depois da ação. `fail` é tratado pela tela (mantém o status
 * e mostra o motivo), por isso devolve o status atual — nunca inventa estado.
 */
export function nextStatusAfter(status: string, action: DeliveryFlowAction): string {
  if (action === "fail") return status;
  return NEXT_STATUS[action];
}

/** Ações habilitadas para um status (para testes/telemetria de UI). */
export function enabledActions(status: string): DeliveryFlowAction[] {
  return (Object.keys(ENABLED_FROM) as DeliveryFlowAction[]).filter((action) => isActionEnabled(status, action));
}
