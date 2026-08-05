import {useMemo, useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api} from '@/api/client';
import {PageHeader} from '@/components/PageHeader';
import {Table, proportional} from '@astryxdesign/core/Table';
import {Button} from '@astryxdesign/core/Button';
import {TextInput} from '@astryxdesign/core/TextInput';
import {TextArea} from '@astryxdesign/core/TextArea';
import {Text} from '@astryxdesign/core/Text';
import {Card} from '@astryxdesign/core/Card';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Badge} from '@astryxdesign/core/Badge';
import {Selector} from '@astryxdesign/core/Selector';
import {CheckboxList, CheckboxListItem} from '@astryxdesign/core/CheckboxList';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Play, Plus, Trash2, Calculator, Database as DbIcon, TrendingUp} from 'lucide-react';
import type {CatalogTable, MetricDefinition, MetricQueryResult} from '@/api/types';

const AGG_OPTIONS = [
  {label: 'SUM 求和', value: 'sum'},
  {label: 'AVG 平均', value: 'avg'},
  {label: 'COUNT 计数', value: 'count'},
  {label: 'MIN 最小', value: 'min'},
  {label: 'MAX 最大', value: 'max'},
  {label: 'COUNT_DISTINCT 去重计数', value: 'count_distinct'},
];

interface NewMetricForm {
  name: string;
  display_name: string;
  description: string;
  table_id: string;
  measure: string;
  aggregation: string;
  unit: string;
  dimensions: string[];
}

const EMPTY_FORM: NewMetricForm = {
  name: '',
  display_name: '',
  description: '',
  table_id: '',
  measure: '',
  aggregation: 'sum',
  unit: '',
  dimensions: [],
};

function formatValue(v: unknown, unit?: string | null): string {
  if (v === null || v === undefined) return '--';
  if (typeof v === 'number') {
    return Number.isInteger(v) ? `${v.toLocaleString()}${unit ? ` ${unit}` : ''}` : `${v.toFixed(2)}${unit ? ` ${unit}` : ''}`;
  }
  return `${String(v)}${unit ? ` ${unit}` : ''}`;
}

