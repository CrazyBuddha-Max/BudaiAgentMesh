import {useQuery} from '@tanstack/react-query';
import {useNavigate} from 'react-router';
import {api} from '@/api/client';
import {StatCard} from '@/components/StatCard';
import {StatusBadge} from '@/components/StatusBadge';
import {QualityBar} from '@/components/QualityBar';
import {Table, proportional} from '@astryxdesign/core/Table';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Badge} from '@astryxdesign/core/Badge';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {useAuthStore} from '@/store/auth';
import type {AuditLogEntry, DataSource} from '@/api/types';
import {
  Database, Table2, Columns3, RefreshCw, ArrowRight, Plus, Upload, Bot as BotIcon,
  PlugZap, BookOpen, GitBranch, ShieldCheck, Activity, CircleCheck,
} from 'lucide-react';

const LAYERS = [
  {name: '接入层', icon: <PlugZap size={15} />, status: '已启用', href: '/sources'},
  {name: '知识层', icon: <BookOpen size={15} />, status: '已启用', href: '/knowledge'},
  {name: '协同层', icon: <BotIcon size={15} />, status: '已启用', href: '/agents'},
  {name: '安全层', icon: <ShieldCheck size={15} />, status: '已启用', href: '/security'},
  {name: '反馈层', icon: <Activity size={15} />, status: '已启用', href: '/observability'},
];

