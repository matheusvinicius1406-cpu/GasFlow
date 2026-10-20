/**
 * serverConfig — URL do servidor (backend) escolhida pelo entregador.
 *
 * O build nasce com os defaults de dev de `config.ts` (LAN do emulador,
 * nuvem vazia): em um celular real o probe falha, o resolveConnection cai em
 * offline e o login não tem baseUrl. Esta URL persistida no Keystore é o
 * `lanBaseUrl` efetivo — o que é digitado na tela de login vale no boot
 * seguinte.
 *
 * Módulo puro — sem imports de RN (mesma convenção de tokenStorage).
 */

import type { KeychainLike } from "./tokenStorage";

export interface ServerUrlStorage {
    get(): Promise<string | null>;
    set(url: string): Promise<void>;
}

/** Fallback em memória (testes/dev). Some ao fechar o app. */
export function createMemoryServerUrlStorage(): ServerUrlStorage {
    let value: string | null = null;
    return {
        async get() {
            return value;
        },
        async set(url: string) {
            value = url;
        },
    };
}

const KEYCHAIN_SERVICE = "gasflow.driver.server";
const KEYCHAIN_USER = "server";

/** URL no Keystore do Android via Keychain — mesma custódia do token. */
export function createKeychainServerUrlStorage(keychain: KeychainLike): ServerUrlStorage {
    return {
        async get() {
            const entry = await keychain.getGenericPassword({ service: KEYCHAIN_SERVICE }).catch(() => false);
            return entry && typeof entry === "object" ? (entry.password ?? null) : null;
        },
        async set(url: string) {
            await keychain.setGenericPassword(KEYCHAIN_USER, url, { service: KEYCHAIN_SERVICE });
        },
    };
}

let current: ServerUrlStorage = createMemoryServerUrlStorage();

/** Injeta o storage efetivo (Keystore em produção). Chamar no boot. */
export function setServerUrlStorage(storage: ServerUrlStorage): void {
    current = storage;
}

export function getServerUrlStorage(): ServerUrlStorage {
    return current;
}

/**
 * Normaliza a URL digitada: trim, barra final removida, exige http(s).
 * Retorna null quando a entrada não é uma URL utilizável.
 */
export function normalizeServerUrl(raw: string): string | null {
    const url = (raw ?? "").trim().replace(/\/+$/, "");
    if (!/^https?:\/\/[^\s]+$/i.test(url)) {
        return null;
    }
    return url;
}
