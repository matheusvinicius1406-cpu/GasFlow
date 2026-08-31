/**
 * GasFlow Tenant Branding System
 *
 * Supports three identity levels:
 * 1. GasFlow Default — official product branding
 * 2. Branding — company name + GasFlow discreet
 * 3. White-label — company identity only
 */

export type ThemeMode = 'light' | 'dark' | 'system'

export interface TenantBranding {
  /** Branding mode */
  mode: 'gasflow' | 'custom'

  /** Company identity */
  companyName: string
  appName: string

  /** Logo URLs */
  logoUrl?: string
  faviconUrl?: string

  /** Color overrides */
  primaryColor?: string
  secondaryColor?: string

  /** Theme preference */
  theme: ThemeMode
}

export const DEFAULT_BRANDING: TenantBranding = {
  mode: 'gasflow',
  companyName: 'GasFlow',
  appName: 'GasFlow',
  theme: 'dark',
}

/** GasFlow brand colors (reference) */
export const GASFLOW_COLORS = {
  primary: '#f97316',
  primaryHover: '#ea580c',
  secondary: '#7c3aed',
  success: '#22c55e',
  warning: '#eab308',
  danger: '#ef4444',
  info: '#3b82f6',
} as const

/**
 * Parse a hex color to RGB values.
 */
export function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const cleaned = hex.replace('#', '')
  if (cleaned.length === 3) {
    const r = parseInt(cleaned.charAt(0) + cleaned.charAt(0), 16)
    const g = parseInt(cleaned.charAt(1) + cleaned.charAt(1), 16)
    const b = parseInt(cleaned.charAt(2) + cleaned.charAt(2), 16)
    return { r, g, b }
  }
  if (cleaned.length === 6) {
    const r = parseInt(cleaned.slice(0, 2), 16)
    const g = parseInt(cleaned.slice(2, 4), 16)
    const b = parseInt(cleaned.slice(4, 6), 16)
    return { r, g, b }
  }
  return null
}

/**
 * Calculate relative luminance of a color.
 */
export function relativeLuminance(r: number, g: number, b: number): number {
  const toLinear = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b)
}

/**
 * Calculate contrast ratio between two colors.
 */
export function contrastRatio(hex1: string, hex2: string): number {
  const c1 = hexToRgb(hex1)
  const c2 = hexToRgb(hex2)
  if (!c1 || !c2) return 1

  const rgb1: { r: number; g: number; b: number } = c1
  const rgb2: { r: number; g: number; b: number } = c2

  const l1 = relativeLuminance(rgb1.r, rgb1.g, rgb1.b)
  const l2 = relativeLuminance(rgb2.r, rgb2.g, rgb2.b)
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

/**
 * Determine appropriate foreground color for a given background.
 * Returns dark text for light backgrounds, light text for dark backgrounds.
 */
export function autoForeground(bgHex: string): string {
  const rgb = hexToRgb(bgHex)
  if (!rgb) return '#09090b'
  const luminance = relativeLuminance(rgb.r, rgb.g, rgb.b)
  return luminance > 0.179 ? '#09090b' : '#fafafa'
}

/**
 * Validate that a color meets minimum contrast requirements.
 * Returns the color if valid, or a fallback.
 */
export function ensureContrast(
  color: string,
  background: string,
  minRatio = 4.5
): string {
  const ratio = contrastRatio(color, background)
  if (ratio >= minRatio) return color

  // Fallback to brand primary if contrast is too low
  return GASFLOW_COLORS.primary
}
