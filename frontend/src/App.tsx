import { Routes, Route } from 'react-router-dom'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { ProtectedRoute } from '@/features/auth'
import { DashboardPage } from '@/features/dashboard'
import { OrdersPage, OrderDetailPage, OrderFormPage } from '@/features/orders'
import { CustomersPage, CustomerDetailPage, CustomerFormPage } from '@/features/customers'
import { WhatsAppPage, CampaignWizardPage, CampaignResultsPage } from '@/features/whatsapp'
import { DeliveriesPage } from '@/features/deliveries'
import { DriversPage, DriverFormPage } from '@/features/drivers'
import { ProductsPage, ProductDetailPage, ProductFormPage } from '@/features/products'
import { InventoryPage, InventoryDetailPage } from '@/features/inventory'
import { FinancePage } from '@/features/finance'
import { ReportsPage } from '@/features/reports'
import { IntelligencePage } from '@/features/intelligence'
import { SettingsPage } from '@/features/settings'
import { LoginPage } from '@/features/auth'
import { DriverLoginPage, DriverHomePage } from '@/features/driver'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/driver/login" element={<DriverLoginPage />} />
      <Route path="/driver" element={<DriverHomePage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />

        {/* Orders */}
        <Route path="orders" element={<OrdersPage />} />
        <Route path="orders/new" element={<OrderFormPage />} />
        <Route path="orders/:codigo" element={<OrderDetailPage />} />

        {/* Customers */}
        <Route path="customers" element={<CustomersPage />} />
        <Route path="customers/new" element={<CustomerFormPage />} />
        <Route path="customers/:codigo" element={<CustomerDetailPage />} />
        <Route path="customers/:codigo/edit" element={<CustomerFormPage />} />

        {/* Products */}
        <Route path="products" element={<ProductsPage />} />
        <Route path="products/new" element={<ProductFormPage />} />
        <Route path="products/:codigo" element={<ProductDetailPage />} />
        <Route path="products/:codigo/edit" element={<ProductFormPage />} />

        {/* Other modules */}
        <Route path="whatsapp" element={<WhatsAppPage />} />
        <Route path="whatsapp/campaigns/new" element={<CampaignWizardPage />} />
        <Route path="whatsapp/campaigns/:id" element={<CampaignResultsPage />} />
        <Route path="deliveries" element={<DeliveriesPage />} />
        <Route path="drivers" element={<DriversPage />} />
        <Route path="drivers/new" element={<DriverFormPage />} />
        <Route path="drivers/:codigo/edit" element={<DriverFormPage />} />
        <Route path="inventory" element={<InventoryPage />} />
        <Route path="inventory/:productCodigo" element={<InventoryDetailPage />} />
        <Route path="finance" element={<FinancePage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="intelligence" element={<IntelligencePage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