export function DashboardPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);

  const stats = useQuery({queryKey: ['catalog-stats'], queryFn: api.catalogStats});
  const sources = useQuery({queryKey: ['sources'], queryFn: api.listSources});
  const audit = useQuery({queryKey: ['audit-logs'], queryFn: () => api.auditLogs({limit: 6})});
  const feedback = useQuery({queryKey: ['feedback-stats'], queryFn: api.feedbackStats});
  const health = useQuery({queryKey: ['health'], queryFn: api.health});

  const roleLabel = user?.role === 'admin' ? '管理员' : user?.role === 'analyst' ? '分析师' : '访客';
  const today = new Date().toLocaleDateString('zh-CN', {year: 'numeric', month: 'long', day: 'numeric', weekday: 'long'});

  const columns = [
    {key: 'name', header: '数据源', width: proportional(2), renderCell: (r: DataSource) => (
      <div>
        <Text weight="semibold">{r.name}</Text>
        <Text type="supporting"><span className="muted">{r.description ?? '暂无描述'}</span></Text>
      </div>
    )},
    {key: 'source_type', header: '类型', width: proportional(1), renderCell: (r: DataSource) => (
      <Text type="body" className="mono">{r.source_type}</Text>
    )},
    {key: 'status', header: '状态', width: proportional(1), renderCell: (r: DataSource) => <StatusBadge status={r.status} />},
    {key: 'quality_score', header: '质量分', width: proportional(1.4), renderCell: (r: DataSource) => <QualityBar score={r.quality_score} />},
    {key: 'created_at', header: '接入时间', width: proportional(1.2), renderCell: (r: DataSource) => (
      <Text type="supporting" className="mono">{r.created_at.slice(0, 10)}</Text>
    )},
  ];

  return (
    <div className="page-stack">
      {/* 欢迎区 */}
      <Card variant="muted" style={{padding: 24}}>
        <HStack hAlign="between" vAlign="center" wrap="wrap" gap={4}>
          <VStack gap={1}>
            <Text weight="semibold" style={{fontSize: 22}}>
              你好, {user?.username} · {roleLabel}
            </Text>
            <Text type="supporting"><span className="muted">{today} · 智能体数据中台运行正常</span></Text>
          </VStack>
          <HStack gap={2}>
            <StatusBadge status={health.data?.status === 'ok' ? 'active' : 'error'} />
            <Badge label={`反馈均分 ${feedback.data?.avg_rating != null ? feedback.data.avg_rating.toFixed(1) : '--'} / 5`} variant="info" />
            <Badge label={`服务 v${health.data?.version ?? '--'}`} variant="neutral" />
          </HStack>
        </HStack>
      </Card>

      {/* 快捷操作 */}
      <HStack gap={2} wrap="wrap">
        <Button label="接入数据源" variant="primary" icon={<Plus size={15} />} onClick={() => navigate('/sources')} />
        <Button label="上传知识文档" variant="secondary" icon={<Upload size={15} />} onClick={() => navigate('/knowledge')} />
        <Button label="发起 Agent 任务" variant="secondary" icon={<BotIcon size={15} />} onClick={() => navigate('/agents')} />
      </HStack>

      {/* 规模统计 */}
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16}}>
        <StatCard label="数据源" value={stats.data?.sources ?? '--'} hint="已注册连接" icon={<Database size={20} />} />
        <StatCard label="目录表" value={stats.data?.tables ?? '--'} hint="Schema 已注册" icon={<Table2 size={20} />} />
        <StatCard label="目录列" value={stats.data?.columns ?? '--'} hint="字段级元数据" icon={<Columns3 size={20} />} />
        <StatCard label="采集任务" value={stats.data?.ingestion_runs ?? '--'} hint="累计执行" icon={<RefreshCw size={20} />} />
      </div>

      {/* 五层状态 */}
      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>平台能力</Text>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: 12}}>
          {LAYERS.map((layer) => (
            <Card key={layer.name} variant="default" style={{padding: 14, cursor: 'pointer'}}>
              <div onClick={() => navigate(layer.href)}>
                <HStack gap={2} vAlign="center">
                  <span className="muted">{layer.icon}</span>
                  <Text weight="semibold">{layer.name}</Text>
                </HStack>
                <HStack gap={1} vAlign="center" style={{marginTop: 8}}>
                  <CircleCheck size={13} style={{color: '#2f9e6e'}} />
                  <Text type="supporting"><span style={{color: '#2f9e6e'}}>{layer.status}</span></Text>
                </HStack>
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* 最近动态 + 数据源 */}
      <div style={{display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 16}}>
        <div>
          <Text weight="semibold" style={{marginBottom: 8}}>最近接入的数据源</Text>
          {sources.isLoading ? (
            <Text type="supporting">加载中...</Text>
          ) : sources.data && sources.data.length > 0 ? (
            <Table data={sources.data as never} columns={columns as never} density="compact" dividers="rows" hasHover />
          ) : (
            <EmptyState
              title="尚未接入数据源"
              description="接入第一个数据资产, 开启智能体数据驱动"
              actions={<Button label="立即接入" variant="primary" onClick={() => navigate('/sources')} />}
            />
          )}
        </div>

        <VStack gap={3}>
          <Card variant="muted" style={{padding: 16}}>
            <VStack gap={2}>
              <HStack gap={2} vAlign="center" hAlign="between">
                <HStack gap={2} vAlign="center">
                  <Activity size={15} className="muted" />
                  <Text weight="semibold">最近动态</Text>
                </HStack>
                <Button label="全部" variant="ghost" size="sm" onClick={() => navigate('/security')} />
              </HStack>
              {(audit.data ?? []).map((l: AuditLogEntry) => (
                <HStack key={l.id} gap={2} vAlign="center">
                  <Badge label={l.action} variant="neutral" />
                  <Text type="supporting" style={{flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
                    <span className="muted">{l.actor} · {l.target_type}{l.target_id ? `:${l.target_id}` : ''}</span>
                  </Text>
                  <Text type="supporting" className="mono muted" style={{fontSize: 11}}>
                    {l.created_at.slice(5, 16).replace('T', ' ')}
                  </Text>
                </HStack>
              ))}
              {(audit.data ?? []).length === 0 && <Text type="supporting"><span className="muted">暂无动态</span></Text>}
            </VStack>
          </Card>

          <Card variant="muted" style={{padding: 16}}>
            <VStack gap={2}>
              <HStack gap={2} vAlign="center">
                <GitBranch size={15} className="muted" />
                <Text weight="semibold">数据驱动闭环</Text>
              </HStack>
              <Text type="supporting">
                <span className="muted">接入 → 知识 → 协同 → 安全 → 反馈, 五层一体。每一次 Agent 执行都回流为系统的进化信号。</span>
              </Text>
              <HStack gap={1}>
                <Badge label="M1–M5 已交付" variant="success" />
                <Badge label="M6: 多租户/SSO/联邦/CDC/OTel 规划中" variant="neutral" />
              </HStack>
            </VStack>
          </Card>
        </VStack>
      </div>

      <HStack hAlign="end">
        <Button label="进入数据源管理" variant="ghost" icon={<ArrowRight size={15} />} onClick={() => navigate('/sources')} />
      </HStack>
    </div>
  );
}
