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
  type UpdateCheckResult,
} from "../logic/mobileUpdate";
import Logo from "../components/ui/Logo";
import { colors, radius, shadows, spacing, typography } from "../theme";

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
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.brand} />
        <Text style={styles.loadingText}>Verificando atualizações…</Text>
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
            <Logo size={34} />
          </View>
          <Text style={styles.title}>Atualização disponível</Text>
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
            <Text style={styles.requiredText}>Atualização obrigatória</Text>
          </View>
        ) : null}

        {/* Actions */}
        <View style={styles.actions}>
          <TouchableOpacity
            style={[styles.updateButton, downloading && styles.updateButtonDisabled]}
            onPress={() => void handleUpdate()}
            disabled={downloading}
            accessibilityRole="button"
            accessibilityLabel="Baixar e instalar atualização"
          >
            {downloading ? (
              <ActivityIndicator size="small" color={colors.background} />
            ) : (
              <Text style={styles.updateButtonText}>Baixar e instalar</Text>
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
  loadingContainer: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
    zIndex: 9999,
  },
  loadingText: {
    marginTop: spacing.md,
    fontSize: typography.label,
    color: colors.mutedForeground,
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.overlay,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 9998,
    paddingHorizontal: spacing.xl,
  },
  card: {
    width: "100%",
    maxWidth: 420,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.xl,
    padding: spacing.xl,
    alignItems: "center",
    ...shadows.floating,
  },
  header: {
    alignItems: "center",
    marginBottom: spacing.lg,
  },
  updateIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.backgroundSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.md,
  },
  title: {
    fontSize: typography.h2,
    fontWeight: "800",
    color: colors.foreground,
    marginBottom: spacing.xs,
  },
  version: {
    fontSize: typography.label,
    color: colors.mutedForeground,
    fontVariant: ["tabular-nums"],
  },
  changelogContainer: {
    width: "100%",
    backgroundColor: colors.backgroundSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  changelogLabel: {
    fontSize: typography.caption,
    fontWeight: "700",
    color: colors.mutedForeground,
    marginBottom: spacing.xs,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  changelog: {
    fontSize: typography.label,
    color: colors.foreground,
    lineHeight: 19,
  },
  requiredBadge: {
    backgroundColor: colors.warningSoft,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.warning,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    marginBottom: spacing.lg,
    alignSelf: "center",
  },
  requiredText: {
    fontSize: typography.caption,
    fontWeight: "700",
    color: colors.warning,
  },
  actions: {
    width: "100%",
    gap: spacing.sm,
  },
  updateButton: {
    backgroundColor: colors.brand,
    borderRadius: radius.lg,
    paddingVertical: spacing.md + 2,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 48,
  },
  updateButtonDisabled: {
    opacity: 0.7,
  },
  updateButtonText: {
    color: colors.background,
    fontSize: typography.body,
    fontWeight: "800",
  },
  laterButton: {
    borderRadius: radius.lg,
    paddingVertical: spacing.md,
    alignItems: "center",
    minHeight: 44,
    justifyContent: "center",
  },
  laterButtonText: {
    color: colors.mutedForeground,
    fontSize: typography.bodySm,
    fontWeight: "600",
  },
  releaseDate: {
    marginTop: spacing.md,
    fontSize: typography.caption,
    color: colors.mutedForeground,
  },
});
