import {AppShell} from '@astryxdesign/core/AppShell';
import {SideNav, SideNavItem, SideNavSection} from '@astryxdesign/core/SideNav';
import {TopNav, TopNavHeading} from '@astryxdesign/core/TopNav';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Avatar} from '@astryxdesign/core/Avatar';
import {Divider} from '@astryxdesign/core/Divider';
import {Text} from '@astryxdesign/core/Text';
import {IconButton} from '@astryxdesign/core/IconButton';
import {useNavigate, useLocation, Outlet} from 'react-router';
import {Database, FolderSearch, Shield, Activity, LayoutGrid, LogOut, Calculator, Sun, Moon, Monitor, BookOpen, Bot, Boxes, BrainCircuit, MessageSquareText} from 'lucide-react';
import {useAuthStore} from '@/store/auth';
import {useThemeStore} from '@/store/theme';
import {SegmentedControl, SegmentedControlItem} from '@astryxdesign/core/SegmentedControl';

const NAV_ITEMS = [
  {path: '/dashboard', label: '数据资产', icon: <LayoutGrid size={17} />},
  {path: '/sources', label: '数据源管理', icon: <Database size={17} />},
  {path: '/catalog', label: '元数据目录', icon: <FolderSearch size={17} />},
  {path: '/knowledge', label: '知识工作台', icon: <BookOpen size={17} />},
  {path: '/metrics', label: '指标语义', icon: <Calculator size={17} />},
  {path: '/models', label: '大模型接入', icon: <BrainCircuit size={17} />},
  {path: '/agents', label: 'Agent 协同', icon: <Bot size={17} />},
  {path: '/tasks', label: '问答工作台', icon: <MessageSquareText size={17} />},
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
  const currentPage = NAV_ITEMS.find((item) => location.pathname.startsWith(item.path))?.label ?? '数据资产';

  const sideNav = (
    <SideNav
      header={
        <VStack gap={0.5} style={{padding: '16px 14px 12px'}}>
          <Text weight="semibold">{currentPage}</Text>
          <Text type="supporting"><span className="muted">当前页面</span></Text>
        </VStack>
      }
      footer={
        <VStack gap={2} style={{padding: '10px 12px'}}>
          <Divider />
          <HStack gap={2} vAlign="center">
            <Avatar name={user?.username ?? 'U'} size="sm" />
            <VStack gap={0.5} style={{flex: 1, minWidth: 0}}>
              <Text weight="semibold" style={{fontSize: 13}}>{user?.username}</Text>
              <Text type="supporting" style={{fontSize: 12}}><span className="muted">{roleLabel}</span></Text>
            </VStack>
            <IconButton
              icon={<LogOut size={15} />}
              label="退出登录"
              variant="ghost"
              size="sm"
              onClick={() => {
                logout();
                navigate('/login');
              }}
            />
          </HStack>
        </VStack>
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
          isSelected={location.pathname.startsWith('/agents') || location.pathname.startsWith('/models')}
          onClick={() => navigate('/agents')}
        />
      </SideNavSection>
    </SideNav>
  );

  const topNav = (
    <TopNav
      heading={
        <TopNavHeading
          logo={
            <span
              style={{
                width: 26,
                height: 26,
                borderRadius: 8,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'rgba(47, 109, 184, 0.14)',
                color: '#2f6db8',
              }}
            >
              <Boxes size={15} />
            </span>
          }
          heading="BudaiAgentMesh"
          headingHref="/dashboard"
        />
      }
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
