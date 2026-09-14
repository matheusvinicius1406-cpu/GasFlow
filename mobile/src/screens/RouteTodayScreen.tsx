/**
 * RouteTodayScreen — scaffold RN (prompt 5.2): rota do dia ordenada, contadores
 * e botão "Iniciar Rota" (ativa background location só dentro do horário —
 * src/logic/workHours.ts decide; o serviço nativo entra na Fase 2).
 */

import React from "react";
import { View, Text, FlatList, TouchableOpacity, StyleSheet } from "react-native";

export interface RouteDelivery {
  delivery_id: string;
  customer_name: string;
  address: string;
  status: string;
}

interface Props {
  deliveries: RouteDelivery[];
  onStartRoute: () => void;
  onOpenDelivery: (deliveryId: string) => void;
}

const STATUS_LABEL: Record<string, string> = {
  PENDING: "Pendente",
  ASSIGNED: "Atribuída",
  DISPATCHED: "Despachada",
  EN_ROUTE: "Em rota",
  ARRIVED: "No local",
  DELIVERED: "Entregue",
  FAILED: "Falhou",
};

export default function RouteTodayScreen({ deliveries, onStartRoute, onOpenDelivery }: Props) {
  const done = deliveries.filter((d) => d.status === "DELIVERED").length;
  return (
    <View style={styles.container}>
      <Text style={styles.counter}>
        {done} de {deliveries.length} concluídas
      </Text>
      <TouchableOpacity style={styles.button} onPress={onStartRoute}>
        <Text style={styles.buttonText}>Iniciar Rota</Text>
      </TouchableOpacity>
      <FlatList
        data={deliveries}
        keyExtractor={(d) => d.delivery_id}
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.card} onPress={() => onOpenDelivery(item.delivery_id)}>
            <Text style={styles.customer}>{item.customer_name}</Text>
            <Text style={styles.address}>{item.address}</Text>
            <Text style={styles.status}>{STATUS_LABEL[item.status] ?? item.status}</Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  counter: { fontSize: 16, marginBottom: 8 },
  button: { backgroundColor: "#0a7", borderRadius: 8, padding: 14, alignItems: "center", marginBottom: 12 },
  buttonText: { color: "#fff", fontWeight: "bold" },
  card: { borderWidth: 1, borderColor: "#ddd", borderRadius: 8, padding: 12, marginBottom: 8 },
  customer: { fontSize: 16, fontWeight: "600" },
  address: { color: "#555" },
  status: { color: "#070", marginTop: 4 },
});
