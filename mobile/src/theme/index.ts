/**
 * Design system do app do entregador.
 *
 * Espelha os tokens do web (`frontend/src/index.css` → variáveis CSS do tema
 * dark) para a marca ser a mesma no desktop e no celular. As telas importam da
 *qui — nunca hex solto num StyleSheet.
 */

export const colors = {
  /** Fundo das telas (page). */
  background: "#09090b",
  /** Fundo secundário (hero/header). */
  backgroundSecondary: "#0f0f12",
  /** Superfície de card. */
  surface: "#18181b",
  /** Superfície em repouso interativo (row pressionada). */
  surfaceHover: "#1f1f23",
  /** Superfície muted (chips, trilhas de progresso). */
  surfaceMuted: "#27272a",
  border: "#27272a",
  borderStrong: "#3f3f46",
  foreground: "#fafafa",
  mutedForeground: "#a1a1aa",
  brand: "#f97316",
  brandHover: "#ea580c",
  brandSoft: "rgba(249, 115, 22, 0.14)",
  secondary: "#7c3aed",
  success: "#22c55e",
  successSoft: "rgba(34, 197, 94, 0.15)",
  warning: "#eab308",
  warningSoft: "rgba(234, 179, 8, 0.15)",
  danger: "#ef4444",
  dangerSoft: "rgba(239, 68, 68, 0.15)",
  info: "#3b82f6",
  infoSoft: "rgba(59, 130, 246, 0.15)",
  white: "#ffffff",
  /** Scrim dos overlays (modal de atualização). */
  overlay: "rgba(0, 0, 0, 0.62)",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const radius = {
  sm: 6,
  md: 8,
  lg: 12,
  xl: 16,
  full: 999,
} as const;

export const typography = {
  display: 30,
  h1: 24,
  h2: 20,
  h3: 17,
  body: 15,
  bodySm: 14,
  label: 13,
  caption: 12,
} as const;

/** Sombras Android/iOS no padrão do tema (elevação sutil sobre o card). */
export const shadows = {
  card: {
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.35,
    shadowRadius: 6,
    elevation: 3,
  },
  floating: {
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4,
    shadowRadius: 16,
    elevation: 10,
  },
} as const;

/** Paleta de cada status de entrega (rótulo + cor de chip). */
export const statusTheme: Record<string, { label: string; fg: string; bg: string }> = {
  PENDING: { label: "Pendente", fg: colors.mutedForeground, bg: colors.surfaceMuted },
  ASSIGNED: { label: "Atribuída", fg: colors.info, bg: colors.infoSoft },
  DISPATCHED: { label: "Despachada", fg: colors.info, bg: colors.infoSoft },
  EN_ROUTE: { label: "Em rota", fg: colors.brand, bg: colors.brandSoft },
  ARRIVED: { label: "No local", fg: colors.warning, bg: colors.warningSoft },
  DELIVERED: { label: "Entregue", fg: colors.success, bg: colors.successSoft },
  FAILED: { label: "Falhou", fg: colors.danger, bg: colors.dangerSoft },
};
