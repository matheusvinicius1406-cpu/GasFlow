/**
 * permissions.ts — solicitacao de permissoes runtime no Android.
 *
 * react-native-permissions esta no package.json mas nunca foi importado.
 * Este modulo implementa a solicitacao de ACCESS_FINE_LOCATION antes de
 * usar o GPS, evitando crash no Android 6+.
 *
 * Sem react-native-permissions: usamos a API nativa do Android via
 * PermissionsAndroid do React Native (ja disponivel sem dependencia extra).
 */

import { PermissionsAndroid, Platform } from "react-native";

/**
 * Solicita permissao de localizacao fine (GPS).
 * Retorna true se concedida, false se negada.
 * No Android 5 (API < 23) sempre retorna true (permissoes no manifest).
 */
export async function requestLocationPermission(): Promise<boolean> {
  if (Platform.OS !== "android") return true;

  const apiLevel = Platform.Version;
  if (apiLevel < 23) return true;

  const granted = await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    {
      title: "Permissao de Localizacao",
      message:
        "O GasFlow precisa da sua localizacao para acompanhar as entregas durante o trabalho.",
      buttonPositive: "Permitir",
      buttonNegative: "Agora nao",
    }
  );

  return granted === PermissionsAndroid.RESULTS.GRANTED;
}

/**
 * Verifica se a permissao de localizacao ja foi concedida.
 */
export async function checkLocationPermission(): Promise<boolean> {
  if (Platform.OS !== "android") return true;

  const apiLevel = Platform.Version;
  if (apiLevel < 23) return true;

  const result = await PermissionsAndroid.check(
    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION
  );

  return result;
}
