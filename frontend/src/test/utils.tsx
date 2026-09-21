import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui/Toast'
import { ThemeProvider } from '@/lib/theme'

interface RenderOptions {
  route?: string
}

export function renderWithProviders(ui: React.ReactElement, options: RenderOptions = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  // ThemeProvider entra no harness porque componentes de marca (BrandLogo,
  // BrandName) e tokens de tema fazem parte das telas reais — `useTheme`
  // lança sem provider, então testar sem ele divergiria do app.
  return render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter initialEntries={[options.route ?? '/']}>{ui}</MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

/**
 * Render a component that depends on route params (e.g. :codigo).
 * `path` is the Route pattern; `route` is the actual URL the router starts at.
 */
export function renderWithRoute(ui: React.ReactElement, path: string, route: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}
