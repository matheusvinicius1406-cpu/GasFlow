/**
 * StatusChip — status da entrega como chip colorido (paleta do tema).
 */

import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, statusTheme, typography } from "../../theme";

interface Props {
  status: string;
  /** Ponto colorido à esquerda do rótulo. */
  dot?: boolean;
}

export default function StatusChip({ status, dot = true }: Props) {
  const theme = statusTheme[status] ?? {
    label: status,
    fg: colors.mutedForeground,
    bg: colors.surfaceMuted,
  };

  return (
    <View style={[styles.chip, { backgroundColor: theme.bg }]}>
      {dot ? <View style={[styles.dot, { backgroundColor: theme.fg }]} /> : null}
      <Text style={[styles.label, { color: theme.fg }]} numberOfLines={1}>
        {theme.label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    borderRadius: radius.full,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    gap: 6,
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  label: { fontSize: typography.caption, fontWeight: "700", letterSpacing: 0.2 },
});
