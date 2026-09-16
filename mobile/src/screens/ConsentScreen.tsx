/**
 * ConsentScreen — consentimento LGPD de rastreamento (F2 do spec, decisão B3).
 *
 * Bloqueante: sem aceitar, o entregador não usa o app (nenhuma rota à frente).
 * Registra data + versão do termo via useSessionStore.acceptConsent().
 * Texto sem jargão: o que coleta, quando, por quanto tempo e como desligar.
 */

import React, { useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from "react-native";
import { useSessionStore } from "../logic/session";

export default function ConsentScreen() {
  const [checked, setChecked] = useState(false);
  const acceptConsent = useSessionStore((s) => s.acceptConsent);

  return (
    <View style={styles.container} testID="consent-screen">
      <Text style={styles.title}>Rastreamento durante o trabalho</Text>
      <ScrollView style={styles.scroll}>
        <Text style={styles.paragraph}>
          Para organizar as entregas, o GasFlow usa a <Text style={styles.bold}>localização do seu celular</Text> enquanto
          você está em rota.
        </Text>
        <Text style={styles.paragraph}>{"\u2022"} O quê: sua posição GPS (latitude/longitude e velocidade).</Text>
        <Text style={styles.paragraph}>{"\u2022"} Quando: só dentro do seu horário de trabalho e com o app aberto.</Text>
        <Text style={styles.paragraph}>{"\u2022"} Por quanto tempo: guardamos as posições por 90 dias e depois apagamos.</Text>
        <Text style={styles.paragraph}>{"\u2022"} Quem vê: apenas a base, para acompanhar as entregas.</Text>
        <Text style={styles.paragraph}>
          Você pode recusar. Sem isso, dá para usar o app, mas a base não acompanha sua rota no mapa.
        </Text>
      </ScrollView>

      <TouchableOpacity
        style={styles.checkboxRow}
        onPress={() => setChecked((v) => !v)}
        accessibilityRole="checkbox"
        accessibilityState={{ checked }}
        testID="consent-checkbox"
      >
        <View style={[styles.checkbox, checked && styles.checkboxOn]} />
        <Text style={styles.checkboxLabel}>
          Li e concordo com a coleta de localização durante meu horário de trabalho.
        </Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.button, (!checked || false) && styles.buttonDisabled]}
        disabled={!checked}
        onPress={() => acceptConsent()}
        testID="consent-accept"
      >
        <Text style={styles.buttonText}>Aceitar e continuar</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 24, justifyContent: "center" },
  title: { fontSize: 22, fontWeight: "bold", marginBottom: 12, textAlign: "center" },
  scroll: { maxHeight: 280, marginBottom: 16 },
  paragraph: { fontSize: 15, color: "#333", marginBottom: 8, lineHeight: 21 },
  bold: { fontWeight: "bold" },
  checkboxRow: { flexDirection: "row", alignItems: "center", marginBottom: 16 },
  checkbox: { width: 22, height: 22, borderWidth: 2, borderColor: "#0a7", borderRadius: 4, marginRight: 10 },
  checkboxOn: { backgroundColor: "#0a7" },
  checkboxLabel: { flex: 1, fontSize: 14, color: "#222" },
  button: { backgroundColor: "#0a7", borderRadius: 8, padding: 14, alignItems: "center" },
  buttonDisabled: { backgroundColor: "#bbb" },
  buttonText: { color: "#fff", fontWeight: "bold", fontSize: 16 },
});
