/**
 * ChangePasswordScreen — troca obrigatória no primeiro acesso.
 *
 * Gate P0 (3.8): reset do admin seta `must_change_password`; o app bloqueia
 * aqui até `POST /auth/change-password` limpar a flag no backend. Espelha a
 * política mínima do backend (8+ chars, 1 maiúscula, 1 minúscula, 1 dígito).
 *
 * Apresentação pura (callbacks) — o comportamento fica no contêiner wired.
 * A checklist de requisitos acompanha o que está sendo digitado.
 */

import React, { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Logo from "../components/ui/Logo";
import { colors, radius, spacing, typography } from "../theme";

interface Props {
  username?: string | null;
  onSubmit: (currentPassword: string, newPassword: string) => Promise<void>;
  onLogout: () => void;
}

const PASSWORD_PATTERN = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$/;

export function validateNewPassword(currentPassword: string, newPassword: string, confirm: string): string {
  if (newPassword.length < 8) return "A nova senha deve ter pelo menos 8 caracteres";
  if (!PASSWORD_PATTERN.test(newPassword)) {
    return "A nova senha deve conter letra maiúscula, minúscula e número";
  }
  if (newPassword === currentPassword) return "A nova senha deve ser diferente da atual";
  if (newPassword !== confirm) return "As senhas não coincidem";
  return "";
}

/** Regras exibidas na tela — mesma política do backend. */
export function passwordRules(newPassword: string, confirm: string): { label: string; ok: boolean }[] {
  return [
    { label: "Pelo menos 8 caracteres", ok: newPassword.length >= 8 },
    { label: "Letra maiúscula e minúscula", ok: /[a-z]/.test(newPassword) && /[A-Z]/.test(newPassword) },
    { label: "Ao menos um número", ok: /\d/.test(newPassword) },
    { label: "Confirmação idêntica", ok: newPassword.length > 0 && newPassword === confirm },
  ];
}

export default function ChangePasswordScreen({ username, onSubmit, onLogout }: Props) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    const validation = validateNewPassword(currentPassword, newPassword, confirmPassword);
    if (validation) {
      setError(validation);
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await onSubmit(currentPassword, newPassword);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível alterar a senha");
    } finally {
      setLoading(false);
    }
  };

  const rules = passwordRules(newPassword, confirmPassword);

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.scroll}
      keyboardShouldPersistTaps="handled"
    >
      <View style={styles.brand}>
        <Logo size={56} />
        <Text style={styles.title}>Crie sua nova senha</Text>
        <Text style={styles.hint}>
          {username ? `${username}, sua` : "Sua"} senha temporária expira agora. Defina uma nova para continuar.
        </Text>
      </View>

      <Card style={styles.card}>
        <Input
          label="Senha atual (temporária)"
          placeholder="Senha que você recebeu"
          secureTextEntry
          autoCapitalize="none"
          value={currentPassword}
          onChangeText={setCurrentPassword}
        />
        <Input
          label="Nova senha"
          placeholder="Digite a nova senha"
          secureTextEntry
          autoCapitalize="none"
          value={newPassword}
          onChangeText={setNewPassword}
        />
        <Input
          label="Confirmar nova senha"
          placeholder="Repita a nova senha"
          secureTextEntry
          autoCapitalize="none"
          value={confirmPassword}
          onChangeText={setConfirmPassword}
        />

        <View style={styles.rules}>
          {rules.map((rule) => (
            <View key={rule.label} style={styles.ruleRow}>
              <View style={[styles.ruleDot, rule.ok && styles.ruleDotOk]}>
                <Text style={[styles.ruleGlyph, rule.ok && styles.ruleGlyphOk]}>
                  {rule.ok ? "✓" : "•"}
                </Text>
              </View>
              <Text style={[styles.ruleLabel, rule.ok && styles.ruleLabelOk]}>{rule.label}</Text>
            </View>
          ))}
        </View>

        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        <Button
          title={loading ? "Salvando…" : "Definir nova senha"}
          onPress={() => void submit()}
          loading={loading}
          disabled={loading || !currentPassword || !newPassword}
        />
      </Card>

      <View style={styles.logout}>
        <Button title="Sair do app" variant="ghost" onPress={onLogout} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  scroll: { paddingHorizontal: spacing.xl, paddingVertical: spacing.xxxl },
  brand: { alignItems: "center", marginBottom: spacing.xxl },
  title: {
    color: colors.foreground,
    fontSize: typography.h1,
    fontWeight: "800",
    marginTop: spacing.lg,
    textAlign: "center",
  },
  hint: {
    color: colors.mutedForeground,
    fontSize: typography.bodySm,
    textAlign: "center",
    marginTop: spacing.sm,
    lineHeight: 20,
  },
  card: { padding: spacing.xl },
  rules: {
    backgroundColor: colors.backgroundSecondary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.lg,
    gap: spacing.sm,
  },
  ruleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  ruleDot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: colors.surfaceMuted,
    alignItems: "center",
    justifyContent: "center",
  },
  ruleDotOk: { backgroundColor: colors.successSoft },
  ruleGlyph: { color: colors.mutedForeground, fontSize: 11, fontWeight: "800", lineHeight: 13 },
  ruleGlyphOk: { color: colors.success },
  ruleLabel: { color: colors.mutedForeground, fontSize: typography.label },
  ruleLabelOk: { color: colors.foreground },
  errorBox: {
    backgroundColor: colors.dangerSoft,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.danger,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginBottom: spacing.lg,
  },
  errorText: { color: colors.danger, fontSize: typography.label, lineHeight: 18 },
  logout: { marginTop: spacing.lg },
});
