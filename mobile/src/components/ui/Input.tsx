/**
 * Input — campo de formulário com label, erro e olho de senha.
 *
 * Borda muda de cor no foco (estado interno) para dar o mesmo feedback visual
 * do input do web (`--ring` laranja).
 */

import React, { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View, type TextInputProps } from "react-native";

import { colors, radius, spacing, typography } from "../../theme";

interface Props extends Omit<TextInputProps, "style"> {
  label?: string;
  error?: string | null;
  hint?: string;
}

export default function Input({ label, error, hint, secureTextEntry, ...rest }: Props) {
  const [focused, setFocused] = useState(false);
  const [hidden, setHidden] = useState(true);

  return (
    <View style={styles.wrap}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <View
        style={[
          styles.field,
          focused && styles.fieldFocused,
          Boolean(error) && styles.fieldError,
        ]}
      >
        <TextInput
          {...rest}
          secureTextEntry={secureTextEntry && hidden}
          onFocus={(e) => {
            setFocused(true);
            rest.onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            rest.onBlur?.(e);
          }}
          placeholderTextColor={colors.mutedForeground}
          style={styles.input}
        />
        {secureTextEntry ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={hidden ? "Mostrar senha" : "Ocultar senha"}
            onPress={() => setHidden((v) => !v)}
            hitSlop={8}
            style={styles.toggle}
          >
            <Text style={styles.toggleText}>{hidden ? "Mostrar" : "Ocultar"}</Text>
          </Pressable>
        ) : null}
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!error && hint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: spacing.lg },
  label: {
    color: colors.foreground,
    fontSize: typography.label,
    fontWeight: "600",
    marginBottom: spacing.xs + 2,
  },
  field: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    minHeight: 48,
    paddingHorizontal: spacing.lg,
  },
  fieldFocused: { borderColor: colors.brand },
  fieldError: { borderColor: colors.danger },
  input: {
    flex: 1,
    color: colors.foreground,
    fontSize: typography.body,
    paddingVertical: spacing.md,
  },
  toggle: { paddingLeft: spacing.md, height: "100%", justifyContent: "center" },
  toggleText: { color: colors.brand, fontSize: typography.label, fontWeight: "600" },
  error: { color: colors.danger, fontSize: typography.label, marginTop: spacing.xs },
  hint: { color: colors.mutedForeground, fontSize: typography.caption, marginTop: spacing.xs },
});
