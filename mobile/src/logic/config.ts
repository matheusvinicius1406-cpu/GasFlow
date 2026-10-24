/**
 * config — alvos de conexão do App do Entregador (F2.5).
 *
 * Defaults de dev; o desktop (QR/configurações) sobrescreve no boot via
 * setConnectionConfig. O relayToken é o segredo compartilhado do relay
 * (X-Relay-Token) — necessário para rastrear pela nuvem fora da LAN.
 *
 * Módulo puro com override injetável — testável via node --test.
 */

export interface ConnectionConfig {
  lanBaseUrl: string;
  cloudBaseUrl: string;
  relayToken: string;
}

export const DEFAULT_CONNECTION_CONFIG: ConnectionConfig = {
  // Default EXCLUSIVO de emulador Android (10.0.2.2 = loopback do host,
  // :8000 = backend direto). Em servidor real o operador digita a URL do
  // Home Server na tela de login (http://IP_DO_SERVIDOR, porta 80 — o nginx
  // expõe /auth/*, /driver/* e /ws; o backend :8000 NÃO é publicado).
  // Essa URL fica persistida no Keystore (serverConfig.ts) e não é
  // sobrescrita por atualização do app.
  lanBaseUrl: "http://10.0.2.2:8000",
  cloudBaseUrl: "",
  relayToken: "",
};

let current: ConnectionConfig = { ...DEFAULT_CONNECTION_CONFIG };

export function setConnectionConfig(config: Partial<ConnectionConfig>): void {
  current = { ...current, ...config };
}

export function getConnectionConfig(): ConnectionConfig {
  return { ...current };
}

/** Formato consumido pelo resolveConnection (connection.ts). */
export function getConnectionTargets(): {
  lan: { baseUrl: string } | null;
  cloud: { baseUrl: string; relayToken: string } | null;
} {
  return {
    lan: current.lanBaseUrl ? { baseUrl: current.lanBaseUrl } : null,
    cloud: current.cloudBaseUrl
      ? { baseUrl: current.cloudBaseUrl, relayToken: current.relayToken }
      : null,
  };
}

/**
 * Retorna a versao atual do app (do build.gradle via React NativeDeviceInfo ou fallback).
 * No Android real, estoaria em buildConfig; para MVP, hardcoded + override possivel.
 */
let _appVersion = "1.2.1";
export function getCurrentAppVersion(): string {
  return _appVersion;
}
export function setAppVersion(version: string): void {
  _appVersion = version;
}
