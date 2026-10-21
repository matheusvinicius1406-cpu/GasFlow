/**
 * Button — botão do design system (variantes espelhando o web).
 *
 * `primary` usa laranja com texto escuro (`--brand-primary-foreground`), igual
 * ao botão do desktop. Ghost/danger são contornos sutis para ações secundárias.
 */

import React, { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, type ViewStyle } from "react-native";

import { colors, radius, spacing, typography, shadows } from "../../theme";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "success";

interface Props {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  testID?: string;
  accessibilityLabel?: string;
  style?: ViewStyle;
}

const TONE: Record<ButtonVariant, { fg: string; bg: string; pressed: string; border: string }> = {
  primary: { fg: colors.background, bg: colors.brand, pressed: colors.brandHover, border: colors.brand },
  success: { fg: colors.background, bg: colors.success, pressed: "#1cae4f", border: colors.success },
  secondary: { fg: colors.foreground, bg: colors.surface, pressed: colors.surfaceHover, border: colors.borderStrong },
  ghost: { fg: colors.mutedForeground, bg: "transparent", pressed: colors.surfaceMuted, border: "transparent" },
  danger: { fg: colors.danger, bg: colors.dangerSoft, pressed: "rgba(239, 68, 68, 0.24)", border: colors.danger },
};

export default function Button({
  title,
  onPress,
  variant = "primary",
  loading = false,
  disabled = false,
  fullWidth = true,
  testID,
  accessibilityLabel,
  style,
}: Props) {
  const [pressed, setPressed] = useState(false);
  const tone = TONE[variant];
  const inactive = disabled || loading;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? title}
      accessibilityState={{ disabled: inactive, busy: loading }}
      disabled={inactive}
      onPress={onPress}
      onPressIn={() => setPressed(true)}
      onPressOut={() => setPressed(false)}
      testID={testID}
      style={[
        styles.base,
        variant === "primary" || variant === "success" ? shadows.card : null,
        { backgroundColor: pressed ? tone.pressed : tone.bg, borderColor: tone.border },
        fullWidth ? styles.fullWidth : styles.hug,
        inactive && styles.inactive,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator size="small" color={tone.fg} />
      ) : (
        <Text style={[styles.label, { color: tone.fg }]} numberOfLines={1}>
          {title}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 48,
    borderWidth: 1,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
  },
  fullWidth: { alignSelf: "stretch" },
  hug: { alignSelf: "auto" },
  inactive: { opacity: 0.55 },
  label: { fontSize: typography.body, fontWeight: "700", letterSpacing: 0.2 },
});
