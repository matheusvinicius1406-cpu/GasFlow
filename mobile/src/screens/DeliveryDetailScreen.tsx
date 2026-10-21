/**
 * DeliveryDetailScreen — dados do cliente, ações rápidas (Navegar/Ligar) e as
 * ações do fluxo start/complete/fail (todas passam pela fila offline —
 * src/logic/offlineQueue.ts).
 *
 * Cada ação só habilita no status em que ela é válida, e o rodapé explica que
 * sem sinal a ação é salva e sincroniza sozinha.
 */

import React from "react";
import { Linking, ScrollView, StyleSheet, Text, View } from "react-native";

import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";
import StatusChip from "../components/ui/StatusChip";
import { colors, radius, spacing, typography } from "../theme";

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
  const callUrl = `tel:${delivery.phone.replace(/[^\d+]/g, "")}`;

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      <Card style={styles.card}>
        <View style={styles.cardHead}>
          <Text style={styles.name}>{delivery.customer_name}</Text>
          <StatusChip status={delivery.status} />
        </View>

        <View style={styles.infoRow}>
          <View style={styles.infoBadge}>
            <Text style={styles.infoGlyph}>⌖</Text>
          </View>
          <Text style={styles.infoText}>{delivery.address}</Text>
        </View>

        {delivery.phone ? (
          <View style={styles.infoRow}>
            <View style={styles.infoBadge}>
              <Text style={styles.infoGlyph}>☎</Text>
            </View>
            <Text style={styles.infoText}>{delivery.phone}</Text>
          </View>
        ) : null}

        <View style={styles.quickActions}>
          <Button
            title="Navegar"
            variant="secondary"
            fullWidth={false}
            style={styles.quickButton}
            onPress={() => void Linking.openURL(mapsUrl)}
            accessibilityLabel="Abrir rota no Waze"
          />
          <Button
            title="Ligar"
            variant="secondary"
            fullWidth={false}
            style={styles.quickButton}
            onPress={() => void Linking.openURL(callUrl)}
            accessibilityLabel="Ligar para o cliente"
          />
        </View>
      </Card>

      <Text style={styles.sectionTitle}>Andamento da entrega</Text>
      <Card style={styles.card}>
        <Button
          title="Iniciar entrega"
          onPress={onStart}
          disabled={delivery.status !== "ASSIGNED"}
          testID="delivery-start"
        />
        <View style={styles.gap} />
        <Button
          title="Concluir entrega"
          variant="success"
          onPress={onComplete}
          disabled={delivery.status !== "ARRIVED"}
          testID="delivery-complete"
        />
        <View style={styles.gap} />
        <Button
          title="Reportar problema"
          variant="danger"
          onPress={() => onFail("OTHER")}
          disabled={delivery.status !== "EN_ROUTE"}
          testID="delivery-fail"
        />
      </Card>

      <Text style={styles.footnote}>
        Sem sinal? A ação fica salva no celular e é enviada assim que a conexão voltar.
      </Text>
    </ScrollView>
  );
}

/** Tela de carregamento antes do dado chegar (usada pelo contêiner wired). */
export function DeliveryLoading() {
  return (
    <View style={styles.loading}>
      <EmptyState glyph="◌" title="Carregando entrega…" message="Buscando os dados no servidor." />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, paddingBottom: spacing.xxxl },
  card: { padding: spacing.lg },
  cardHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md,
    marginBottom: spacing.lg,
  },
  name: { flex: 1, color: colors.foreground, fontSize: typography.h2, fontWeight: "800" },
  infoRow: { flexDirection: "row", gap: spacing.md, marginBottom: spacing.md, alignItems: "flex-start" },
  infoBadge: {
    width: 32,
    height: 32,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceMuted,
    alignItems: "center",
    justifyContent: "center",
  },
  infoGlyph: { color: colors.brand, fontSize: 15, fontWeight: "700" },
  infoText: {
    flex: 1,
    color: colors.foreground,
    fontSize: typography.body,
    lineHeight: 21,
    paddingTop: 5,
  },
  quickActions: { flexDirection: "row", gap: spacing.md, marginTop: spacing.sm },
  quickButton: { flex: 1 },
  sectionTitle: {
    color: colors.foreground,
    fontSize: typography.h3,
    fontWeight: "700",
    marginTop: spacing.xl,
    marginBottom: spacing.md,
  },
  gap: { height: spacing.sm },
  footnote: {
    color: colors.mutedForeground,
    fontSize: typography.caption,
    textAlign: "center",
    lineHeight: 17,
    marginTop: spacing.xl,
  },
  loading: { flex: 1, backgroundColor: colors.background, justifyContent: "center" },
});
