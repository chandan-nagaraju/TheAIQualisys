import { Navigate, Route, Routes } from "react-router-dom";
import AdminRoute from "./components/AdminRoute";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import PublicPricingGate from "./components/PublicPricingGate";
import WorkspaceSubscriptionGate from "./components/WorkspaceSubscriptionGate";
import WorkspaceLayout from "./layouts/WorkspaceLayout";
import AdminCompanyFirIntelligencePage from "./pages/AdminCompanyFirIntelligencePage";
import AdminCompanyPage from "./pages/AdminCompanyPage";
import AdminDashboardPage from "./pages/AdminDashboardPage";
import AdminDesktopLicensingPage from "./pages/AdminDesktopLicensingPage";
import AdminPricingPage from "./pages/AdminPricingPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import CompanyDashboardPage from "./pages/CompanyDashboardPage";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import AllModulesPricingPage from "./pages/AllModulesPricingPage";
import ModuleProductPricingPage from "./pages/ModuleProductPricingPage";
import ModuleWorkbenchPage from "./pages/ModuleWorkbenchPage";
import ModulesDashboardPage from "./pages/ModulesDashboardPage";
import PricingPage from "./pages/PricingPage";
import SignupPage from "./pages/SignupPage";
import SignupCompletePage from "./pages/SignupCompletePage";
import UpgradePage from "./pages/UpgradePage";
import UpgradePayPage from "./pages/UpgradePayPage";
import CustomersPage from "./pages/workspace/CustomersPage";
import ExtractedPage from "./pages/workspace/ExtractedPage";
import InspectionPage from "./pages/workspace/InspectionPage";
import InspectionResultsPage from "./pages/workspace/InspectionResultsPage";
import PartDetailPage from "./pages/workspace/PartDetailPage";
import PartsPage from "./pages/workspace/PartsPage";
import SelectCustomerPage from "./pages/workspace/SelectCustomerPage";
import SettingsPage from "./pages/workspace/SettingsPage";
import UploadPage from "./pages/workspace/UploadPage";
import WorkspaceDashboard from "./pages/workspace/WorkspaceDashboard";
import ManualEntryPage from "./pages/workspace/ManualEntryPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import ProfilePage from "./pages/workspace/ProfilePage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";

export default function App() {
  return (
    <Routes>
      <Route
        path="/workspace"
        element={
          <ProtectedRoute>
            <WorkspaceLayout />
          </ProtectedRoute>
        }
      >
        <Route path="pricing" element={<PricingPage variant="workspace" />} />
        <Route element={<WorkspaceSubscriptionGate />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<WorkspaceDashboard />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="select-customer" element={<SelectCustomerPage />} />
          <Route path="upload" element={<UploadPage />} />
          <Route path="manual-entry" element={<ManualEntryPage />} />
          <Route path="extracted" element={<ExtractedPage />} />
          <Route path="inspection" element={<InspectionPage />} />
          <Route path="inspection/results" element={<InspectionResultsPage />} />
          <Route path="parts" element={<PartsPage />} />
          <Route path="parts/:id" element={<PartDetailPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Route>

      <Route element={<Layout />}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/signup/complete" element={<SignupCompletePage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/pricing" element={<PublicPricingGate />} />
        <Route path="/pricing/all-modules" element={<AllModulesPricingPage />} />
        <Route path="/pricing/modules/:slug" element={<ModuleProductPricingPage />} />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <ProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/profile/change-password"
          element={
            <ProtectedRoute>
              <ChangePasswordPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <ModulesDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/dashboard/billing"
          element={
            <ProtectedRoute>
              <CompanyDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/modules/:slug"
          element={
            <ProtectedRoute>
              <ModuleWorkbenchPage />
            </ProtectedRoute>
          }
        />
        <Route path="/upgrade" element={<UpgradePage />} />
        <Route path="/upgrade/pay" element={<UpgradePayPage />} />
        <Route path="/admin/login" element={<Navigate to="/login" replace />} />
        <Route
          path="/admin"
          element={
            <AdminRoute>
              <AdminDashboardPage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/users"
          element={
            <AdminRoute>
              <AdminUsersPage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/pricing"
          element={
            <AdminRoute>
              <AdminPricingPage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/desktop-licensing"
          element={
            <AdminRoute>
              <AdminDesktopLicensingPage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/companies/:id/fir-intelligence"
          element={
            <AdminRoute>
              <AdminCompanyFirIntelligencePage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin/companies/:id"
          element={
            <AdminRoute>
              <AdminCompanyPage />
            </AdminRoute>
          }
        />
      </Route>
    </Routes>
  );
}
