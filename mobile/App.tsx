/**
 * GasFlow App do Entregador — entry RN (F2 do spec).
 *
 * Responsabilidades do container:
 * 1. Animacao de splash no boot (AnimatedSplash com fade/scale/pulse).
 * 2. Carregar o consentimento LGPD persistido ANTES de decidir a rota inicial.
 * 3. Resolver a conexao ativa (LAN → nuvem → offline) e publicar no connection store.
 * 4. Montar o RootNavigator (gates de login/consentimento nas telas).
 *
 * Compila com o toolchain RN (React Native 0.76). A logica de negocio continua
 * em src/logic/*, testada em CI via node --test (sem toolchain RN).
 */

import React, { useEffect, useState } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import * as Keychain from "react-native-keychain";

import AnimatedSplash from "./src/screens/AnimatedSplash";
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
import { requestLocationPermission } from "./src/logic/permissions";

/**
 * Storage do consentimento no RN. O AsyncStorage e dependencia nativa — para
 * nao exigir pod/android build na F2, usamos o storage em memoria por padrao
 * e trocamos por AsyncStorage quando o pacote estiver no projeto (F2.5).
 */
setConsentStorage(createMemoryConsentStorage());

/**
 * Sessao: o token vive no Keystore do Android (EncryptedSharedPreferences) via
 * react-native-keychain — NUNCA em AsyncStorage em texto puro. E o que faz a
 * sessao persistir ao fechar/reabrir o app.
 */
setTokenStorage(createKeychainTokenStorage(Keychain as unknown as KeychainLike));

export default function App() {
  const [booted, setBooted] = useState(false);
  const [splashVisible, setSplashVisible] = useState(true);
  const setConnection = useConnectionStore((s) => s.setConnection);

  useEffect(() => {
    void (async () => {
      // 1. Solicitar permissao de GPS antes de qualquer coisa
      await requestLocationPermission();

      // 2. Carregar consentimento persistido
      await loadPersistedConsent();

      // 3. Restaurar sessao persistida (Keystore)
      await restorePersistedSession();

      // 4. Resolver conexao ativa (LAN → relay → cloud)
      const targets = getConnectionTargets();
      const resolved = await resolveConnection(targets, fetch);
      setConnection(resolved, targets.cloud?.relayToken ?? "");

      // 5. Boot concluido — marcar para splash sair
      setBooted(true);

      // Splash fica visivel por mais 600ms apos o boot para a animacao completar
      setTimeout(() => setSplashVisible(false), 600);
    })();
  }, [setConnection]);

  return (
    <>
      <AnimatedSplash visible={splashVisible} />
      {booted && (
        <SafeAreaProvider>
          <RootNavigator />
        </SafeAreaProvider>
      )}
    </>
  );
}
