import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from '@/api/client';
import {PageHeader} from '@/components/PageHeader';
import {QualityBar} from '@/components/QualityBar';
import {Table, proportional, pixel} from '@astryxdesign/core/Table';
import {Button} from '@astryxdesign/core/Button';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Text} from '@astryxdesign/core/Text';
import {Card} from '@astryxdesign/core/Card';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Badge} from '@astryxdesign/core/Badge';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {ChevronDown, ChevronUp, KeyRound, Database as DbIcon} from 'lucide-react';
import type {CatalogColumn, CatalogTable} from '@/api/types';

export function CatalogPage() {
  const [keyword, setKeyword] = useState('');
  const [expanded, setExpanded] = useState<number | null>(null);

  const tables = useQuery({
    queryKey: ['catalog-tables', keyword],
    queryFn: () => api.catalogTables({keyword: keyword || undefined}),
  });

  const tableColumns = [
    {key: 'table_name', header: '表名', width: proportional(1.6), renderCell: (r: CatalogTable) => (
      <HStack gap={2} vAlign="center">
        <DbIcon size={15} className="muted" />
        <Text weight="semibold" className="mono">{r.schema_name}.{r.table_name}</Text>
      </HStack>
    )},
    {key: 'row_count', header: '行数', width: proportional(0.9), renderCell: (r: CatalogTable) => (
      <Text className="mono">{r.row_count.toLocaleString()}</Text>
    )},
    {key: 'columns', header: '列数', width: proportional(0.7), renderCell: (r: CatalogTable) => (
      <Text className="mono">{r.columns.length}</Text>
    )},
    {key: 'quality_score', header: '质量分', width: proportional(1.3), renderCell: (r: CatalogTable) => <QualityBar score={r.quality_score} />},
    {key: 'expand', header: '', width: pixel(92), renderCell: (r: CatalogTable) => (
      <Button
        label={expanded === r.id ? '收起' : '展开'}
        variant="ghost"
        size="sm"
        icon={expanded === r.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        onClick={() => setExpanded(expanded === r.id ? null : r.id)}
      />
    )},
  ];

  const columnColumns = [
    {key: 'column_name', header: '字段', width: proportional(1.5), renderCell: (c: CatalogColumn) => (
      <HStack gap={2} vAlign="center">
        <Text className="mono">{c.column_name}</Text>
        {c.is_primary_key && <KeyRound size={13} className="muted" />}
      </HStack>
    )},
    {key: 'data_type', header: '类型', width: proportional(1), renderCell: (c: CatalogColumn) => (
      <Badge label={c.data_type} variant="neutral" />
    )},
    {key: 'null_rate', header: '空值率', width: proportional(1), renderCell: (c: CatalogColumn) => (
      <Text className="mono">{(c.null_rate * 100).toFixed(1)}%</Text>
    )},
    {key: 'distinct_ratio', header: '区分度', width: proportional(1), renderCell: (c: CatalogColumn) => (
      <Text className="mono">{(c.distinct_ratio * 100).toFixed(1)}%</Text>
    )},
    {key: 'sample_values', header: '采样值', width: proportional(2), renderCell: (c: CatalogColumn) => (
      <HStack gap={1}>
        {(c.sample_values ?? []).slice(0, 3).map((v, i) => (
          <Badge key={i} label={String(v)} variant="neutral" />
        ))}
        {(c.sample_values?.length ?? 0) === 0 && <Text type="supporting"><span className="muted">无</span></Text>}
      </HStack>
    )},
  ];

  return (
    <div className="page-stack">
      <PageHeader
        title="元数据目录"
        description="Schema 注册中心: 检索表与字段, 查看质量初检画像"
        actions={
          <TextInput
            label="搜索"
            isLabelHidden
            type="text"
            value={keyword}
            onChange={setKeyword}
            description="按表名 / 字段名检索"
            style={{width: 280}}
          />
        }
      />

      {tables.isLoading ? (
        <Text type="supporting">加载中...</Text>
      ) : tables.data && tables.data.length > 0 ? (
        <VStack gap={3}>
          {tables.data.map((t) => (
            <Card key={t.id} variant={expanded === t.id ? 'muted' : 'default'} padding={0}>
              <Table data={[t] as never} columns={tableColumns as never} density="compact" dividers="rows" hasHover />
              {expanded === t.id && (
                <div style={{padding: '8px 16px 16px'}}>
                  <Text type="supporting" style={{margin: '10px 0 8px', display: 'block'}}>字段画像</Text>
                  <Table data={t.columns as never} columns={columnColumns as never} density="compact" dividers="grid" />
                </div>
              )}
            </Card>
          ))}
        </VStack>
      ) : (
        <EmptyState
          title={keyword ? `未找到包含「${keyword}」的表` : '目录为空'}
          description={keyword ? '尝试更换关键词或先执行数据源采集' : '先在数据源管理页执行一次采集, 目录将自动生成'}
        />
      )}
    </div>
  );
}
