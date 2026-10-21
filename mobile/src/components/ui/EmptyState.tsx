/**
 * EmptyState — estado vazio centralizado (rota sem entregas, sem conexão…).
 */

import React, { type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, typography } from "../../theme";

interface Props {
  glyph?: string;
  title: string;
  message?: string;
  children?: ReactNode;
}

export default function EmptyState({ glyph = "○", title, message, children }: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.glyphCircle}>
        <Text style={styles.glyph}>{glyph}</Text>
      </View>
      <Text style={styles.title}>{title}</Text>
      {message ? <Text style={styles.message}>{message}</Text> : null}
      {children ? <View style={styles.actions}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", paddingHorizontal: spacing.xl, paddingVertical: spacing.xxxl },
  glyphCircle: {
    width: 64,
    height: 64,
    borderRadius: radius.full,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.lg,
  },
  glyph: { fontSize: 26, color: colors.mutedForeground },
  title: { color: colors.foreground, fontSize: typography.h3, fontWeight: "700", marginBottom: spacing.xs },
  message: {
    color: colors.mutedForeground,
    fontSize: typography.bodySm,
    textAlign: "center",
    lineHeight: 20,
  },
  actions: { marginTop: spacing.xl, alignSelf: "stretch" },
});
