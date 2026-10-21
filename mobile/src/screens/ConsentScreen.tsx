/**
 * ConsentScreen — consentimento LGPD de rastreamento (F2 do spec, decisão B3).
 *
 * Bloqueante: sem aceitar, o entregador não usa o app (nenhuma rota à frente).
 * Registra data + versão do termo via useSessionStore.acceptConsent().
 * Texto sem jargão: o que coleta, quando, por quanto tempo e como desligar.
 */

import React, { useState } from "react";
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Logo from "../components/ui/Logo";
import { colors, radius, spacing, typography } from "../theme";
import { useSessionStore } from "../logic/session";

const BULLETS: { label: string; text: string }[] = [
  { label: "O quê", text: "sua posição GPS (latitude/longitude e velocidade)." },
  { label: "Quando", text: "só dentro do seu horário de trabalho e com o app aberto." },
  { label: "Por quanto tempo", text: "guardamos as posições por 90 dias e depois apagamos." },
  { label: "Quem vê", text: "apenas a base, para acompanhar as entregas." },
];

export default function ConsentScreen() {
  const [checked, setChecked] = useState(false);
  const acceptConsent = useSessionStore((s) => s.acceptConsent);

  return (
    <View style={styles.screen} testID="consent-screen">
      <View style={styles.header}>
        <Logo size={52} />
        <Text style={styles.title}>Rastreamento durante o trabalho</Text>
        <Text style={styles.subtitle}>
          Para organizar as entregas, o GasFlow usa a <Text style={styles.bold}>localização do seu
          celular</Text> enquanto você está em rota.
        </Text>
      </View>

      <Card padded={false} style={styles.card}>
        <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
          {BULLETS.map((bullet) => (
            <View key={bullet.label} style={styles.bulletRow}>
              <View style={styles.bulletDot} />
              <Text style={styles.bulletText}>
                <Text style={styles.bulletLabel}>{bullet.label}: </Text>
                {bullet.text}
              </Text>
            </View>
          ))}
          <Text style={styles.note}>
            Você pode recusar. Sem isso, dá para usar o app, mas a base não acompanha sua rota no mapa.
          </Text>
        </ScrollView>
      </Card>

      <TouchableOpacity
        style={styles.checkboxRow}
        onPress={() => setChecked((v) => !v)}
        accessibilityRole="checkbox"
        accessibilityState={{ checked }}
        testID="consent-checkbox"
      >
        <View style={[styles.checkbox, checked && styles.checkboxOn]}>
          {checked ? <Text style={styles.checkGlyph}>✓</Text> : null}
        </View>
        <Text style={styles.checkboxLabel}>
          Li e concordo com a coleta de localização durante meu horário de trabalho.
        </Text>
      </TouchableOpacity>

      <Button
        title="Aceitar e continuar"
        disabled={!checked}
        onPress={() => acceptConsent()}
        testID="consent-accept"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.xxl,
    justifyContent: "center",
  },
  header: { alignItems: "center", marginBottom: spacing.xl },
  title: {
    color: colors.foreground,
    fontSize: typography.h2,
    fontWeight: "800",
    textAlign: "center",
    marginTop: spacing.lg,
  },
  subtitle: {
    color: colors.mutedForeground,
    fontSize: typography.bodySm,
    textAlign: "center",
    lineHeight: 20,
    marginTop: spacing.sm,
  },
  bold: { color: colors.foreground, fontWeight: "700" },
  card: { marginBottom: spacing.lg },
  scroll: { maxHeight: 260 },
  scrollContent: { padding: spacing.lg, gap: spacing.md },
  bulletRow: { flexDirection: "row", gap: spacing.sm },
  bulletDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.brand,
    marginTop: 7,
  },
  bulletText: { flex: 1, color: colors.mutedForeground, fontSize: typography.bodySm, lineHeight: 20 },
  bulletLabel: { color: colors.foreground, fontWeight: "700" },
  note: {
    color: colors.mutedForeground,
    fontSize: typography.label,
    lineHeight: 19,
    fontStyle: "italic",
    marginTop: spacing.xs,
  },
  checkboxRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginBottom: spacing.xl,
    paddingVertical: spacing.sm,
  },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: radius.sm,
    borderWidth: 2,
    borderColor: colors.borderStrong,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  checkboxOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  checkGlyph: { color: colors.background, fontSize: 14, fontWeight: "900", lineHeight: 16 },
  checkboxLabel: { flex: 1, color: colors.foreground, fontSize: typography.label, lineHeight: 19 },
});
