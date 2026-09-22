/**
 * ChangePasswordScreen — troca obrigatória no primeiro acesso.
 *
 * Gate P0 (3.8): reset do admin seta `must_change_password`; o app bloqueia
 * aqui até `POST /auth/change-password` limpar a flag no backend. Espelha a
 * política mínima do backend (8+ chars, 1 maiúscula, 1 minúscula, 1 dígito).
 *
 * Apresentação pura (callbacks) — o comportamento fica no contêiner wired.
 */

import React, { useState } from "react";
import { View, Text, TextInput, Button, StyleSheet } from "react-native";

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

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Troca de senha obrigatória</Text>
      <Text style={styles.hint}>
        {username ? `${username}, sua` : "Sua"} senha foi redefinida. Defina uma nova senha para continuar.
      </Text>

      <TextInput
        style={styles.input}
        placeholder="Senha atual (temporária)"
        secureTextEntry
        value={currentPassword}
        onChangeText={setCurrentPassword}
      />
      <TextInput style={styles.input} placeholder="Nova senha" secureTextEntry value={newPassword} onChangeText={setNewPassword} />
      <TextInput
        style={styles.input}
        placeholder="Confirmar nova senha"
        secureTextEntry
        value={confirmPassword}
        onChangeText={setConfirmPassword}
      />

      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Button
        title={loading ? "Salvando…" : "Definir nova senha"}
        onPress={submit}
        disabled={loading || !currentPassword || !newPassword}
      />
      <View style={styles.spacer} />
      <Button title="Sair" onPress={onLogout} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", padding: 24 },
  title: { fontSize: 22, fontWeight: "bold", marginBottom: 8, textAlign: "center" },
  hint: { color: "#555", marginBottom: 20, textAlign: "center" },
  input: { borderWidth: 1, borderColor: "#ccc", borderRadius: 8, padding: 12, marginBottom: 12 },
  error: { color: "#c00", marginBottom: 12 },
  spacer: { height: 12 },
});
