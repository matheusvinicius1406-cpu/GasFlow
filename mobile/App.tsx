/**
 * GasFlow App do Entregador — entry RN (Fase 2).
 *
 * SCAFFOLD: este arquivo compila com o toolchain RN (após `npm install` no
 * diretório mobile/ — React Native 0.76, New Architecture). A lógica de
 * negócio (fila offline, work-hours LGPD, fallback de conexão) vive em
 * src/logic/* e é testada em CI via node --test (sem toolchain RN).
 *
 * Telas do MVP (prompt 5.2): Login, Rota do Dia, Detalhe da Entrega,
 * Concluir Entrega (foto+assinatura), Reportar Problema, Histórico, Perfil.
 */

import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import LoginScreen from "./src/screens/LoginScreen";
import RouteTodayScreen from "./src/screens/RouteTodayScreen";
import DeliveryDetailScreen from "./src/screens/DeliveryDetailScreen";

export type RootStackParamList = {
  Login: undefined;
  RouteToday: undefined;
  DeliveryDetail: { deliveryId: string };
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator initialRouteName="Login">
        <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
        <Stack.Screen name="RouteToday" component={RouteTodayScreen} options={{ title: "Rota do Dia" }} />
        <Stack.Screen
          name="DeliveryDetail"
          component={DeliveryDetailScreen}
          options={{ title: "Entrega" }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
