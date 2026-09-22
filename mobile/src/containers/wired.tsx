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

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { View, Text, StyleSheet } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import type { RootStackParamList } from "../navigation/RootNavigator";
import LoginScreen from "../screens/LoginScreen";
import ChangePasswordScreen from "../screens/ChangePasswordScreen";
import RouteTodayScreen, { type RouteDelivery } from "../screens/RouteTodayScreen";
import DeliveryDetailScreen, { type DeliveryDetail } from "../screens/DeliveryDetailScreen";
import { useSessionStore } from "../logic/session";
import {
  operatorLogin,
  changePassword,
  fetchMyDeliveries,
  fetchDriverMe,
  driverWsUrl,
  postDeliveryAction,
  postDriverLocation,
  postDriverLocationRelay,
  type DeliveryDTO,
} from "../logic/api";
import { attachDriverSocket, reconnectDelay } from "../logic/realtime";
import { OfflineQueue, type QueueItem, type QueueStorage } from "../logic/offlineQueue";
import { resolveConnection, type ResolvedConnection } from "../logic/connection";
import { TrackingController, type TrackingDeps, type GpsPosition } from "../logic/tracking";
import { createBackgroundTracking } from "../logic/backgroundTracking";

export type RouteTodayScreenWiredProps = NativeStackScreenProps<RootStackParamList, "RouteToday">;
export type DeliveryDetailScreenWiredProps = NativeStackScreenProps<RootStackParamList, "DeliveryDetail">;

