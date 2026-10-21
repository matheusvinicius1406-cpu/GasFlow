/**
 * RouteTodayScreen — rota do dia ordenada, progresso do dia e botão
 * "Iniciar Rota" (ativa background location só dentro do horário —
 * src/logic/workHours.ts decide; o serviço nativo entra na Fase 2).
 *
 * Visual: hero com progresso + km do dia, lista em cards com chip de status.
 */

import React from "react";
import { FlatList, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";
import StatusChip from "../components/ui/StatusChip";
import { colors, radius, spacing, typography } from "../theme";

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
  /** Fase 7.5: km percorridos hoje (vem do /driver/me). */
  todayDistanceKm?: number;
}

export default function RouteTodayScreen({
  deliveries,
  onStartRoute,
  onOpenDelivery,
  todayDistanceKm,
}: Props) {
  const total = deliveries.length;
  const done = deliveries.filter((d) => d.status === "DELIVERED").length;
  const percent = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <View style={styles.screen}>
      <FlatList
        data={deliveries}
        keyExtractor={(d) => d.delivery_id}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        ListHeaderComponent={
          <View style={styles.hero}>
            <Card style={styles.heroCard}>
              <View style={styles.heroTop}>
                <View style={styles.heroText}>
                  <Text style={styles.heroLabel}>Progresso de hoje</Text>
                  <Text style={styles.heroValue}>
                    {done}
                    <Text style={styles.heroTotal}> de {total} entregas</Text>
                  </Text>
                </View>
                <View style={styles.percentBadge}>
                  <Text style={styles.percentText}>{percent}%</Text>
                </View>
              </View>

              <View style={styles.track}>
                <View style={[styles.trackFill, { width: `${percent}%` }]} />
              </View>

              {typeof todayDistanceKm === "number" ? (
                <View style={styles.kmRow}>
                  <View style={styles.kmDot} />
                  <Text style={styles.kmText}>
                    Hoje: <Text style={styles.kmValue}>{todayDistanceKm.toFixed(1)} km</Text> percorridos
                  </Text>
                </View>
              ) : null}

              <View style={styles.heroAction}>
                <Button
                  title="Iniciar Rota"
                  onPress={onStartRoute}
                  testID="start-route"
                  accessibilityLabel="Iniciar rota do dia"
                />
              </View>
            </Card>

            <Text style={styles.sectionTitle}>
              Entregas {total > 0 ? `(${total})` : ""}
            </Text>
          </View>
        }
        ListEmptyComponent={
          <EmptyState
            glyph="✓"
            title="Nenhuma entrega por aqui"
            message="Quando a base atribuir entregas, elas aparecem nesta lista na ordem da rota."
          />
        }
        renderItem={({ item, index }) => (
          <TouchableOpacity
            style={styles.item}
            onPress={() => onOpenDelivery(item.delivery_id)}
            accessibilityRole="button"
            accessibilityLabel={`Entrega para ${item.customer_name}`}
            activeOpacity={0.7}
          >
            <View style={styles.itemIndex}>
              <Text style={styles.itemIndexText}>{index + 1}</Text>
            </View>
            <View style={styles.itemBody}>
              <Text style={styles.customer} numberOfLines={1}>
                {item.customer_name}
              </Text>
              <Text style={styles.address} numberOfLines={2}>
                {item.address}
              </Text>
              <StatusChip status={item.status} />
            </View>
            <Text style={styles.chevron}>›</Text>
          </TouchableOpacity>
        )}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxxl },
  hero: { paddingTop: spacing.lg, paddingBottom: spacing.sm },
  heroCard: { padding: spacing.lg },
  heroTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  heroText: { flex: 1 },
  heroLabel: {
    color: colors.mutedForeground,
    fontSize: typography.caption,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  heroValue: { color: colors.foreground, fontSize: 32, fontWeight: "800", marginTop: spacing.xs },
  heroTotal: { color: colors.mutedForeground, fontSize: typography.h3, fontWeight: "600" },
  percentBadge: {
    backgroundColor: colors.brandSoft,
    borderRadius: radius.full,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderWidth: 1,
    borderColor: colors.brand,
  },
  percentText: { color: colors.brand, fontSize: typography.label, fontWeight: "800" },
  track: {
    height: 8,
    borderRadius: radius.full,
    backgroundColor: colors.surfaceMuted,
    overflow: "hidden",
    marginTop: spacing.lg,
  },
  trackFill: { height: "100%", borderRadius: radius.full, backgroundColor: colors.brand },
  kmRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md },
  kmDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.info },
  kmText: { color: colors.mutedForeground, fontSize: typography.label },
  kmValue: { color: colors.foreground, fontWeight: "700" },
  heroAction: { marginTop: spacing.lg },
  sectionTitle: {
    color: colors.foreground,
    fontSize: typography.h3,
    fontWeight: "700",
    marginTop: spacing.xl,
    marginBottom: spacing.md,
  },
  item: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.xl,
    padding: spacing.lg,
  },
  itemIndex: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.surfaceMuted,
    alignItems: "center",
    justifyContent: "center",
  },
  itemIndexText: { color: colors.foreground, fontSize: typography.label, fontWeight: "800" },
  itemBody: { flex: 1, gap: spacing.xs },
  customer: { color: colors.foreground, fontSize: typography.h3, fontWeight: "700" },
  address: { color: colors.mutedForeground, fontSize: typography.bodySm, lineHeight: 19 },
  chevron: { color: colors.mutedForeground, fontSize: 26, fontWeight: "400", marginTop: -2 },
  separator: { height: spacing.sm },
});
