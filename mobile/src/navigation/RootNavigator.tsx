/**
 * RootNavigator — auth gate + consent gate do App do Entregador (F2 do spec).
 *
 * Ordem de navegação (C4 do prompt):
 *   login → consentimento LGPD (1º acesso) → rota do dia → detalhe da entrega
 *
 * - Sem sessão → Login (swipe desabilitado: gates não são puláveis).
 * - Com sessão e sem consentimento válido → Consent (bloqueante).
 * - Com sessão + consentimento → RouteToday.
 * - `consentLoaded` evita flash do consent enquanto o storage carrega.
 *
 * As telas renderizadas são os contêineres wired (containers/wired.tsx),
 * que ligam store de sessão + API + fila offline às telas de apresentação.
 */

import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import ConsentScreen from "../screens/ConsentScreen";
import {
  LoginScreenWired,
  ChangePasswordScreenWired,
  RouteTodayScreenWired,
  DeliveryDetailScreenWired,
  RouteTodayScreenWiredProps,
  DeliveryDetailScreenWiredProps,
} from "../containers/wired";
import { useSessionStore } from "../logic/session";

export type RootStackParamList = {
  Login: undefined;
  ChangePassword: undefined;
  Consent: undefined;
  RouteToday: undefined;
  DeliveryDetail: { deliveryId: string };
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  const accessToken = useSessionStore((s) => s.accessToken);
  const consentLoaded = useSessionStore((s) => s.consentLoaded);
  const mustChangePassword = useSessionStore((s) => s.mustChangePassword);
  const hasValidConsent = useSessionStore((s) => s.hasValidConsent());

  // Ordem: login → troca de senha (bloqueante) → consentimento LGPD → rota.
  const initialRoute: keyof RootStackParamList = !consentLoaded
    ? "RouteToday" // placeholder durante o load (evita flash do consent)
    : !accessToken
      ? "Login"
      : mustChangePassword
        ? "ChangePassword"
        : !hasValidConsent
          ? "Consent"
          : "RouteToday";

  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName={initialRoute}
        screenOptions={{ gestureEnabled: false }} // gates não são puláveis por swipe
      >
        {!consentLoaded ? (
          // Splash mínimo enquanto o consentimento persistido carrega.
          <Stack.Screen name="RouteToday" options={{ headerShown: false }}>
            {() => (
              <View style={styles.splash} testID="boot-splash">
                <Text>Carregando…</Text>
              </View>
            )}
          </Stack.Screen>
        ) : !accessToken ? (
          <Stack.Screen name="Login" options={{ headerShown: false }}>
            {() => <LoginScreenWired />}
          </Stack.Screen>
        ) : mustChangePassword ? (
          <Stack.Screen name="ChangePassword" options={{ headerShown: false }}>
            {() => <ChangePasswordScreenWired />}
          </Stack.Screen>
        ) : !hasValidConsent ? (
          <Stack.Screen name="Consent" options={{ headerShown: false, title: "Consentimento" }}>
            {() => <ConsentScreen />}
          </Stack.Screen>
        ) : (
          <>
            <Stack.Screen name="RouteToday" options={{ title: "Rota do Dia" }}>
              {(props: RouteTodayScreenWiredProps) => <RouteTodayScreenWired {...props} />}
            </Stack.Screen>
            <Stack.Screen name="DeliveryDetail" options={{ title: "Entrega" }}>
              {(props: DeliveryDetailScreenWiredProps) => <DeliveryDetailScreenWired {...props} />}
            </Stack.Screen>
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  splash: { flex: 1, alignItems: "center", justifyContent: "center" },
});
