/**
 * Logo — marca unificada do GasFlow (PNG gerado por
 * `scripts/generate_brand_icons.py`).
 *
 * `mark` é a chama transparente (fundo escuro do app); `badge` é o ícone
 * completo com o quadradinho — usado onde a marca precisa de contorno.
 */

import React from "react";
import { Image, StyleSheet, Text, View } from "react-native";

import { colors, spacing, typography } from "../../theme";

interface Props {
  size?: number;
  variant?: "mark" | "badge";
  showWordmark?: boolean;
}

export default function Logo({ size = 72, variant = "mark", showWordmark = false }: Props) {
  const source = variant === "mark"
    ? require("../../../assets/logo-mark.png")
    : require("../../../assets/logo-badge.png");

  if (!showWordmark) {
    return <Image source={source} style={{ width: size, height: size }} resizeMode="contain" />;
  }

  return (
    <View style={styles.wrap}>
      <Image source={source} style={{ width: size, height: size }} resizeMode="contain" />
      <Text style={styles.wordmark}>GasFlow</Text>
      <Text style={styles.tagline}>Sistema Operacional de Entregas</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center" },
  wordmark: {
    color: colors.foreground,
    fontSize: typography.display,
    fontWeight: "800",
    letterSpacing: -0.5,
    marginTop: spacing.lg,
  },
  tagline: {
    color: colors.mutedForeground,
    fontSize: typography.label,
    letterSpacing: 0.4,
    marginTop: spacing.xs,
  },
});
