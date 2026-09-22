/**
 * RootNavigator — auth gate + consent gate do App do Entregador.
 *
 * Ordem de navegacao:
 *   login → consentimento LGPD (1o acesso) → rota do dia → detalhe da entrega
 *
 * - Sem sessao → Login (swipe desabilitado: gates nao sao pulaveis).
 * - Com sessao e sem consentimento valido → Consent (bloqueante).
 * - Com sessao + consentimento → RouteToday.
 * - `consentLoaded` evita flash do consent enquanto o storage carrega.
 *
 * Transicoes animadas:
 * - Login/Consent → RouteToday: slide_from_right
 * - RouteToday → DeliveryDetail: slide_from_bottom
 * - Login/Consent: fade
 */

import React from "react";
import { View, StyleSheet } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import AnimatedSplash from "../screens/AnimatedSplash";
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
        screenOptions={{
          gestureEnabled: false,
          animation: "slide_from_right",
          contentStyle: { backgroundColor: "#ffffff" },
        }}
      >
        {!consentLoaded ? (
          // Splash minimo enquanto o consentimento persistido carrega.
          <Stack.Screen name="RouteToday" options={{ headerShown: false }}>
            {() => (
              <View style={styles.splash} testID="boot-splash">
                <AnimatedSplash visible={true} />
              </View>
            )}
          </Stack.Screen>
        ) : !accessToken ? (
          <Stack.Screen name="Login" options={{ headerShown: false, animation: "fade" }}>
            {() => <LoginScreenWired />}
          </Stack.Screen>
        ) : mustChangePassword ? (
          <Stack.Screen name="ChangePassword" options={{ headerShown: false, animation: "fade" }}>
            {() => <ChangePasswordScreenWired />}
          </Stack.Screen>
        ) : !hasValidConsent ? (
          <Stack.Screen name="Consent" options={{ headerShown: false, title: "Consentimento", animation: "fade" }}>
            {() => <ConsentScreen />}
          </Stack.Screen>
        ) : (
          <>
            <Stack.Screen name="RouteToday" options={{ title: "Rota do Dia", animation: "slide_from_right" }}>
              {(props: RouteTodayScreenWiredProps) => <RouteTodayScreenWired {...props} />}
            </Stack.Screen>
            <Stack.Screen name="DeliveryDetail" options={{ title: "Entrega", animation: "slide_from_bottom" }}>
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
