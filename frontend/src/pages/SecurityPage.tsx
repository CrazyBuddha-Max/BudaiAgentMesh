import {useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api} from '@/api/client';
import {PageHeader} from '@/components/PageHeader';
import {Table, proportional, pixel} from '@astryxdesign/core/Table';
import {Card} from '@astryxdesign/core/Card';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Badge} from '@astryxdesign/core/Badge';
import {Button} from '@astryxdesign/core/Button';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Selector} from '@astryxdesign/core/Selector';
import {useToast} from '@astryxdesign/core/Toast';
import {ShieldCheck, ScanSearch, ScrollText, GitBranch, EyeOff, ShieldBan, Database as DbIcon, Building2, Network as NetworkIcon} from 'lucide-react';
import type {AuditLogEntry, ColumnPolicy, FederationPeer, FederationResult, LifecycleData, LineageGraph, MaskingPolicy, TenantInfo} from '@/api/types';

interface UserRow {
  username: string;
  role: string;
  level: string;
  capabilities: string[];
}

const USERS: UserRow[] = [
  {username: 'admin', role: '管理员', level: '3', capabilities: ['数据源管理', '采集执行', '目录检索', '治理配置', '观测']},
  {username: 'analyst', role: '分析师', level: '2', capabilities: ['数据源管理', '采集执行', '目录检索', '观测']},
  {username: 'viewer', role: '访客', level: '1', capabilities: ['目录检索', '观测']},
];

const MATRIX: {capability: string; admin: boolean; analyst: boolean; viewer: boolean}[] = [
  {capability: '浏览数据资产', admin: true, analyst: true, viewer: true},
  {capability: '接入 / 编辑数据源', admin: true, analyst: true, viewer: false},
  {capability: '测试连接', admin: true, analyst: true, viewer: false},
  {capability: '执行采集入库', admin: true, analyst: true, viewer: false},
  {capability: '删除数据源', admin: true, analyst: true, viewer: false},
  {capability: '治理策略配置', admin: true, analyst: false, viewer: false},
];

const CAPS: {name: string; desc: string; stage: string}[] = [
  {name: '认证 (JWT)', desc: '令牌签发与校验, 内置账号 RBAC 角色模型', stage: '已启用'},
  {name: '权限模型 (RBAC)', desc: 'viewer / analyst / admin 三级角色门槛', stage: '已启用'},
  {name: '动态脱敏', desc: '敏感列识别 + 按角色动态掩码 (手机/身份证/银行卡/邮箱/姓名/地址)', stage: '已启用'},
  {name: '审计日志', desc: '登录/采集/指标查询/数据采样/Agent 任务全链路留痕, 独立会话写入', stage: '已启用'},
  {name: '数据血缘', desc: '源表 → 指标 → 任务 → 结果, 图结构可查询可追溯', stage: '已启用'},
  {name: '细粒度列级权限', desc: '按角色禁止访问指定列, 与动态脱敏叠加生效', stage: '已启用'},
  {name: '生命周期治理', desc: '保留期策略 + 状态评估 (活跃/临期/过期), 到期时间自动计算', stage: '已启用'},
];

