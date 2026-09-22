/**
 * tokenStorage — custódia do token de sessão do app do entregador.
 *
 * Regra de segurança (prompt seção 7/12): o token NUNCA vai para storage em
 * texto puro (`AsyncStorage`). A produção usa Keystore/SecureStore; aqui a
 * interface é injetável para: (a) testar em node --test, (b) permitir um
 * adapter Android nativo sem acoplar o resto da lógica.
 *
 * `createKeychainTokenStorage` recebe o módulo (react-native-keychain) já
 * resolvido — a resolução dinâmica fica no boot do app (App.tsx), para o app
 * continuar funcionando mesmo se o pacote nativo não estiver instalado.
 *
 * Módulo puro — sem imports de RN.
 */

export interface TokenStorage {
  get(): Promise<string | null>;
  set(token: string): Promise<void>;
  clear(): Promise<void>;
}

/** Fallback em memória (testes/dev). Some ao fechar o app. */
export function createMemoryTokenStorage(): TokenStorage {
  let value: string | null = null;
  return {
    async get() {
      return value;
    },
    async set(token: string) {
      value = token;
    },
    async clear() {
      value = null;
    },
  };
}

/** Forma mínima usada do react-native-keychain (testável sem RN). */
export interface KeychainLike {
  setGenericPassword(username: string, password: string, options?: Record<string, unknown>): Promise<unknown>;
  getGenericPassword(options?: Record<string, unknown>): Promise<false | { password?: string }>;
  resetGenericPassword(options?: Record<string, unknown>): Promise<unknown>;
}

const KEYCHAIN_SERVICE = "gasflow.driver.session";
const KEYCHAIN_USER = "driver";

/**
 * Token no Keystore do Android via Keychain (EncryptedSharedPreferences).
 * Produção. O serviço/usuário fixos mantêm uma única credencial por app.
 */
export function createKeychainTokenStorage(keychain: KeychainLike): TokenStorage {
  return {
    async get() {
      const entry = await keychain.getGenericPassword({ service: KEYCHAIN_SERVICE }).catch(() => false);
      return entry && typeof entry === "object" ? (entry.password ?? null) : null;
    },
    async set(token: string) {
      await keychain.setGenericPassword(KEYCHAIN_USER, token, { service: KEYCHAIN_SERVICE });
    },
    async clear() {
      await keychain.resetGenericPassword({ service: KEYCHAIN_SERVICE }).catch(() => undefined);
    },
  };
}

let current: TokenStorage = createMemoryTokenStorage();

/** Injeta o storage efetivo (Keystore em produção). Chamar no boot. */
export function setTokenStorage(storage: TokenStorage): void {
  current = storage;
}

export function getTokenStorage(): TokenStorage {
  return current;
}
