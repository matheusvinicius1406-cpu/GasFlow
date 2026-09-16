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

import RootNavigator from "./src/navigation/RootNavigator";
import { loadPersistedConsent, setConsentStorage, createMemoryConsentStorage } from "./src/logic/session";
import { resolveConnection } from "./src/logic/connection";
import { useConnectionStore } from "./src/containers/wired";

/**
 * Storage do consentimento no RN. O AsyncStorage é dependência nativa — para
 * não exigir pod/android build na F2, usamos o storage em memória por padrão
 * e trocamos por AsyncStorage quando o pacote estiver no projeto (F2.5).
 */
setConsentStorage(createMemoryConsentStorage());

export default function App() {
  const [booted, setBooted] = useState(false);
  const setConnection = useConnectionStore((s) => s.setConnection);

  useEffect(() => {
    void (async () => {
      await loadPersistedConsent();
      // Targets reais virão das configurações/QR na F2.5; aqui, o dev server
      // local é o fallback LAN default e o relay da nuvem quando configurado.
      const targets = {
        lan: { baseUrl: "http://10.0.2.2:8000" }, // host machine a partir do emulador Android
        cloud: undefined,
      };
      const resolved = await resolveConnection(targets, fetch);
      setConnection(resolved);
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
