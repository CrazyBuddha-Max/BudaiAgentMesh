import {AppShell} from '@astryxdesign/core/AppShell';
import {SideNav, SideNavItem, SideNavSection} from '@astryxdesign/core/SideNav';
import {TopNav, TopNavHeading} from '@astryxdesign/core/TopNav';
import {HStack} from '@astryxdesign/core/HStack';
import {Badge} from '@astryxdesign/core/Badge';
import {IconButton} from '@astryxdesign/core/IconButton';
import {useNavigate, useLocation, Outlet} from 'react-router';
import {Database, FolderSearch, Shield, Activity, LayoutGrid, LogOut, Calculator, Sun, Moon, Monitor, BookOpen, Bot} from 'lucide-react';
import {useAuthStore} from '@/store/auth';
import {useThemeStore} from '@/store/theme';
import {SegmentedControl, SegmentedControlItem} from '@astryxdesign/core/SegmentedControl';

const NAV_ITEMS = [
  {path: '/dashboard', label: '数据资产', icon: <LayoutGrid size={17} />},
  {path: '/sources', label: '数据源管理', icon: <Database size={17} />},
  {path: '/catalog', label: '元数据目录', icon: <FolderSearch size={17} />},
  {path: '/knowledge', label: '知识工作台', icon: <BookOpen size={17} />},
  {path: '/metrics', label: '指标语义', icon: <Calculator size={17} />},
  {path: '/agents', label: 'Agent 协同', icon: <Bot size={17} />},
  {path: '/security', label: '安全治理', icon: <Shield size={17} />},
  {path: '/observability', label: '运行观测', icon: <Activity size={17} />},
];

export function AppChrome() {
  const navigate = useNavigate();
  const location = useLocation();
  const {user, logout} = useAuthStore();
  const themeMode = useThemeStore((s) => s.mode);
  const setThemeMode = useThemeStore((s) => s.setMode);

  const roleLabel = user?.role === 'admin' ? '管理员' : user?.role === 'analyst' ? '分析师' : '访客';

  const sideNav = (
    <SideNav
      collapsible
      resizable
      footer={
        <HStack gap={2} style={{padding: '8px 12px'}}>
          <Badge label={user?.username ?? ''} variant="neutral" />
          <Badge label={roleLabel} variant="info" />
        </HStack>
      }
    >
      <SideNavSection title="平台">
        {NAV_ITEMS.map((item) => (
          <SideNavItem
            key={item.path}
            label={item.label}
            icon={item.icon}
            isSelected={location.pathname.startsWith(item.path)}
            onClick={() => navigate(item.path)}
          />
        ))}
      </SideNavSection>
      <SideNavSection title="体系">
        <SideNavItem label="接入层" icon={<Database size={17} />} onClick={() => navigate('/sources')} />
        <SideNavItem
          label="知识层"
          icon={<BookOpen size={17} />}
          isSelected={location.pathname.startsWith('/knowledge') || location.pathname.startsWith('/metrics')}
          onClick={() => navigate('/knowledge')}
        />
        <SideNavItem
          label="协同层"
          icon={<Bot size={17} />}
          isSelected={location.pathname.startsWith('/agents')}
          onClick={() => navigate('/agents')}
        />
      </SideNavSection>
    </SideNav>
  );

  const topNav = (
    <TopNav
      heading={<TopNavHeading heading="BudaiAgentMesh" headingHref="/dashboard" />}
      endContent={
        <HStack gap={2}>
          <SegmentedControl label="主题模式" value={themeMode} onChange={(v) => setThemeMode(v as 'system' | 'light' | 'dark')} size="sm">
            <SegmentedControlItem value="system" label="系统" icon={<Monitor size={13} />} />
            <SegmentedControlItem value="light" label="浅色" icon={<Sun size={13} />} />
            <SegmentedControlItem value="dark" label="深色" icon={<Moon size={13} />} />
          </SegmentedControl>
          <IconButton
            icon={<LogOut size={17} />}
            label="退出登录"
            variant="ghost"
            size="sm"
            onClick={() => {
              logout();
              navigate('/login');
            }}
          />
        </HStack>
      }
    />
  );

  return (
    <AppShell variant="elevated" sideNav={sideNav} topNav={topNav} contentPadding={4}>
      <Outlet />
    </AppShell>
  );
}
