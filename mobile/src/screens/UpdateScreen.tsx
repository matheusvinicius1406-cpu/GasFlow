/**
 * UpdateScreen — tela de atualizacao do APK.
 *
 * Mostrada quando uma nova versao esta disponivel.
 * Modo nao-bloqueante: o usuario pode adiar e continuar trabalhando.
 * Modo bloqueante: se a versao e obrigatoria (min_required), nao pode ser dispensada.
 */

import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Linking,
} from "react-native";
import {
  checkForUpdate,
  openDownloadLink,
  type MobileVersionInfo,
  type UpdateCheckResult,
} from "../logic/mobileUpdate";

interface UpdateScreenProps {
  currentVersion: string;
  baseUrl: string;
  onDismiss: () => void;
}

export default function UpdateScreen({
  currentVersion,
  baseUrl,
  onDismiss,
}: UpdateScreenProps) {
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState<UpdateCheckResult | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    checkForUpdate(currentVersion, baseUrl).then((r) => {
      setResult(r);
      setLoading(false);
    });
  }, [currentVersion, baseUrl]);

  const handleUpdate = async () => {
    if (!result?.versionInfo) return;
    if (!result.versionInfo.download_url) {
      // URL vazia — informar o usuario
      return;
    }
    setDownloading(true);
    const ok = await openDownloadLink(result.versionInfo.download_url);
    setDownloading(false);
    if (!ok) {
      // Fallback: abrir no browser
      Linking.openURL(result.versionInfo.download_url).catch(() => {
        // Ultimo recurso: nada — URL invalida
      });
    }
  };

  if (loading) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color="#FF6B00" />
        <Text style={styles.loadingText}>Verificando atualizacoes...</Text>
      </View>
    );
  }

  if (!result?.hasUpdate || !result.versionInfo) {
    return null;
  }

  // URL de download nao configurada — nao mostra nada (admin precisa setar mobile_version.json)
  if (!result.versionInfo.download_url) {
    return null;
  }

  const info = result.versionInfo;

  return (
    <View style={styles.overlay}>
      <View style={styles.card}>
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.updateIcon}>
            <Text style={styles.updateIconText}>⬆</Text>
          </View>
          <Text style={styles.title}>Atualizacao Disponivel</Text>
          <Text style={styles.version}>
            v{currentVersion} → v{info.latest_version}
          </Text>
        </View>

        {/* Changelog */}
        {info.changelog ? (
          <View style={styles.changelogContainer}>
            <Text style={styles.changelogLabel}>Novidades:</Text>
            <Text style={styles.changelog}>{info.changelog}</Text>
          </View>
        ) : null}

        {/* Required badge */}
        {result.isRequired ? (
          <View style={styles.requiredBadge}>
            <Text style={styles.requiredText}>Atualizacao obrigatoria</Text>
          </View>
        ) : null}

        {/* Actions */}
        <View style={styles.actions}>
          <TouchableOpacity
            style={[styles.updateButton, downloading && styles.updateButtonDisabled]}
            onPress={handleUpdate}
            disabled={downloading}
          >
            {downloading ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Text style={styles.updateButtonText}>Baixar e Instalar</Text>
            )}
          </TouchableOpacity>

          {!result.isRequired ? (
            <TouchableOpacity style={styles.laterButton} onPress={onDismiss}>
              <Text style={styles.laterButtonText}>Depois</Text>
            </TouchableOpacity>
          ) : null}
        </View>

        {/* Release date */}
        <Text style={styles.releaseDate}>
          Publicado em {info.release_date || "data desconhecida"}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#fff",
  },
  loadingText: {
    marginTop: 16,
    fontSize: 14,
    color: "#666",
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.5)",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 9998,
  },
  card: {
    width: "85%",
    backgroundColor: "#fff",
    borderRadius: 16,
    padding: 24,
    alignItems: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 8,
  },
  header: {
    alignItems: "center",
    marginBottom: 20,
  },
  updateIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: "#FFF3E0",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 12,
  },
  updateIconText: {
    fontSize: 28,
  },
  title: {
    fontSize: 20,
    fontWeight: "700",
    color: "#1a1a1a",
    marginBottom: 4,
  },
  version: {
    fontSize: 14,
    color: "#666",
  },
  changelogContainer: {
    width: "100%",
    backgroundColor: "#f8f9fa",
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  changelogLabel: {
    fontSize: 12,
    fontWeight: "600",
    color: "#666",
    marginBottom: 4,
  },
  changelog: {
    fontSize: 13,
    color: "#333",
    lineHeight: 18,
  },
  requiredBadge: {
    backgroundColor: "#FFF3E0",
    borderRadius: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
    marginBottom: 16,
  },
  requiredText: {
    fontSize: 12,
    fontWeight: "600",
    color: "#E65100",
  },
  actions: {
    width: "100%",
    gap: 10,
  },
  updateButton: {
    backgroundColor: "#FF6B00",
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
  },
  updateButtonDisabled: {
    opacity: 0.7,
  },
  updateButtonText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
  laterButton: {
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
  },
  laterButtonText: {
    color: "#666",
    fontSize: 14,
    fontWeight: "500",
  },
  releaseDate: {
    marginTop: 12,
    fontSize: 11,
    color: "#999",
  },
});
