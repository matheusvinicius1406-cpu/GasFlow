/**
 * session — estado global do app do entregador (zustand).
 *
 * F2 do spec: fonte de verdade compartilhada entre as telas.
 * - tokens/sessão após o login (tokens reais vão para storage seguro na F2.5;
 *   aqui ficam em memória e o App container persiste via storage injetável)
 * - consentimento LGPD de rastreamento: bloqueia o uso até aceitar (F2),
 *   registrando data e versão do termo
 *
 * Persistência do consentimento: storage injetável (async puro, interface
 * mínima) — no RN real será AsyncStorage/MMKV; nos testes, um Map em memória.
 * Módulo importável por telas RN E por node --test (zustand é isomórfico).
 */

import { create } from "zustand";

import { getTokenStorage } from "./tokenStorage.ts";

export const CONSENT_VERSION = "1.0"; // bump quando o termo mudar → pede de novo

export interface SessionState {
  accessToken: string | null;
  refreshToken: string | null;
  driverId: string | null;
  /** Nome de login exibido no gate de senha. */
  username: string | null;
  /**
   * P0 (3.8): true pós-reset admin — o app fica bloqueado na tela de troca até
   * `POST /auth/change-password` limpar a flag no backend.
   */
  mustChangePassword: boolean;

  /** LGPD: consentimento de rastreamento aceito? (null = ainda não perguntado) */
  consentAcceptedAt: string | null;
  consentVersion: string | null;
  consentLoaded: boolean;

  setSession(tokens: { access_token: string; refresh_token: string; driver_id: string }): void;
  /** Restaura a sessão persistida (Keystore) no boot — não passa por login. */
  restoreToken(token: string): void;
  setMustChangePassword(value: boolean): void;
  clearSession(): void;
  acceptConsent(now?: Date): void;
  setConsentLoaded(): void;
  /** Termo vigente aceito? (false enquanto não carregar ou não responder) */
  hasValidConsent(): boolean;
}

interface ConsentPersisted {
  acceptedAt: string;
  version: string;
}

export interface ConsentStorage {
  get(): Promise<ConsentPersisted | null>;
  set(value: ConsentPersisted): Promise<void>;
}

/** Storage em memória — default nos testes e fallback seguro no RN. */
export function createMemoryConsentStorage(): ConsentStorage {
  let value: ConsentPersisted | null = null;
  return {
    async get() {
      return value;
    },
    async set(next) {
      value = next;
    },
  };
}

let consentStorage: ConsentStorage = createMemoryConsentStorage();

/** Injeta o storage persistente (AsyncStorage no RN). Chamar no boot do app. */
export function setConsentStorage(storage: ConsentStorage): void {
  consentStorage = storage;
}

export function getConsentStorage(): ConsentStorage {
  return consentStorage;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  accessToken: null,
  refreshToken: null,
  driverId: null,
  username: null,
  mustChangePassword: false,
  consentAcceptedAt: null,
  consentVersion: null,
  consentLoaded: false,

  setSession: ({ access_token, refresh_token, driver_id }) => {
    set({ accessToken: access_token, refreshToken: refresh_token, driverId: driver_id });
    // Custódia do token: Keystore (produção) — nunca AsyncStorage em texto puro.
    void getTokenStorage().set(access_token).catch(() => {
      /* falha de persistência não derruba a sessão em memória */
    });
  },

  restoreToken: (token) => set({ accessToken: token }),

  setMustChangePassword: (value) => set({ mustChangePassword: value }),

  clearSession: () => {
    set({ accessToken: null, refreshToken: null, driverId: null, mustChangePassword: false });
    void getTokenStorage().clear().catch(() => undefined);
  },

  acceptConsent: (now = new Date()) => {
    const acceptedAt = now.toISOString();
    set({ consentAcceptedAt: acceptedAt, consentVersion: CONSENT_VERSION });
    void consentStorage.set({ acceptedAt, version: CONSENT_VERSION }).catch(() => {
      /* persistência é best-effort — o estado em memória já vale para a sessão */
    });
  },

  setConsentLoaded: () => set({ consentLoaded: true }),

  hasValidConsent: () => {
    const s = get();
    return !!s.consentAcceptedAt && s.consentVersion === CONSENT_VERSION;
  },
}));

/**
 * Boot: carrega consentimento persistido. Chamar uma vez no App container;
 * a navegação só decide depois de `consentLoaded` (evita flash do consent).
 */
export async function loadPersistedConsent(): Promise<void> {
  try {
    const persisted = await consentStorage.get();
    if (persisted && persisted.version === CONSENT_VERSION) {
      useSessionStore.setState({
        consentAcceptedAt: persisted.acceptedAt,
        consentVersion: persisted.version,
      });
    } else if (persisted) {
      // Termo antigo → pede novamente (LGPD: nova versão = novo consentimento)
      useSessionStore.setState({ consentAcceptedAt: null, consentVersion: null });
    }
  } catch {
    /* storage indisponível → pede consentimento (fail-closed) */
  } finally {
    useSessionStore.getState().setConsentLoaded();
  }
}

/**
 * Boot: restaura o token do Keystore. É o que faz "fechar e reabrir o app →
 * sessão persiste" sem passar pelo login de novo. Devolve se havia sessão.
 */
export async function restorePersistedSession(): Promise<boolean> {
  try {
    const token = await getTokenStorage().get();
    if (token) {
      useSessionStore.getState().restoreToken(token);
      return true;
    }
  } catch {
    /* Keystore indisponível → cai no login */
  }
  return false;
}
