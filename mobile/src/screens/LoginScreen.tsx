/**
 * LoginScreen — scaffold RN (prompt 5.2): username/password → /auth/mobile/login.
 * Guarda tokens no storage seguro (nunca texto puro — prompt seção 7/12).
 * A lógica de conexão (LAN→nuvem→offline) vem de src/logic/connection.ts.
 *
 * O campo "Servidor" existe porque o alvo de conexão não tem outro ponto de
 * entrada no app: o valor digitado vira o lanBaseUrl (persistido no Keystore)
 * e é resolvido antes do login.
 */

import React, { useState } from "react";
import { View, Text, TextInput, Button, StyleSheet } from "react-native";

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
    <View style={styles.container}>
      <Text style={styles.title}>GasFlow — Entregador</Text>
      <TextInput
        style={styles.input}
        placeholder="Servidor (http://ip:8000)"
        keyboardType="url"
        autoCapitalize="none"
        autoCorrect={false}
        value={server}
        onChangeText={setServer}
      />
      <TextInput
        style={styles.input}
        placeholder="Usuário"
        autoCapitalize="none"
        value={username}
        onChangeText={setUsername}
      />
      <TextInput style={styles.input} placeholder="Senha" secureTextEntry value={password} onChangeText={setPassword} />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Button
        title={loading ? "Entrando…" : "Entrar"}
        onPress={submit}
        disabled={loading || !username || !password || !server}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", padding: 24 },
  title: { fontSize: 24, fontWeight: "bold", marginBottom: 24, textAlign: "center" },
  input: { borderWidth: 1, borderColor: "#ccc", borderRadius: 8, padding: 12, marginBottom: 12 },
  error: { color: "#c00", marginBottom: 12 },
});