/** Url de conexão ativa — setada pelo app container a partir do resolveConnection. */
interface ConnectionStore {
  connection: ResolvedConnection;
  /** Token compartilhado do relay (X-Relay-Token) — usado pelo rastreamento na nuvem. */
  relayToken: string;
  setConnection: (c: ResolvedConnection, relayToken?: string) => void;
}
import { create } from "zustand";
export const useConnectionStore = create<ConnectionStore>((set) => ({
  connection: { mode: "offline", baseUrl: null },
  relayToken: "",
  setConnection: (connection, relayToken = "") => set({ connection, relayToken }),
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

// ── Rastreamento (F2.5) ──────────────────────────────────────

/**
 * Estado de runtime do rastreamento — preenchido pelo /driver/me (intervalo
 * e janela LGPD do servidor) e pelas entregas visíveis (statuses p/ o gate).
 * workWindow null ⇒ fail-closed (nada coleta até o servidor informar).
 */
const trackingRuntime = {
  statuses: [] as string[],
  workWindow: null as string | null,
  intervalSeconds: 120,
  relayToken: "",
  driverId: "",
  tenantId: "default",
};

/** geolocation — import direto (lib nativa autolinkada no shell android/). */
import Geolocation from "@react-native-community/geolocation";

function getGeolocation(): {
  watchPosition: (ok: (p: { coords: { latitude: number; longitude: number; accuracy?: number | null; speed?: number | null; heading?: number | null }; timestamp: number }) => void, err: (e: { message?: string; code?: number }) => void, opts?: Record<string, unknown>) => number;
  clearWatch: (id: number) => void;
} {
  return Geolocation;
}

/**
 * Fase 5: captura em segundo plano.
 *
 * A lib nativa (@ikolvi/tracelet) entra atrás do adaptador; se ela não
 * estiver disponível (autolink pendente, iOS sem pod), o adaptador cai no
 * `foregroundWatch` abaixo — o rastreio continua funcionando em primeiro plano.
 */
const foregroundWatch = (onPosition: (pos: GpsPosition) => void, onError: (e: Error) => void) => {
  const geo = getGeolocation();
  const watchId = geo.watchPosition(
    (p) =>
      onPosition({
        latitude: p.coords.latitude,
        longitude: p.coords.longitude,
        accuracy: p.coords.accuracy ?? undefined,
        speed: p.coords.speed ?? undefined,
        bearing: p.coords.heading ?? undefined,
        timestamp: p.timestamp,
      }),
    (e) => onError(new Error(e.message ?? `GPS erro ${e.code ?? "?"}`)),
    { enableHighAccuracy: true, distanceFilter: 10, timeout: 15_000, maximumAge: 30_000 },
  );
  return () => geo.clearWatch(watchId);
};

const backgroundTracking = createBackgroundTracking({
  // TODO(Fase 5 — background real): passa `tracelet: Tracelet` quando a lib
  // estiver utilizável. Hoje ela está BLOQUEADA (ver mobile/README.md):
  // `@ikolvi/tracelet@0.1.0-alpha.1` é publicada sem o submódulo `core`
  // (`Unresolved reference: core` no :ikolvi_tracelet:compileReleaseKotlin) e
  // com um `<service>` fora do `<application>` no manifest (AAPT rejeita).
  // Com `null`, o adaptador usa o foregroundWatch abaixo — mesmo rastreio de
  // antes, agora atrás da costura que liga o background quando ele voltar.
  tracelet: null,
  fallback: foregroundWatch,
  log: (level, message) => {
    if (level === "warn") console.warn(`[tracking] ${message}`);
    else console.log(`[tracking] ${message}`);
  },
});

let trackingController: TrackingController | null = null;

/** Controller singleton do rastreamento (gate B2 + cadência + roteamento). */
export function getTrackingController(): TrackingController {
  if (trackingController) return trackingController;
  const deps: TrackingDeps = {
    fetchFn: fetch,
    now: () => Date.now(),
    log: (level, message) => {
      if (level === "warn") console.warn(`[tracking] ${message}`);
      else console.log(`[tracking] ${message}`);
    },
    getSnapshot: () => ({
      statuses: trackingRuntime.statuses,
      workWindow: trackingRuntime.workWindow,
      intervalSeconds: trackingRuntime.intervalSeconds,
      token: useSessionStore.getState().accessToken ?? "",
      relayToken: trackingRuntime.relayToken,
      driverId: trackingRuntime.driverId || useSessionStore.getState().driverId || "",
      tenantId: trackingRuntime.tenantId,
      connection: useConnectionStore.getState().connection,
    }),
    // Fase 5: background real via @ikolvi/tracelet (com fallback de
    // primeiro plano). O gate/cadência/fila continuam no controller.
    watch: (onPosition, onError) => backgroundTracking.watch(onPosition, onError),
    queue: deliveryQueue,
  };
  trackingController = new TrackingController(deps);
  return trackingController;
}

/**
 * Liga o gate do rastreamento às entregas visíveis (mesma semântica B2 do
 * desktop) e ao /driver/me (intervalo + janela LGPD). Usar em UMA tela viva
 * (RouteToday) — o controller é singleton e sobrevive à navegação.
 */
export function useTrackingGate(deliveries: RouteDelivery[]): void {
  const token = useSessionStore((s) => s.accessToken);
  const { connection, relayToken } = useConnectionStore();
  const statusesKey = useMemo(() => deliveries.map((d) => d.status).join(","), [deliveries]);

  // Perfil do entregador: intervalo configurável + janela LGPD do servidor.
  useEffect(() => {
    if (!token || connection.mode === "offline" || !connection.baseUrl) return;
    let alive = true;
    void fetchDriverMe(fetch, connection.baseUrl, token)
      .then((me) => {
        if (!alive) return;
        trackingRuntime.workWindow = me.work_hours ?? null;
        trackingRuntime.intervalSeconds = me.tracking_interval_seconds;
        trackingRuntime.driverId = me.driver_id;
        trackingRuntime.tenantId = me.tenant_id || "default";
      })
      .catch(() => undefined); // offline p/ /me: mantém fail-closed
    return () => {
      alive = false;
    };
  }, [token, connection.mode, connection.baseUrl]);

  useEffect(() => {
    trackingRuntime.statuses = statusesKey ? statusesKey.split(",") : [];
    trackingRuntime.relayToken = relayToken;
  }, [statusesKey, relayToken]);

  // Sessão controla o ciclo de vida: sem login ⇒ rastreamento parado.
  useEffect(() => {
    const controller = getTrackingController();
    if (token) controller.start();
    else controller.stop();
  }, [token]);
}

/**
 * Fase 5.3 — geofencing por entrega.
 *
 * Registra um fence (~150 m). No ENTER, a UI deve apenas SUGERIR "marcar como
 * chegou" — nunca concluir a entrega sozinho.
 *
 * TODO(geofence-enter): ligar o evento de entry do fence ao botão "cheguei"
 * na tela da rota. O DTO atual (`RouteDelivery`) não carrega lat/lng do
 * endereço, então quem chamar precisa passar as coordenadas da entrega.
 */
export function registerDeliveryGeofence(delivery: {
  delivery_id: string;
  latitude: number;
  longitude: number;
}): Promise<boolean> {
  return backgroundTracking.addDeliveryGeofence({
    id: delivery.delivery_id,
    latitude: delivery.latitude,
    longitude: delivery.longitude,
  });
}

function toRoute(d: DeliveryDTO): RouteDelivery {
  return { delivery_id: d.delivery_id, customer_name: d.customer_name, address: d.address, status: d.status };
}

function toDetail(d: DeliveryDTO): DeliveryDetail {
  return { delivery_id: d.delivery_id, customer_name: d.customer_name, address: d.address, phone: d.phone ?? "", status: d.status };
}

/**
 * Transporte da fila (F2.5: agora também roteia posições "location").
 * Lê os stores no momento do envio (a conexão pode ter mudado desde o
 * enqueue): lan → backend com JWT · cloud → relay com X-Relay-Token.
 * Lança em falha — o OfflineQueue aplica o backoff.
 */
export function makeTransport() {
  return async (item: QueueItem) => {
    const { connection, relayToken } = useConnectionStore.getState();
    const { accessToken, driverId } = useSessionStore.getState();
    const token = accessToken ?? "";

    if (item.kind === "location") {
      if (connection.mode === "lan" && connection.baseUrl && token) {
        await postDriverLocation(fetch, connection.baseUrl, token, {
          latitude: Number(item.payload.latitude),
          longitude: Number(item.payload.longitude),
          accuracy: item.payload.accuracy as number | undefined,
          speed: item.payload.speed as number | undefined,
          bearing: item.payload.bearing as number | undefined,
        });
        return;
      }
      if (connection.mode === "cloud" && connection.baseUrl && relayToken && driverId) {
        await postDriverLocationRelay(fetch, connection.baseUrl, relayToken, {
          driverId,
          tenantId: "default",
          positions: [
            {
              lat: Number(item.payload.latitude),
              lng: Number(item.payload.longitude),
              speed: (item.payload.speed as number) ?? null,
              heading: (item.payload.bearing as number) ?? null,
              accuracy: (item.payload.accuracy as number) ?? null,
              recorded_at: (item.payload.recorded_at as string) ?? null,
            },
          ],
        });
        return;
      }
      throw new Error("offline — posição aguarda canal");
    }

    if (!item.deliveryId) throw new Error("ação sem deliveryId");
    await postDeliveryAction(fetch, connection.baseUrl ?? "", token, {
      deliveryId: item.deliveryId,
      action: item.kind,
      clientActionId: item.client_action_id,
      payload: item.payload,
    });
  };
}

// ── Login (wired) ────────────────────────────────────────────
//
// Autentica na auth PRINCIPAL (`/auth/login`): o entregador é um usuário com
// role DRIVER. O `must_change_password` resultante decide se o app vai para a
// tela de troca antes de qualquer tela do entregador (gate no RootNavigator).

export function LoginScreenWired() {
  const setSession = useSessionStore((s) => s.setSession);

  const doLogin = useCallback(
    async (username: string, password: string) => {
      const { connection } = useConnectionStore.getState();
      if (!connection.baseUrl) throw new Error("Sem conexão com o depósito.");
      const result = await operatorLogin(fetch, connection.baseUrl, username, password);
      const access = result.access_token || result.token || "";
      // driver_id é resolvido pelo /driver/me; aqui só a sessão.
      setSession({ access_token: access, refresh_token: result.refresh_token, driver_id: "" });
      useSessionStore.setState({
        username,
        mustChangePassword: Boolean(result.user?.must_change_password),
      });
      return { access_token: access, refresh_token: result.refresh_token, driver_id: "" };
    },
    [setSession]
  );

  // A navegação reage ao store (accessToken); o onLogin é redundante aqui.
  return <LoginScreen onLogin={() => undefined} doLogin={doLogin} />;
}

// ── Troca de senha obrigatória (wired) ───────────────────────

export function ChangePasswordScreenWired() {
  const accessToken = useSessionStore((s) => s.accessToken);
  const username = useSessionStore((s) => s.username);
  const clearSession = useSessionStore((s) => s.clearSession);
  const setMustChangePassword = useSessionStore((s) => s.setMustChangePassword);

  const onSubmit = useCallback(
    async (currentPassword: string, newPassword: string) => {
      const { connection } = useConnectionStore.getState();
      if (!connection.baseUrl || !accessToken) throw new Error("Sem conexão com o depósito.");
      await changePassword(fetch, connection.baseUrl, accessToken, currentPassword, newPassword);
      // Backend limpou a flag; o gate libera as telas do entregador.
      setMustChangePassword(false);
    },
    [accessToken, setMustChangePassword]
  );

  return <ChangePasswordScreen username={username} onSubmit={onSubmit} onLogout={clearSession} />;
}

// ── Realtime (wired) ─────────────────────────────────────────
//
// Conecta no canal `driver:{driver_id}` do backend. Um fechamento 4003
// ("Password change required") é estado de app → levanta o gate, sem
// reconectar em loop.

export function useDriverRealtime(): void {
  const token = useSessionStore((s) => s.accessToken);
  const connection = useConnectionStore((s) => s.connection);
  const setMustChangePassword = useSessionStore((s) => s.setMustChangePassword);
  const socketRef = useRef<{ close: () => void } | null>(null);

  useEffect(() => {
    if (!token || connection.mode === "offline" || !connection.baseUrl) return;

    let closed = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (closed) return;
      const socket = new WebSocket(driverWsUrl(connection.baseUrl as string, token));
      socketRef.current = socket;
      attachDriverSocket({
        socket,
        onOpen: () => {
          attempt = 0;
        },
        onPasswordChangeRequired: () => setMustChangePassword(true),
        onClose: () => {
          if (closed) return;
          attempt += 1;
          timer = setTimeout(connect, reconnectDelay(attempt));
        },
        log: (message) => console.log(`[ws] ${message}`),
      });
    };
    connect();

    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [token, connection.mode, connection.baseUrl, setMustChangePassword]);
}

// ── Rota do dia (wired) ─────────────────────────────────────

export function RouteTodayScreenWired({ navigation }: NativeStackScreenProps<RootStackParamList, "RouteToday">) {
  const token = useSessionStore((s) => s.accessToken);
  const { connection } = useConnectionStore();
  const [deliveries, setDeliveries] = useState<RouteDelivery[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Fase 7.5: km do dia (calculado do histórico no backend).
  const [todayDistanceKm, setTodayDistanceKm] = useState<number | null>(null);

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

  const reloadDistance = useCallback(async () => {
    if (!token || !connection.baseUrl) return;
    try {
      const me = await fetchDriverMe(fetch, connection.baseUrl, token);
      setTodayDistanceKm(me.today_distance_km ?? 0);
    } catch {
      // offline: mantém o último valor conhecido na tela
    }
  }, [token, connection.baseUrl]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    void reloadDistance();
    const timer = setInterval(() => void reloadDistance(), 60_000);
    return () => clearInterval(timer);
  }, [reloadDistance]);

  // Replay da fila ao ficar online (C4.3: confirmação offline → sync depois).
  const flushQueue = useCallback(async () => {
    if (useConnectionStore.getState().connection.mode === "offline") return;
    await deliveryQueue.flush(makeTransport());
    await reload();
  }, [reload]);

  useEffect(() => {
    if (connection.mode !== "offline") void flushQueue();
  }, [connection.mode, flushQueue]);

  // F2.5: gate de rastreamento acompanha as entregas desta tela (auto on/off).
  useTrackingGate(deliveries);
  // Realtime: eventos do canal driver:{driver_id} + gate de senha (4003).
  useDriverRealtime();

  return (
    <View style={{ flex: 1 }}>
      {error ? <Text style={styles.offlineBanner}>{error}</Text> : null}
      <RouteTodayScreen
        deliveries={deliveries}
        todayDistanceKm={todayDistanceKm ?? undefined}
        onStartRoute={() => {
          // F2.5: rastreio já liga sozinho com entrega atribuída (gate B2);
          // o botão antecipa/força a vontade do entregador.
          getTrackingController().setOverride(true);
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
      if (connection.mode !== "offline") {
        void deliveryQueue.flush(makeTransport()).then(() => {
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
