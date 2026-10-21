/**
 * LoginScreen — scaffold RN (prompt 5.2): username/password → /auth/mobile/login.
 * Guarda tokens no storage seguro (nunca texto puro — prompt seção 7/12).
 * A lógica de conexão (LAN→nuvem→offline) vem de src/logic/connection.ts.
 *
 * O campo "Servidor" existe porque o alvo de conexão não tem outro ponto de
 * entrada no app: o valor digitado vira o lanBaseUrl (persistido no Keystore)
 * e é resolvido antes do login.
 *
 * Visual: design system dark do projeto (src/theme) — mesma marca do desktop.
 */

import React, { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import Logo from "../components/ui/Logo";
import { colors, spacing, typography } from "../theme";

interface Props {
  onLogin: (tokens: { access_token: string; refresh_token: string; driver_id: string }) => void;
  doLogin: (
    username: string,
    password: string,
    serverUrl: string,
  ) => Promise<{ access_token: string; refresh_token: string; driver_id: string }>;
  initialServerUrl?: string;
}

export default function LoginScreen({ onLogin, doLogin, initialServerUrl }: Props) {
  const [server, setServer] = useState(initialServerUrl ?? "");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError(null);
    setLoading(true);
    try {
      const tokens = await doLogin(username, password, server);
      onLogin(tokens);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Usuário ou senha inválidos.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.brand}>
          <Logo size={76} showWordmark />
        </View>

        <Card style={styles.card}>
          <Input
            label="Servidor"
            placeholder="http://ip:8000"
            hint="Endereço do depósito (LAN ou nuvem)"
            keyboardType="url"
            autoCapitalize="none"
            autoCorrect={false}
            value={server}
            onChangeText={setServer}
          />
          <Input
            label="Usuário"
            placeholder="seu usuário"
            autoCapitalize="none"
            autoCorrect={false}
            value={username}
            onChangeText={setUsername}
          />
          <Input
            label="Senha"
            placeholder="sua senha"
            secureTextEntry
            autoCapitalize="none"
            value={password}
            onChangeText={setPassword}
            returnKeyType="go"
          />

          {error ? (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          <Button
            title={loading ? "Entrando…" : "Entrar"}
            onPress={() => void submit()}
            loading={loading}
            disabled={loading || !username || !password || !server}
          />
        </Card>

        <Text style={styles.footer}>GasFlow · Sistema Operacional de Entregas</Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  scroll: {
    flexGrow: 1,
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.xxxl,
  },
  brand: { alignItems: "center", marginBottom: spacing.xxl },
  card: { padding: spacing.xl },
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
  footer: {
    color: colors.mutedForeground,
    fontSize: typography.caption,
    textAlign: "center",
    marginTop: spacing.xl,
    letterSpacing: 0.3,
  },
});