export function SecurityPage() {
  const cell = (ok: boolean) => (
    <span className={`matrix-cell ${ok ? 'matrix-yes' : 'matrix-no'}`}>{ok ? '有' : '无'}</span>
  );

  // M3: 审计 / 血缘 / 脱敏策略
  const audit = useQuery({queryKey: ['audit-logs'], queryFn: () => api.auditLogs({limit: 50})});
  const lineage = useQuery({queryKey: ['lineage'], queryFn: api.lineage});
  const masking = useQuery({queryKey: ['masking-policies'], queryFn: api.maskingPolicies});

  // M5: 列级权限 / 生命周期
  const qc = useQueryClient();
  const toast = useToast();
  const policies = useQuery({queryKey: ['column-policies'], queryFn: api.columnPolicies});
  const lifecycle = useQuery({queryKey: ['lifecycle'], queryFn: api.lifecycle});
  const tables = useQuery({queryKey: ['catalog-tables-all'], queryFn: () => api.catalogTables({})});
  const [polRole, setPolRole] = useState('analyst');
  const [polTable, setPolTable] = useState('');
  const [polColumn, setPolColumn] = useState('');

  // M6: 多租户 / 联邦接入
  const [tenantCode, setTenantCode] = useState('');
  const [tenantName, setTenantName] = useState('');
  const [peerName, setPeerName] = useState('');
  const [peerUrl, setPeerUrl] = useState('');
  const [peerToken, setPeerToken] = useState('');
  const tenants = useQuery({queryKey: ['tenants'], queryFn: api.tenants});
  const addTenant = useMutation({
    mutationFn: () => api.createTenant(tenantCode.trim(), tenantName.trim()),
    onSuccess: () => {
      toast({body: '租户已创建'});
      setTenantCode('');
      setTenantName('');
      qc.invalidateQueries({queryKey: ['tenants']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '创建失败', type: 'error'}),
  });
  const toggleTenant = useMutation({
    mutationFn: ({code, status}: {code: string; status: string}) => api.setTenantStatus(code, status),
    onSuccess: () => qc.invalidateQueries({queryKey: ['tenants']}),
  });
  const peers = useQuery({queryKey: ['federation-peers'], queryFn: api.federationPeers});
  const addPeer = useMutation({
    mutationFn: () => api.createFederationPeer(peerName.trim(), peerUrl.trim(), peerToken.trim() || undefined),
    onSuccess: () => {
      toast({body: '联邦实例已注册'});
      setPeerName('');
      setPeerUrl('');
      setPeerToken('');
      qc.invalidateQueries({queryKey: ['federation-peers']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '注册失败', type: 'error'}),
  });
  const removePeer = useMutation({
    mutationFn: (id: number) => api.deleteFederationPeer(id),
    onSuccess: () => qc.invalidateQueries({queryKey: ['federation-peers']}),
  });
  const fedSearch = useQuery({queryKey: ['federation-search'], queryFn: () => api.federationSearch(), enabled: false});

  const addPolicy = useMutation({
    mutationFn: () => api.createColumnPolicy(polRole, polColumn, polTable ? Number(polTable) : undefined),
    onSuccess: () => {
      toast({body: '列权限规则已添加'});
      setPolColumn('');
      qc.invalidateQueries({queryKey: ['column-policies']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '添加失败', type: 'error'}),
  });

  const removePolicy = useMutation({
    mutationFn: (id: number) => api.deleteColumnPolicy(id),
    onSuccess: () => {
      toast({body: '规则已删除'});
      qc.invalidateQueries({queryKey: ['column-policies']});
    },
  });

  const auditColumns = [
    {key: 'created_at', header: '时间', width: pixel(150), renderCell: (l: AuditLogEntry) => (
      <Text type="supporting" className="mono">{l.created_at.slice(0, 19).replace('T', ' ')}</Text>
    )},
    {key: 'actor', header: '操作者', width: proportional(1), renderCell: (l: AuditLogEntry) => (
      <Text weight="semibold" className="mono">{l.actor}</Text>
    )},
    {key: 'action', header: '动作', width: proportional(1.1), renderCell: (l: AuditLogEntry) => (
      <Badge label={l.action} variant="neutral" />
    )},
    {key: 'target', header: '目标', width: proportional(1.2), renderCell: (l: AuditLogEntry) => (
      <Text className="mono">{l.target_type}{l.target_id ? `:${l.target_id}` : ''}</Text>
    )},
    {key: 'detail', header: '详情', width: proportional(2), renderCell: (l: AuditLogEntry) => (
      <Text type="supporting" className="muted">{JSON.stringify(l.detail ?? {})}</Text>
    )},
  ];

  const lineageData: LineageGraph = lineage.data ?? {nodes: [], edges: []};
  const byId = new Map(lineageData.nodes.map((n) => [n.id, n]));

  const columns = [
    {key: 'username', header: '账号', width: proportional(1.2), renderCell: (r: UserRow) => (
      <Text weight="semibold" className="mono">{r.username}</Text>
    )},
    {key: 'role', header: '角色', width: proportional(0.8), renderCell: (r: UserRow) => (
      <Badge label={r.role} variant={r.level === '3' ? 'success' : r.level === '2' ? 'info' : 'neutral'} />
    )},
    {key: 'level', header: '级别', width: proportional(0.5), renderCell: (r: UserRow) => (
      <Text className="mono">L{r.level}</Text>
    )},
    {key: 'capabilities', header: '能力范围', width: proportional(2.4), renderCell: (r: UserRow) => (
      <HStack gap={1}>
        {r.capabilities.map((c) => <Badge key={c} label={c} variant="neutral" />)}
      </HStack>
    )},
  ];

  return (
    <div className="page-stack">
      <PageHeader
        title="安全治理"
        description="每一次数据供给都可授权、可脱敏、可审计、可溯源"
      />

      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={4}>
          <HStack gap={2} vAlign="center">
            <ShieldCheck size={18} />
            <Text weight="semibold">RBAC 权限矩阵</Text>
          </HStack>
          <Table
            data={MATRIX as never}
            columns={[
              {key: 'capability', header: '能力', width: proportional(3), renderCell: (r: (typeof MATRIX)[number]) => <Text>{r.capability}</Text>},
              {key: 'admin', header: '管理员', width: proportional(1), renderCell: (r: (typeof MATRIX)[number]) => cell(r.admin)},
              {key: 'analyst', header: '分析师', width: proportional(1), renderCell: (r: (typeof MATRIX)[number]) => cell(r.analyst)},
              {key: 'viewer', header: '访客', width: proportional(1), renderCell: (r: (typeof MATRIX)[number]) => cell(r.viewer)},
            ] as never}
            density="compact"
            dividers="rows"
          />
        </VStack>
      </Card>

      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <ScanSearch size={18} />
            <Text weight="semibold">内置账号</Text>
          </HStack>
          <Table data={USERS as never} columns={columns as never} density="compact" dividers="rows" />
        </VStack>
      </Card>

      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>治理能力演进</Text>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12}}>
          {CAPS.map((cap) => (
            <Card key={cap.name} variant="default" style={{padding: 14}}>
              <VStack gap={1}>
                <HStack gap={2} vAlign="center" hAlign="between">
                  <Text weight="semibold">{cap.name}</Text>
                  <Badge label={cap.stage} variant={cap.stage.startsWith('已') ? 'success' : 'neutral'} />
                </HStack>
                <Text type="supporting"><span className="muted">{cap.desc}</span></Text>
              </VStack>
            </Card>
          ))}
        </div>
      </div>

      {/* M3: 动态脱敏策略 */}
      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <EyeOff size={18} />
            <Text weight="semibold">动态脱敏策略</Text>
            <Text type="supporting"><span className="muted">viewer/analyst 查询时 PII 自动掩码, admin 可见明文</span></Text>
          </HStack>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12}}>
            {(masking.data ?? []).map((p: MaskingPolicy) => (
              <Card key={p.sensitive_type} variant="default" style={{padding: 14}}>
                <HStack hAlign="between">
                  <Text weight="semibold">{p.label}</Text>
                  <Badge label={p.sensitive_type} variant="info" />
                </HStack>
                <Text className="mono" style={{margin: '6px 0', color: '#2f6db8'}}>{p.example}</Text>
                <Text type="supporting" className="mono muted">{p.patterns.slice(0, 3).join(' | ')}</Text>
              </Card>
            ))}
          </div>
        </VStack>
      </Card>

      {/* M3: 审计日志 */}
      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <ScrollText size={18} />
            <Text weight="semibold">审计日志 ({audit.data?.length ?? 0})</Text>
            <Text type="supporting"><span className="muted">全链路操作留痕: 谁 / 何时 / 访问了什么</span></Text>
          </HStack>
          <Table data={(audit.data ?? []) as never} columns={auditColumns as never} density="compact" dividers="rows" />
        </VStack>
      </Card>

      {/* M3: 数据血缘 */}
      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <GitBranch size={18} />
            <Text weight="semibold">数据血缘 ({lineageData.edges.length} 条链路)</Text>
            <Text type="supporting"><span className="muted">源表 → 指标 → 任务 → 结果, 全链路可追溯</span></Text>
          </HStack>
          {lineageData.edges.length === 0 ? (
            <Text type="supporting"><span className="muted">暂无血缘记录, 执行一次指标查询或 Agent 任务后自动生成</span></Text>
          ) : (
            <VStack gap={2}>
              {lineageData.edges.slice(0, 30).map((e, i) => (
                <HStack key={i} gap={2} vAlign="center">
                  <Badge label={byId.get(e.from)?.label ?? e.from} variant={byId.get(e.from)?.kind === 'source' ? 'blue' : 'neutral'} />
                  <Text type="supporting" className="muted">→ {e.action} →</Text>
                  <Badge label={byId.get(e.to)?.label ?? e.to} variant={byId.get(e.to)?.kind === 'consumer' ? 'green' : 'neutral'} />
                </HStack>
              ))}
            </VStack>
          )}
        </VStack>
      </Card>
      {/* M5: 细粒度列级权限 */}
      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <ShieldBan size={18} />
            <Text weight="semibold">细粒度列级权限</Text>
            <Text type="supporting"><span className="muted">按角色禁止访问指定列, 与动态脱敏叠加生效</span></Text>
          </HStack>
          <HStack gap={2} vAlign="end" wrap="wrap">
            <Selector
              label="角色"
              value={polRole}
              onChange={setPolRole}
              options={[
                {label: '访客 (viewer)', value: 'viewer'},
                {label: '分析师 (analyst)', value: 'analyst'},
                {label: '管理员 (admin)', value: 'admin'},
              ]}
            />
            <Selector
              label="数据表"
              value={polTable}
              onChange={setPolTable}
              options={[
                {label: '全部表', value: ''},
                ...(tables.data ?? []).map((t) => ({
                  label: `${t.schema_name}.${t.table_name}`,
                  value: String(t.id),
                })),
              ]}
            />
            <TextInput
              label="禁止的列"
              value={polColumn}
              onChange={setPolColumn}
              placeholder="列名, 如 phone; 输入 * 禁止整表"
              style={{minWidth: 220}}
            />
            <Button
              label="添加规则"
              variant="primary"
              isDisabled={!polColumn || !polRole}
              isLoading={addPolicy.isPending}
              onClick={() => addPolicy.mutate()}
            />
          </HStack>
          {policies.data && policies.data.length > 0 ? (
            <VStack gap={2}>
              {(policies.data as ColumnPolicy[]).map((p) => (
                <HStack key={p.id} gap={2} vAlign="center">
                  <Badge label={p.role} variant="info" />
                  <Badge label={p.table_id ? `表#${p.table_id}` : '全部表'} variant="neutral" />
                  <Text className="mono">{p.column_name}</Text>
                  <Button label="删除" size="sm" variant="ghost" onClick={() => removePolicy.mutate(p.id)} />
                </HStack>
              ))}
            </VStack>
          ) : (
            <Text type="supporting"><span className="muted">暂无规则, 添加后对应角色的数据访问将自动剔除该列</span></Text>
          )}
        </VStack>
      </Card>

      {/* M5: 数据生命周期 */}
      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <DbIcon size={18} />
            <Text weight="semibold">数据生命周期</Text>
            <Text type="supporting"><span className="muted">保留期策略: 自最近采集起算, 临期/到期自动标记</span></Text>
            <HStack gap={1}>
              <Badge label={`无策略 ${lifecycle.data?.summary.by_status['no-policy'] ?? 0}`} variant="neutral" />
              <Badge label={`活跃 ${lifecycle.data?.summary.by_status['active'] ?? 0}`} variant="success" />
              <Badge label={`临期 ${lifecycle.data?.summary.by_status['expiring'] ?? 0}`} variant="warning" />
              <Badge label={`过期 ${lifecycle.data?.summary.by_status['expired'] ?? 0}`} variant="error" />
            </HStack>
          </HStack>
          {(lifecycle.data?.items ?? []).length > 0 ? (
            <VStack gap={2}>
              {(lifecycle.data as LifecycleData).items.map((item) => (
                <HStack key={item.source_id} gap={2} vAlign="center">
                  <Text weight="semibold" style={{minWidth: 140}}>{item.source_name}</Text>
                  <Badge label={item.status_label} variant={item.status === 'expired' ? 'error' : item.status === 'expiring' ? 'warning' : item.status === 'active' ? 'success' : 'neutral'} />
                  <Text type="supporting" className="mono muted">
                    保留期 {item.retention_days ? `${item.retention_days} 天` : '未设置'}
                    {item.expires_at ? ` · 到期 ${item.expires_at.slice(0, 10)}` : ''}
                  </Text>
                </HStack>
              ))}
            </VStack>
          ) : (
            <Text type="supporting"><span className="muted">暂无数据源, 接入后在此设置保留期</span></Text>
          )}
        </VStack>
      </Card>

      {/* M6: 多租户 */}
      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <Building2 size={18} />
            <Text weight="semibold">多租户 ({tenants.data?.length ?? 0})</Text>
            <Text type="supporting"><span className="muted">数据接入层按租户硬隔离, 越权访问视为不存在; 账号归属由 BUILTIN_USERS 第 4 段声明</span></Text>
          </HStack>
          <HStack gap={2} vAlign="end" wrap="wrap">
            <TextInput label="租户编码" value={tenantCode} onChange={setTenantCode} placeholder="如 acme" style={{minWidth: 160}} />
            <TextInput label="租户名称" value={tenantName} onChange={setTenantName} placeholder="如 Acme 集团" style={{minWidth: 180}} />
            <Button label="新建租户" variant="primary" isLoading={addTenant.isPending} isDisabled={!tenantCode || !tenantName} onClick={() => addTenant.mutate()} />
          </HStack>
          {(tenants.data ?? []).length > 0 ? (
            <VStack gap={2}>
              {(tenants.data as TenantInfo[]).map((t) => (
                <HStack key={t.id} gap={2} vAlign="center">
                  <Badge label={t.code} variant="info" />
                  <Text weight="semibold">{t.name}</Text>
                  <Badge label={t.status} variant={t.status === 'active' ? 'success' : 'neutral'} />
                  <Button label={t.status === 'active' ? '停用' : '启用'} size="sm" variant="ghost" onClick={() => toggleTenant.mutate({code: t.code, status: t.status === 'active' ? 'disabled' : 'active'})} />
                </HStack>
              ))}
            </VStack>
          ) : (
            <Text type="supporting"><span className="muted">暂无租户, 默认账号归属 default 租户</span></Text>
          )}
        </VStack>
      </Card>

      {/* M6: 联邦接入 */}
      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <NetworkIcon size={18} />
            <Text weight="semibold">联邦接入 ({peers.data?.length ?? 0})</Text>
            <Text type="supporting"><span className="muted">注册远端 BudaiAgentMesh 实例, 目录/数据跨实例透传可查</span></Text>
          </HStack>
          <HStack gap={2} vAlign="end" wrap="wrap">
            <TextInput label="实例名称" value={peerName} onChange={setPeerName} placeholder="如 华东节点" style={{minWidth: 140}} />
            <TextInput label="地址" value={peerUrl} onChange={setPeerUrl} placeholder="如 http://peer:8000" style={{minWidth: 220}} />
            <TextInput label="令牌 (可选)" value={peerToken} onChange={setPeerToken} placeholder="远端访问令牌" style={{minWidth: 180}} />
            <Button label="注册实例" variant="primary" isLoading={addPeer.isPending} isDisabled={!peerName || !peerUrl} onClick={() => addPeer.mutate()} />
          </HStack>
          {(peers.data ?? []).length > 0 ? (
            <VStack gap={2}>
              {(peers.data as FederationPeer[]).map((p) => (
                <HStack key={p.id} gap={2} vAlign="center">
                  <Badge label={p.name} variant="blue" />
                  <Text className="mono muted">{p.base_url}</Text>
                  <Badge label={p.status} variant={p.status === 'active' ? 'success' : 'neutral'} />
                  <Button label="删除" size="sm" variant="ghost" onClick={() => removePeer.mutate(p.id)} />
                </HStack>
              ))}
              <Button label="联邦检索" size="sm" variant="ghost" isLoading={fedSearch.isFetching} onClick={() => fedSearch.refetch()} />
              {(fedSearch.data ?? []).length > 0 && (
                <VStack gap={1}>
                  {(fedSearch.data as FederationResult[]).map((r, i) => (
                    <Text key={i} type="supporting" className="muted">
                      {r.ok ? `[${r.peer}] 命中 ${(r.data ?? []).length} 张表` : `[${r.peer}] ${r.error}`}
                    </Text>
                  ))}
                </VStack>
              )}
            </VStack>
          ) : (
            <Text type="supporting"><span className="muted">暂无联邦实例, 注册后可跨实例检索目录</span></Text>
          )}
        </VStack>
      </Card>
    </div>
  );
}
