/**
 * Contêineres "wired" das telas (F2 do spec).
 *
 * As telas em screens/* são de apresentação (callbacks). Aqui elas ganham
 * comportamento: store de sessão (zustand), API real (logic/api.ts), fila
 * offline (logic/offlineQueue.ts) e navegação (@react-navigation).
 *
 * A resolução de conexão (LAN→nuvem→offline, logic/connection.ts) acontece
 * no app container no boot; o baseUrl ativo fica no store de conexão e é
 * injetado aqui. Sem rede: ações passam pela fila e a rota mostra cache.
 */

import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import type { RootStackParamList } from "../navigation/RootNavigator";
import LoginScreen from "../screens/LoginScreen";
import RouteTodayScreen, { type RouteDelivery } from "../screens/RouteTodayScreen";
import DeliveryDetailScreen, { type DeliveryDetail } from "../screens/DeliveryDetailScreen";
import { useSessionStore } from "../logic/session";
import { mobileLogin, fetchMyDeliveries, postDeliveryAction, type DeliveryDTO } from "../logic/api";
import { OfflineQueue, type QueueItem, type QueueStorage } from "../logic/offlineQueue";
import { resolveConnection, type ResolvedConnection } from "../logic/connection";

export type RouteTodayScreenWiredProps = NativeStackScreenProps<RootStackParamList, "RouteToday">;
export type DeliveryDetailScreenWiredProps = NativeStackScreenProps<RootStackParamList, "DeliveryDetail">;

/** Url de conexão ativa — setada pelo app container a partir do resolveConnection. */
interface ConnectionStore {
  connection: ResolvedConnection;
  setConnection: (c: ResolvedConnection) => void;
}
import { create } from "zustand";
export const useConnectionStore = create<ConnectionStore>((set) => ({
  connection: { mode: "offline", baseUrl: null },
  setConnection: (connection) => set({ connection }),
}));

/** Fila offline com storage em memória + rehidratação (RN real: SQLite/MMKV). */
const queueItems: QueueItem[] = [];
export const queueStorage: QueueStorage = {
  all: () => queueItems.slice(),
  save: (item) => {
    const idx = queueItems.findIndex((i) => i.client_action_id === item.client_action_id);
    if (idx >= 0) queueItems[idx] = { ...item };
    else queueItems.push({ ...item });
  },
};
export const deliveryQueue = new OfflineQueue(queueStorage);

function toRoute(d: DeliveryDTO): RouteDelivery {
  return { delivery_id: d.delivery_id, customer_name: d.customer_name, address: d.address, status: d.status };
}

function toDetail(d: DeliveryDTO): DeliveryDetail {
  return { delivery_id: d.delivery_id, customer_name: d.customer_name, address: d.address, phone: d.phone ?? "", status: d.status };
}

/** Injected em vez de importado — facilita o teste do replay. */
export function makeTransport(baseUrl: string, token: string) {
  return (item: QueueItem) =>
    postDeliveryAction(fetch, baseUrl, token, {
      deliveryId: item.deliveryId,
      action: item.kind === "location" ? "start" : item.kind,
      clientActionId: item.client_action_id,
      payload: item.payload,
    });
}

// ── Login (wired) ────────────────────────────────────────────

export function LoginScreenWired() {
  const setSession = useSessionStore((s) => s.setSession);

  const doLogin = useCallback(
    async (username: string, password: string) => {
      const { connection } = useConnectionStore.getState();
      if (!connection.baseUrl) throw new Error("offline");
      return mobileLogin(fetch, connection.baseUrl, username, password);
    },
    []
  );

  return <LoginScreen onLogin={setSession} doLogin={doLogin} />;
}

// ── Rota do dia (wired) ─────────────────────────────────────

export function RouteTodayScreenWired({ navigation }: NativeStackScreenProps<RootStackParamList, "RouteToday">) {
  const token = useSessionStore((s) => s.accessToken);
  const { connection } = useConnectionStore();
  const [deliveries, setDeliveries] = useState<RouteDelivery[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!token || !connection.baseUrl) {
      // Offline: mostra o último snapshot em memória (a fila reenvia as ações).
      return;
    }
    try {
      const list = await fetchMyDeliveries(fetch, connection.baseUrl, token);
      setDeliveries(list.map(toRoute));
      setError(null);
    } catch {
      setError("Sem conexão — mostrando dados salvos.");
    }
  }, [token, connection.baseUrl]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Replay da fila ao ficar online (C4.3: confirmação offline → sync depois).
  const flushQueue = useCallback(async () => {
    if (!token || !connection.baseUrl) return;
    await deliveryQueue.flush(makeTransport(connection.baseUrl, token));
    await reload();
  }, [token, connection.baseUrl, reload]);

  useEffect(() => {
    if (connection.mode !== "offline") void flushQueue();
  }, [connection.mode, flushQueue]);

  return (
    <View style={{ flex: 1 }}>
      {error ? <Text style={styles.offlineBanner}>{error}</Text> : null}
      <RouteTodayScreen
        deliveries={deliveries}
        onStartRoute={() => {
          /* serviço de background location nativo entra na F2.5 */
        }}
        onOpenDelivery={(deliveryId) => navigation.navigate("DeliveryDetail", { deliveryId })}
      />
    </View>
  );
}

// ── Detalhe da entrega (wired) ──────────────────────────────

export function DeliveryDetailScreenWired({ route }: NativeStackScreenProps<RootStackParamList, "DeliveryDetail">) {
  const { deliveryId } = route.params;
  const token = useSessionStore((s) => s.accessToken);
  const { connection } = useConnectionStore();
  const [delivery, setDelivery] = useState<DeliveryDetail | null>(null);

  useEffect(() => {
    let alive = true;
    if (!token || !connection.baseUrl) return;
    void fetchMyDeliveries(fetch, connection.baseUrl, token).then((list) => {
      if (!alive) return;
      const found = list.find((d) => d.delivery_id === deliveryId);
      if (found) setDelivery(toDetail(found));
    });
    return () => {
      alive = false;
    };
  }, [deliveryId, token, connection.baseUrl]);

  const enqueueAction = useCallback(
    (kind: "start" | "complete" | "fail", payload: Record<string, unknown> = {}) => {
      // Sempre enfileira: quando online, o flush dispara imediatamente;
      // quando offline, fica pending e vai no próximo flush (C4.3).
      deliveryQueue.enqueue(kind, deliveryId, payload);
      if (token && connection.baseUrl) {
        void deliveryQueue.flush(makeTransport(connection.baseUrl, token)).then(() => {
          setDelivery((prev) => (prev ? { ...prev, status: kind === "complete" ? "DELIVERED" : kind === "start" ? "EN_ROUTE" : prev.status } : prev));
        });
      } else {
        setDelivery((prev) => (prev ? { ...prev, status: kind === "complete" ? "DELIVERED" : kind === "start" ? "EN_ROUTE" : prev.status } : prev));
      }
    },
    [deliveryId, token, connection.baseUrl]
  );

  if (!delivery) {
    return (
      <View style={styles.splash}>
        <Text>Carregando entrega…</Text>
      </View>
    );
  }

  return (
    <DeliveryDetailScreen
      delivery={delivery}
      onStart={() => enqueueAction("start")}
      onComplete={() => enqueueAction("complete", { proof_type: "NONE" })}
      onFail={(reason) => enqueueAction("fail", { reason })}
    />
  );
}

const styles = StyleSheet.create({
  offlineBanner: { backgroundColor: "#f0ad4e", color: "#000", padding: 8, textAlign: "center" },
  splash: { flex: 1, alignItems: "center", justifyContent: "center" },
});
