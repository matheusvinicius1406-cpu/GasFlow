/**
 * mobileUpdate.ts — verificacao de atualizacoes OTA para o APK.
 *
 * O desktop usa electron-updater com GitHub Releases. O mobile nao tem
 * CodePush nem App Center — implementamos um mecanismo leve via API backend:
 *
 * 1. App abre → GET /api/v1/mobile/version (ou relay equivalente)
 * 2. Backend retorna { latest_version, download_url, changelog, min_required }
 * 3. Se latest_version > current → mostra dialog de atualizacao
 * 4. Usuario clica "Atualizar" → abre o link de download (APK direto)
 * 5. Android instala o APK por cima (same signature)
 *
 * O APK e distribuido via URL direta (Nginx, S3, ou relay).
 * O backend mantem um arquivo version.json que o admin atualiza no deploy.
 */

import { Linking } from "react-native";

export interface MobileVersionInfo {
  latest_version: string;
  download_url: string;
  changelog: string;
  min_required: string;
  release_date: string;
}

export interface UpdateCheckResult {
  hasUpdate: boolean;
  isRequired: boolean;
  versionInfo: MobileVersionInfo | null;
  error: string | null;
}

/**
 * Compara versoes semver (major.minor.patch).
 * Retorna positivo se a > b, negativo se a < b, 0 se iguais.
 */
export function compareVersions(a: string, b: string): number {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

/**
 * Verifica se ha atualizacao disponivel.
 * @param currentVersion versao atual do app (ex: "1.2.0")
 * @param baseUrl base URL do backend (ex: "http://192.168.1.5:8000")
 */
export async function checkForUpdate(
  currentVersion: string,
  baseUrl: string
): Promise<UpdateCheckResult> {
  try {
    const url = `${baseUrl}/api/v1/mobile/version`;
    const res = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(5000),
    });

    if (!res.ok) {
      return { hasUpdate: false, isRequired: false, versionInfo: null, error: `HTTP ${res.status}` };
    }

    const data: MobileVersionInfo = await res.json();

    // Validar campos obrigatorios
    if (!data.latest_version || !data.download_url) {
      return { hasUpdate: false, isRequired: false, versionInfo: null, error: "Resposta invalida" };
    }

    const hasUpdate = compareVersions(data.latest_version, currentVersion) > 0;
    const isRequired = hasUpdate && data.min_required
      ? compareVersions(currentVersion, data.min_required) < 0
      : false;

    return { hasUpdate, isRequired, versionInfo: data, error: null };
  } catch (err) {
    return {
      hasUpdate: false,
      isRequired: false,
      versionInfo: null,
      error: err instanceof Error ? err.message : "Erro desconhecido",
    };
  }
}

/**
 * Abre o link de download do APK no navegador/gerenciador de downloads.
 */
export async function openDownloadLink(downloadUrl: string): Promise<boolean> {
  try {
    const supported = await Linking.canOpenURL(downloadUrl);
    if (supported) {
      await Linking.openURL(downloadUrl);
      return true;
    }
    return false;
  } catch {
    return false;
  }
}
