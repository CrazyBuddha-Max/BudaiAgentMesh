import {useQuery} from '@tanstack/react-query';
import {useNavigate} from 'react-router';
import {api} from '@/api/client';
import {PageHeader} from '@/components/PageHeader';
import {StatCard} from '@/components/StatCard';
import {StatusBadge} from '@/components/StatusBadge';
import {QualityBar} from '@/components/QualityBar';
import {Table, proportional} from '@astryxdesign/core/Table';
import {Button} from '@astryxdesign/core/Button';
import {Text} from '@astryxdesign/core/Text';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Database, Table2, Columns3, RefreshCw, ArrowRight} from 'lucide-react';

export function DashboardPage() {
  const navigate = useNavigate();

  const stats = useQuery({queryKey: ['catalog-stats'], queryFn: api.catalogStats});
  const sources = useQuery({queryKey: ['sources'], queryFn: api.listSources});

  const columns = [
    {key: 'name', header: '数据源', width: proportional(2), renderCell: (r: {name: string; description: string | null}) => (
      <div>
        <Text weight="semibold">{r.name}</Text>
        <Text type="supporting"><span className="muted">{r.description ?? '暂无描述'}</span></Text>
      </div>
    )},
    {key: 'source_type', header: '类型', width: proportional(1), renderCell: (r: {source_type: string}) => (
      <Text type="body" className="mono">{r.source_type}</Text>
    )},
    {key: 'status', header: '状态', width: proportional(1), renderCell: (r: {status: string}) => <StatusBadge status={r.status} />},
    {key: 'quality_score', header: '质量分', width: proportional(1.4), renderCell: (r: {quality_score: number}) => <QualityBar score={r.quality_score} />},
    {key: 'created_at', header: '接入时间', width: proportional(1.2), renderCell: (r: {created_at: string}) => (
      <Text type="supporting" className="mono">{r.created_at.slice(0, 10)}</Text>
    )},
  ];

  return (
    <div className="page-stack">
      <PageHeader
        title="数据资产"
        description="企业数据资产统一视图: 接入规模、目录规模与质量总览"
        actions={
          <Button
            label="管理数据源"
            variant="secondary"
            icon={<ArrowRight size={16} />}
            onClick={() => navigate('/sources')}
          />
        }
      />

      <div style={{display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16}}>
        <StatCard
          label="数据源"
          value={stats.data?.sources ?? '--'}
          hint="已注册连接"
          icon={<Database size={20} />}
        />
        <StatCard
          label="目录表"
          value={stats.data?.tables ?? '--'}
          hint="Schema 已注册"
          icon={<Table2 size={20} />}
        />
        <StatCard
          label="目录列"
          value={stats.data?.columns ?? '--'}
          hint="字段级元数据"
          icon={<Columns3 size={20} />}
        />
        <StatCard
          label="采集任务"
          value={stats.data?.ingestion_runs ?? '--'}
          hint="累计执行"
          icon={<RefreshCw size={20} />}
        />
      </div>

      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>最近接入的数据源</Text>
        {sources.isLoading ? (
          <Text type="supporting">加载中...</Text>
        ) : sources.data && sources.data.length > 0 ? (
          <Table
            data={sources.data as never}
            columns={columns as never}
            density="compact"
            dividers="rows"
            hasHover
          />
        ) : (
          <EmptyState
            title="尚未接入数据源"
            description="前往数据源管理页, 接入第一个数据资产"
            actions={<Button label="立即接入" variant="primary" onClick={() => navigate('/sources')} />}
          />
        )}
      </div>
    </div>
  );
}