export function MetricsPage() {
  const qc = useQueryClient();
  const [keyword, setKeyword] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<NewMetricForm>(EMPTY_FORM);
  const [formError, setFormError] = useState('');
  const [queryTarget, setQueryTarget] = useState<number | null>(null);
  const [queryGroupBy, setQueryGroupBy] = useState<string[]>([]);
  const [queryResult, setQueryResult] = useState<MetricQueryResult | null>(null);
  const [queryError, setQueryError] = useState('');

  const metrics = useQuery({
    queryKey: ['metrics', keyword],
    queryFn: () => api.listMetrics({keyword: keyword || undefined}),
  });

  const tables = useQuery({queryKey: ['catalog-tables-all'], queryFn: () => api.catalogTables({})});

  const selectedTable: CatalogTable | undefined = useMemo(
    () => tables.data?.find((t) => String(t.id) === form.table_id),
    [tables.data, form.table_id],
  );

  const createMetric = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.createMetric(payload),
    onSuccess: () => {
      qc.invalidateQueries({queryKey: ['metrics']});
      setShowForm(false);
      setForm(EMPTY_FORM);
    },
    onError: (e: Error) => setFormError(e.message),
  });

  const deleteMetric = useMutation({
    mutationFn: (id: number) => api.deleteMetric(id),
    onSuccess: () => qc.invalidateQueries({queryKey: ['metrics']}),
  });

  const runQuery = useMutation({
    mutationFn: (m: MetricDefinition) =>
      api.runMetricQuery(m.id, {group_by: queryGroupBy.length ? queryGroupBy : undefined}),
    onSuccess: (data) => {
      setQueryResult(data);
      setQueryError('');
    },
    onError: (e: Error) => setQueryError(e.message),
  });

  const columns = [
    {key: 'metric', header: '指标', width: proportional(1.4), renderCell: (m: MetricDefinition) => (
      <VStack gap={0.5}>
        <HStack gap={2} vAlign="center">
          <Calculator size={15} className="muted" />
          <Text weight="semibold">{m.display_name}</Text>
          <Text type="supporting" className="mono muted">{m.name}</Text>
        </HStack>
        <Text type="supporting" style={{maxWidth: 420}}><span className="muted">{m.description || '暂无口径说明'}</span></Text>
      </VStack>
    )},
    {key: 'expression', header: '表达式', width: proportional(1.1), renderCell: (m: MetricDefinition) => (
      <VStack gap={0.5}>
        <Text className="mono">{m.expression}</Text>
        <HStack gap={1}>
          {m.unit && <Badge label={m.unit} variant="info" />}
          <Badge label={m.status === 'active' ? '启用' : '归档'} variant={m.status === 'active' ? 'success' : 'neutral'} />
        </HStack>
      </VStack>
    )},
    {key: 'table', header: '来源', width: proportional(1), renderCell: (m: MetricDefinition) => (
      <VStack gap={0.5}>
        <HStack gap={1} vAlign="center">
          <DbIcon size={13} className="muted" />
          <Text className="mono">{m.source ? m.source.name : '--'}</Text>
        </HStack>
        <Text type="supporting" className="mono muted">{m.table ? `${m.table.schema_name}.${m.table.table_name}` : '--'}</Text>
      </VStack>
    )},
    {key: 'dimensions', header: '允许维度', width: proportional(1.2), renderCell: (m: MetricDefinition) => (
      <HStack gap={1} wrap="wrap">
        {m.dimensions.length === 0 && <Text type="supporting"><span className="muted">无 (仅总量)</span></Text>}
        {m.dimensions.map((d) => <Badge key={d} label={d} variant="neutral" />)}
      </HStack>
    )},
    {key: 'actions', header: '', width: proportional(0.9), renderCell: (m: MetricDefinition) => (
      <HStack gap={1}>
        <Button
          label={queryTarget === m.id ? '收起结果' : '运行'}
          size="sm"
          variant="primary"
          icon={queryTarget === m.id ? undefined : <Play size={13} />}
          onClick={() => {
            setQueryTarget(queryTarget === m.id ? null : m.id);
            setQueryResult(null);
            setQueryGroupBy([]);
            setQueryError('');
          }}
        />
        <Button
          label="删除"
          size="sm"
          variant="ghost"
          icon={<Trash2 size={13} />}
          onClick={() => deleteMetric.mutate(m.id)}
        />
      </HStack>
    )},
  ];

  const submit = () => {
    if (!form.name || !form.display_name || !form.table_id || !form.measure) {
      setFormError('请填写指标名、显示名、来源表与度量表达式');
      return;
    }
    createMetric.mutate({
      name: form.name,
      display_name: form.display_name,
      description: form.description,
      table_id: Number(form.table_id),
      measure: form.measure,
      aggregation: form.aggregation,
      dimensions: form.dimensions,
      unit: form.unit || null,
      owner: 'admin',
    });
  };

  const metricForQuery = queryTarget != null ? metrics.data?.find((m) => m.id === queryTarget) : undefined;

  return (
    <div className="page-stack">
      <PageHeader
        title="指标语义层"
        description="统一指标口径: 同名同义, 每次查询返回可追溯的数字与定义"
        actions={
          <>
            <TextInput
              label="搜索"
              isLabelHidden
              type="text"
              value={keyword}
              onChange={setKeyword}
              description="按指标名 / 口径检索"
              style={{width: 260}}
            />
            <Button label="新建指标" icon={<Plus size={15} />} onClick={() => setShowForm(!showForm)} />
          </>
        }
      />

      {showForm && (
        <Card variant="muted" padding={4}>
          <VStack gap={3}>
            <HStack hAlign="between" vAlign="center">
              <Text weight="semibold">新建指标定义</Text>
              <Badge label="口径即契约: 绑定目录表, 度量表达式须引用已注册列" variant="neutral" />
            </HStack>
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12}}>
              <TextInput label="指标名" value={form.name} onChange={(v) => setForm({...form, name: v})} description="snake_case, 唯一, 如 total_revenue" placeholder="total_revenue" />
              <TextInput label="显示名" value={form.display_name} onChange={(v) => setForm({...form, display_name: v})} description="中文名称" placeholder="销售总额" />
              <TextInput label="单位" value={form.unit} onChange={(v) => setForm({...form, unit: v})} description="可选, 如 元/件/%" placeholder="元" />
              <Selector
                label="来源表"
                value={form.table_id}
                onChange={(v) => {
                  const next: NewMetricForm = {...form, table_id: v, dimensions: []};
                  const t = tables.data?.find((x) => String(x.id) === v);
                  if (t) next.dimensions = t.columns.filter((c) => c.data_type !== 'unknown').map((c) => c.column_name);
                  setForm(next);
                }}
                options={(tables.data ?? []).map((t) => ({label: `${t.schema_name}.${t.table_name} (${t.row_count} 行)`, value: String(t.id)}))}
                description="绑定到元数据目录中的表"
                isRequired
              />
              <Selector
                label="聚合方式"
                value={form.aggregation}
                onChange={(v) => setForm({...form, aggregation: v})}
                options={AGG_OPTIONS}
                isRequired
              />
              <TextInput label="度量表达式" value={form.measure} onChange={(v) => setForm({...form, measure: v})} description="支持 + - * / 与括号, 如 unit_price * quantity" placeholder="unit_price * quantity" isRequired />
            </div>
            <TextArea
              label="口径定义"
              value={form.description}
              onChange={(v) => setForm({...form, description: v})}
              rows={2}
              placeholder="例如: 订单金额合计, 含全部订单状态 (取消单计入)"
            />
            <CheckboxList
              label="允许下钻的维度"
              value={form.dimensions}
              onChange={(v) => setForm({...form, dimensions: v})}
              description="选择该指标可下钻的维度列; 留空则仅返回总量"
            >
              {(selectedTable?.columns ?? []).map((c) => (
                <CheckboxListItem key={c.column_name} label={`${c.column_name} (${c.data_type})`} value={c.column_name} />
              ))}
            </CheckboxList>
            {formError && <Text style={{color: '#d64545'}}>{formError}</Text>}
            <HStack gap={2}>
              <Button label="保存指标" variant="primary" onClick={submit} isLoading={createMetric.isPending} />
              <Button label="取消" variant="ghost" onClick={() => { setShowForm(false); setForm(EMPTY_FORM); setFormError(''); }} />
            </HStack>
          </VStack>
        </Card>
      )}

      {metrics.isLoading ? (
        <Text type="supporting">加载中...</Text>
      ) : metrics.data && metrics.data.length > 0 ? (
        <VStack gap={3}>
          {metrics.data.map((m) => (
            <Card key={m.id} variant={queryTarget === m.id ? 'muted' : 'default'} padding={0}>
              <Table data={[m] as never} columns={columns as never} density="compact" dividers="rows" hasHover />

              {queryTarget === m.id && metricForQuery && (
                <div style={{padding: '16px'}}>
                  <VStack gap={3}>
                    <HStack hAlign="between" vAlign="center" wrap="wrap">
                      <HStack gap={2} vAlign="center">
                        <TrendingUp size={15} className="muted" />
                        <Text weight="semibold">指标查询</Text>
                        <Text type="supporting" className="mono muted">{metricForQuery.expression}</Text>
                      </HStack>
                      <HStack gap={2}>
                        <CheckboxList
                          label="下钻维度"
                          isLabelHidden
                          value={queryGroupBy}
                          onChange={setQueryGroupBy}
                        >
                          {metricForQuery.dimensions.map((d) => (
                            <CheckboxListItem key={d} label={d} value={d} />
                          ))}
                        </CheckboxList>
                        <Button label="运行" variant="primary" icon={<Play size={13} />} onClick={() => runQuery.mutate(metricForQuery)} isLoading={runQuery.isPending} />
                      </HStack>
                    </HStack>

                    {queryError && <Text style={{color: '#d64545'}}>{queryError}</Text>}

                    {queryResult && (
                      <>
                        {queryResult.group_by.length === 0 ? (
                          <Card variant="default" style={{padding: 16, display: 'flex', alignItems: 'center', gap: 12}}>
                            <Text type="supporting">总量结果</Text>
                            <Text size="xl" weight="bold" className="mono" style={{fontSize: 28}}>
                              {formatValue(queryResult.rows[0]?.value, metricForQuery.unit)}
                            </Text>
                            <Text type="supporting" className="muted">
                              执行耗时 {queryResult.duration_ms} ms · 表达式 {queryResult.expression}
                            </Text>
                          </Card>
                        ) : (
                          <Card variant="default" padding={0}>
                            <Table
                              data={queryResult.rows as never}
                              columns={[
                                ...queryResult.group_by.map((d) => ({
                                  key: d,
                                  header: d,
                                  width: proportional(1),
                                  renderCell: (r: Record<string, unknown>) => <Text className="mono">{String(r[d] ?? '--')}</Text>,
                                })),
                                {key: 'value', header: '数值', width: proportional(1), renderCell: (r: Record<string, unknown> & {value: number | string | null}) => (
                                  <Text weight="semibold" className="mono">{formatValue(r.value, metricForQuery.unit)}</Text>
                                )},
                              ] as never}
                              density="compact"
                              dividers="rows"
                            />
                          </Card>
                        )}

                        <HStack gap={2} wrap="wrap">
                          <Badge label={`来源: ${queryResult.source.name}`} variant="info" />
                          <Badge label={`表: ${queryResult.source.schema}.${queryResult.source.table}`} variant="neutral" />
                          <Badge label={`口径: ${metricForQuery.display_name}`} variant="neutral" />
                          <Text type="supporting" className="muted">执行于 {queryResult.executed_at}</Text>
                        </HStack>
                      </>
                    )}
                  </VStack>
                </div>
              )}
            </Card>
          ))}
        </VStack>
      ) : (
        <EmptyState
          title={keyword ? `未找到包含「${keyword}」的指标` : '指标语义层为空'}
          description={keyword ? '尝试更换关键词' : '点击右上角「新建指标」注册第一个统一口径的指标'}
        />
      )}
    </div>
  );
}
