/**
 * GasFlow Theme Provider
 *
 * Manages:
 * - Light/Dark/System theme
 * - Tenant branding (logo, colors, company name)
 * - CSS variable injection for dynamic branding
 */

import { createContext, useContext, useState, useEffect, useCallback, useMemo, type ReactNode } from 'react'
import { DEFAULT_BRANDING, type TenantBranding, type ThemeMode } from './branding'

interface ThemeContextType {
  /** Current resolved theme (never 'system') */
  theme: 'light' | 'dark'

  /** User's theme preference */
  themeMode: ThemeMode

  /** Set theme preference */
  setThemeMode: (mode: ThemeMode) => void

  /** Tenant branding */
  branding: TenantBranding

  /** Update tenant branding */
  setBranding: (branding: Partial<TenantBranding>) => void

  /** Toggle between light and dark */
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextType | null>(null)

function getSystemTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'dark'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function resolveTheme(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') return getSystemTheme()
  return mode
}

/**
 * Apply branding CSS variables to document root.
 */
function applyBranding(branding: TenantBranding) {
  const root = document.documentElement

  if (branding.primaryColor) {
    root.style.setProperty('--primary', branding.primaryColor)
    root.style.setProperty('--brand-primary', branding.primaryColor)
    root.style.setProperty('--ring', branding.primaryColor)
  }

  if (branding.secondaryColor) {
    root.style.setProperty('--brand-secondary', branding.secondaryColor)
  }
}

function clearBrandingOverrides() {
  const root = document.documentElement
  root.style.removeProperty('--primary')
  root.style.removeProperty('--brand-primary')
  root.style.removeProperty('--ring')
  root.style.removeProperty('--brand-secondary')
}

interface ThemeProviderProps {
  children: ReactNode
  defaultMode?: ThemeMode
  defaultBranding?: Partial<TenantBranding>
}

export function ThemeProvider({
  children,
  defaultMode = 'dark',
  defaultBranding,
}: ThemeProviderProps) {
  const [themeMode, setThemeModeState] = useState<ThemeMode>(() => {
    if (typeof window !== 'undefined') {
      return (localStorage.getItem('gasflow_theme') as ThemeMode) || defaultMode
    }
    return defaultMode
  })

  const [branding, setBrandingState] = useState<TenantBranding>({
    ...DEFAULT_BRANDING,
    ...defaultBranding,
  })

  const resolvedTheme = resolveTheme(themeMode)

  // Apply theme class to <html>
  useEffect(() => {
    const root = document.documentElement
    root.classList.remove('light', 'dark')
    root.classList.add(resolvedTheme)
  }, [resolvedTheme])

  // Apply branding CSS variables
  useEffect(() => {
    if (branding.mode === 'custom' && branding.primaryColor) {
      applyBranding(branding)
    } else {
      clearBrandingOverrides()
    }
  }, [branding])

  // Listen for system theme changes
  useEffect(() => {
    if (themeMode !== 'system') return

    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      const root = document.documentElement
      root.classList.remove('light', 'dark')
      root.classList.add(getSystemTheme())
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [themeMode])

  const setThemeMode = useCallback((mode: ThemeMode) => {
    setThemeModeState(mode)
    localStorage.setItem('gasflow_theme', mode)
  }, [])

  const setBranding = useCallback((partial: Partial<TenantBranding>) => {
    setBrandingState((prev) => ({ ...prev, ...partial }))
  }, [])

  const toggleTheme = useCallback(() => {
    setThemeModeState((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark'
      localStorage.setItem('gasflow_theme', next)
      return next
    })
  }, [])

  const value = useMemo(
    () => ({
      theme: resolvedTheme,
      themeMode,
      setThemeMode,
      branding,
      setBranding,
      toggleTheme,
    }),
    [resolvedTheme, themeMode, setThemeMode, branding, setBranding, toggleTheme]
  )

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
