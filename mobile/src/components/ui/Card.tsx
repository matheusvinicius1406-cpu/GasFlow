/**
 * Card — superfície de conteúdo (surface + borda + raio), igual ao card do web.
 */

import React, { type ReactNode } from "react";
import { StyleSheet, View, type ViewStyle } from "react-native";

import { colors, radius, shadows, spacing } from "../../theme";

interface Props {
  children: ReactNode;
  padded?: boolean;
  style?: ViewStyle;
}

export default function Card({ children, padded = true, style }: Props) {
  return <View style={[styles.card, padded && styles.padded, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.xl,
    ...shadows.card,
  },
  padded: { padding: spacing.lg },
});
