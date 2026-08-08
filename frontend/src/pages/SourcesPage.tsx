import {useState} from 'react';
import {useQuery, useMutation, useQueryClient} from '@tanstack/react-query';
import {api} from '@/api/client';
import {PageHeader} from '@/components/PageHeader';
import {StatusBadge} from '@/components/StatusBadge';
import {QualityBar} from '@/components/QualityBar';
import {Table, proportional, pixel} from '@astryxdesign/core/Table';
import {Button} from '@astryxdesign/core/Button';
import {IconButton} from '@astryxdesign/core/IconButton';
import {Card} from '@astryxdesign/core/Card';
import {Text} from '@astryxdesign/core/Text';
import {TextInput} from '@astryxdesign/core/TextInput';
import {FileInput} from '@astryxdesign/core/FileInput';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {SegmentedControl, SegmentedControlItem} from '@astryxdesign/core/SegmentedControl';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {useToast} from '@astryxdesign/core/Toast';
import type {ConnectorInfo, DataSource} from '@/api/types';
import {Plus, Play, PlugZap, Trash2, X} from 'lucide-react';
import {useAuthStore} from '@/store/auth';

export function SourcesPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = (user?.role ?? 'viewer') !== 'viewer';

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    name: '',
    source_type: 'csv',
    description: '',
    host: '',
    port: '',
    database: '',
    schema_name: 'public',
    username: '',
    password: '',
    file_path: '',
  });
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const isCsv = form.source_type === 'csv';

  const sources = useQuery({queryKey: ['sources'], queryFn: api.listSources});
  const connectors = useQuery({queryKey: ['connectors'], queryFn: api.connectors});

  const testMutation = useMutation({
    mutationFn: (id: number) => api.testSource(id),
    onSuccess: (data) => {
      toast({body: data.message});
      qc.invalidateQueries({queryKey: ['sources']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '连接失败', type: 'error'}),
  });

  const ingestMutation = useMutation({
    mutationFn: (id: number) => api.ingestSource(id),
    onSuccess: (data) => {
      toast({body: data.message});
      qc.invalidateQueries({queryKey: ['sources']});
      qc.invalidateQueries({queryKey: ['catalog-stats']});
      qc.invalidateQueries({queryKey: ['catalog-tables']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '采集失败', type: 'error'}),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteSource(id),
    onSuccess: () => {
      toast({body: '数据源已删除'});
      qc.invalidateQueries({queryKey: ['sources']});
      qc.invalidateQueries({queryKey: ['catalog-stats']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '删除失败', type: 'error'}),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      isCsv && csvFile
        ? api.createCsvSource(form.name, form.description || '', csvFile)
        : api.createSource({
            name: form.name,
            source_type: form.source_type,
            description: form.description || null,
            host: form.host || null,
            port: form.port ? Number(form.port) : null,
            database: form.database || null,
            schema_name: form.schema_name || 'public',
            username: form.username || null,
            password: form.password || null,
            file_path: form.file_path || null,
          }),
    onSuccess: (source) => {
      toast({body: `数据源「${source.name}」已创建`});
      setShowCreate(false);
      setForm({name: '', source_type: 'csv', description: '', host: '', port: '', database: '', schema_name: 'public', username: '', password: '', file_path: ''});
      setCsvFile(null);
      qc.invalidateQueries({queryKey: ['sources']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '创建失败', type: 'error'}),
  });

  const columns = [
    {key: 'name', header: '名称', width: proportional(1.8), renderCell: (r: DataSource) => (
      <div>
        <Text weight="semibold">{r.name}</Text>
        <Text type="supporting"><span className="muted">{r.description ?? '暂无描述'}</span></Text>
      </div>
    )},
    {key: 'source_type', header: '连接器', width: proportional(0.8), renderCell: (r: DataSource) => (
      <Text className="mono">{r.source_type}</Text>
    )},
    {key: 'target', header: '目标', width: proportional(1.2), renderCell: (r: DataSource) => (
      <Text type="supporting" className="mono">
        {r.source_type === 'csv' ? (r.file_path ?? '--') : `${r.host ?? '--'}:${r.port ?? ''}`}
      </Text>
    )},
    {key: 'status', header: '状态', width: proportional(0.9), renderCell: (r: DataSource) => <StatusBadge status={r.status} />},
    {key: 'quality_score', header: '质量分', width: proportional(1.2), renderCell: (r: DataSource) => <QualityBar score={r.quality_score} />},
    {key: 'last_ingested_at', header: '最近采集', width: proportional(1.1), renderCell: (r: DataSource) => (
      <Text type="supporting" className="mono">{r.last_ingested_at ? r.last_ingested_at.slice(0, 16).replace('T', ' ') : '从未采集'}</Text>
    )},
    {key: 'actions', header: '操作', width: pixel(150), renderCell: (r: DataSource) => (
      <HStack gap={1}>
        <IconButton
          size="sm"
          variant="ghost"
          label="测试连接"
          icon={<PlugZap size={15} />}
          isDisabled={!canEdit || testMutation.isPending}
          onClick={() => testMutation.mutate(r.id)}
        />
        <IconButton
          size="sm"
          variant="ghost"
          label="执行采集"
          icon={<Play size={15} />}
          isDisabled={!canEdit || ingestMutation.isPending}
          onClick={() => ingestMutation.mutate(r.id)}
        />
        <IconButton
          size="sm"
          variant="ghost"
          label="删除"
          icon={<Trash2 size={15} />}
          isDisabled={!canEdit}
          onClick={() => {
            if (window.confirm(`确认删除数据源「${r.name}」? 目录元数据将一并清除`)) {
              deleteMutation.mutate(r.id);
            }
          }}
        />
      </HStack>
    )},
  ];

  const set = (key: keyof typeof form) => (v: string) => setForm((f) => ({...f, [key]: v}));

  return (
    <div className="page-stack">
      <PageHeader
        title="数据源管理"
        description="接入企业任意数据资产: 注册连接、校验连通性、执行采集入库"
        actions={
          canEdit ? (
            showCreate ? (
              <Button label="收起表单" variant="ghost" icon={<X size={16} />} onClick={() => setShowCreate(false)} />
            ) : (
              <Button label="接入数据源" variant="primary" icon={<Plus size={16} />} onClick={() => setShowCreate(true)} />
            )
          ) : undefined
        }
      />

      {showCreate && canEdit && (
        <Card variant="muted" style={{padding: 20}}>
          <VStack gap={4}>
            <Text weight="semibold">新建数据源</Text>
            <SegmentedControl value={form.source_type} onChange={(v) => setForm((f) => ({...f, source_type: v}))} label="连接器类型">
              {connectors.data?.map((c) => <SegmentedControlItem key={c.type} value={c.type} label={c.display_name} />)}
            </SegmentedControl>

            <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16}}>
              <TextInput label="数据源名称" value={form.name} onChange={set('name')} isRequired description="全局唯一" />
              <TextInput label="描述" value={form.description} onChange={set('description')} />
              {isCsv ? (
                <FileInput
                  label="CSV 文件"
                  accept=".csv"
                  value={csvFile}
                  onChange={(f) => setCsvFile(f as File | null)}
                  isRequired
                  description="从电脑选择 CSV 文件上传"
                />
              ) : (
                <TextInput label="数据库名" value={form.database} onChange={set('database')} isRequired />
              )}
              {!isCsv && <TextInput label="主机" value={form.host} onChange={set('host')} isRequired />}
              {!isCsv && <TextInput label="端口" value={form.port} onChange={set('port')} />}
              {!isCsv && <TextInput label="Schema" value={form.schema_name} onChange={set('schema_name')} />}
              {!isCsv && <TextInput label="用户名" value={form.username} onChange={set('username')} />}
              {!isCsv && <TextInput label="密码" type="password" value={form.password} onChange={set('password')} description="密文存储, 绝不回显" />}
            </div>

            <HStack gap={2} hAlign="end">
              <Button label="取消" variant="ghost" onClick={() => setShowCreate(false)} />
              <Button
                label={createMutation.isPending ? '创建中...' : '创建数据源'}
                variant="primary"
                isLoading={createMutation.isPending}
                isDisabled={!form.name || (isCsv ? !csvFile : !form.database)}
                onClick={() => createMutation.mutate()}
              />
            </HStack>
          </VStack>
        </Card>
      )}

      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>连接器市场 ({connectors.data?.length ?? 0})</Text>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12}}>
          {(connectors.data ?? []).map((c: ConnectorInfo) => (
            <Card key={c.type} variant="default" style={{padding: 14}}>
              <HStack hAlign="between">
                <Text weight="semibold" className="mono">{c.display_name}</Text>
                <StatusBadge status={c.available ? 'active' : 'pending'} />
              </HStack>
              <Text type="supporting"><span className="muted">{c.description}</span></Text>
            </Card>
          ))}
        </div>
      </div>

      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>已接入数据源 ({sources.data?.length ?? 0})</Text>
        {sources.isLoading ? (
          <Text type="supporting">加载中...</Text>
        ) : sources.data && sources.data.length > 0 ? (
          <Table data={sources.data as never} columns={columns as never} density="compact" dividers="rows" hasHover />
        ) : (
          <EmptyState title="暂无数据源" description="点击「接入数据源」开始整合企业数据资产" />
        )}
      </div>
    </div>
  );
}
