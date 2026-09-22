/**
 * GasFlow App do Entregador — entry RN (F2 do spec).
 *
 * Responsabilidades do container:
 * 1. Carregar o consentimento LGPD persistido ANTES de decidir a rota inicial
 *    (loadPersistedConsent + setConsentStorage com AsyncStorage quando disponível).
 * 2. Resolver a conexão ativa (LAN → nuvem → offline, logic/connection.ts) e
 *    publicar no connection store usado pelos contêineres wired.
 * 3. Montar o RootNavigator (gates de login/consentimento nas telas).
 *
 * Compila com o toolchain RN (React Native 0.76). A lógica de negócio continua
 * em src/logic/*, testada em CI via node --test (sem toolchain RN).
 */

import React, { useEffect, useState } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import * as Keychain from "react-native-keychain";

import RootNavigator from "./src/navigation/RootNavigator";
import {
  loadPersistedConsent,
  restorePersistedSession,
  setConsentStorage,
  createMemoryConsentStorage,
} from "./src/logic/session";
import { setTokenStorage, createKeychainTokenStorage, type KeychainLike } from "./src/logic/tokenStorage";
import { resolveConnection } from "./src/logic/connection";
import { getConnectionTargets } from "./src/logic/config";
import { useConnectionStore } from "./src/containers/wired";

/**
 * Storage do consentimento no RN. O AsyncStorage é dependência nativa — para
 * não exigir pod/android build na F2, usamos o storage em memória por padrão
 * e trocamos por AsyncStorage quando o pacote estiver no projeto (F2.5).
 */
setConsentStorage(createMemoryConsentStorage());

/**
 * Sessão: o token vive no Keystore do Android (EncryptedSharedPreferences) via
 * react-native-keychain — NUNCA em AsyncStorage em texto puro. É o que faz a
 * sessão persistir ao fechar/reabrir o app.
 */
setTokenStorage(createKeychainTokenStorage(Keychain as unknown as KeychainLike));

export default function App() {
  const [booted, setBooted] = useState(false);
  const setConnection = useConnectionStore((s) => s.setConnection);

  useEffect(() => {
    void (async () => {
      await loadPersistedConsent();
      // Sessão persistida (Keystore): reabrir o app não pede login de novo.
      await restorePersistedSession();
      // F2.5: alvos reais (LAN/relay) de logic/config.ts — o desktop pode
      // sobrescrever no boot (QR/configurações) via setConnectionConfig.
      const targets = getConnectionTargets();
      const resolved = await resolveConnection(targets, fetch);
      setConnection(resolved, targets.cloud?.relayToken ?? "");
      setBooted(true);
    })();
  }, [setConnection]);

  if (!booted) return null; // splash nativo cobre este instante
  return (
    <SafeAreaProvider>
      <RootNavigator />
    </SafeAreaProvider>
  );
}
