/**
 * Banner — faixa de aviso no topo da tela (offline, erro de conexão…).
 */

import React, { type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, spacing, typography } from "../../theme";

export type BannerTone = "warning" | "info" | "danger";

interface Props {
  children: ReactNode;
  tone?: BannerTone;
}

const TONE: Record<BannerTone, { fg: string; bg: string }> = {
  warning: { fg: colors.warning, bg: colors.warningSoft },
  info: { fg: colors.info, bg: colors.infoSoft },
  danger: { fg: colors.danger, bg: colors.dangerSoft },
};

export default function Banner({ children, tone = "warning" }: Props) {
  const style = TONE[tone];
  return (
    <View style={[styles.banner, { backgroundColor: style.bg }]}>
      <Text style={[styles.text, { color: style.fg }]}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  text: { fontSize: typography.label, fontWeight: "600", textAlign: "center" },
});
