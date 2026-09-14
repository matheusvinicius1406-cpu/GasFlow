/**
 * DeliveryDetailScreen — scaffold RN (prompt 5.2): dados do cliente, botões
 * "Navegar" (deep link Waze/Maps) e "Ligar", ações start/complete/fail
 * (todas passam pela fila offline — src/logic/offlineQueue.ts).
 */

import React from "react";
import { View, Text, Button, StyleSheet, Linking } from "react-native";

export interface DeliveryDetail {
  delivery_id: string;
  customer_name: string;
  address: string;
  phone: string;
  status: string;
}

interface Props {
  delivery: DeliveryDetail;
  onStart: () => void;
  onComplete: () => void;
  onFail: (reason: string) => void;
}

export default function DeliveryDetailScreen({ delivery, onStart, onComplete, onFail }: Props) {
  const mapsUrl = `https://waze.com/ul?q=${encodeURIComponent(delivery.address)}`;
  const callUrl = `tel:${delivery.phone}`;
  return (
    <View style={styles.container}>
      <Text style={styles.name}>{delivery.customer_name}</Text>
      <Text style={styles.line}>{delivery.address}</Text>
      <Text style={styles.line}>{delivery.phone}</Text>
      <View style={styles.row}>
        <Button title="Navegar" onPress={() => void Linking.openURL(mapsUrl)} />
        <Button title="Ligar" onPress={() => void Linking.openURL(callUrl)} />
      </View>
      <View style={styles.row}>
        <Button title="Iniciar entrega" onPress={onStart} disabled={delivery.status !== "ASSIGNED"} />
        <Button title="Concluir" onPress={onComplete} disabled={delivery.status !== "ARRIVED"} />
      </View>
      <Button title="Reportar problema" onPress={() => onFail("OTHER")} disabled={delivery.status !== "EN_ROUTE"} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  name: { fontSize: 20, fontWeight: "bold", marginBottom: 8 },
  line: { fontSize: 15, marginBottom: 4 },
  row: { flexDirection: "row", justifyContent: "space-around", marginVertical: 12 },
});
