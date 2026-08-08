import {BrowserRouter, Routes, Route, Navigate} from 'react-router';
import {useAuthStore} from '@/store/auth';
import {AppChrome} from '@/components/AppChrome';
import {LoginPage} from '@/pages/LoginPage';
import {DashboardPage} from '@/pages/DashboardPage';
import {SourcesPage} from '@/pages/SourcesPage';
import {CatalogPage} from '@/pages/CatalogPage';
import {SecurityPage} from '@/pages/SecurityPage';
import {ObservabilityPage} from '@/pages/ObservabilityPage';
import {MetricsPage} from '@/pages/MetricsPage';
import {KnowledgePage} from '@/pages/KnowledgePage';
import {AgentsPage} from '@/pages/AgentsPage';
import {ModelsPage} from '@/pages/ModelsPage';

function Protected({children}: {children: React.ReactNode}) {
  const token = useAuthStore((s) => s.token);
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <Protected>
              <AppChrome />
            </Protected>
          }
        >
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/sources" element={<SourcesPage />} />
          <Route path="/catalog" element={<CatalogPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/metrics" element={<MetricsPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/security" element={<SecurityPage />} />
          <Route path="/observability" element={<ObservabilityPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
