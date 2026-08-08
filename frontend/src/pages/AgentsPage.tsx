import {useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api} from '@/api/client';
import {PageHeader} from '@/components/PageHeader';
import {StatusBadge} from '@/components/StatusBadge';
import {Table, proportional} from '@astryxdesign/core/Table';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Text} from '@astryxdesign/core/Text';
import {TextInput} from '@astryxdesign/core/TextInput';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {Badge} from '@astryxdesign/core/Badge';
import {Selector} from '@astryxdesign/core/Selector';
import {CheckboxList, CheckboxListItem} from '@astryxdesign/core/CheckboxList';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {useToast} from '@astryxdesign/core/Toast';
import type {AgentInfo, ToolInfo} from '@/api/types';
import {Bot, BrainCircuit, ChevronDown, ChevronRight, ExternalLink, Pencil, Plus, Trash2, Wrench, Layers} from 'lucide-react';
import {useAuthStore} from '@/store/auth';

export function AgentsPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = (user?.role ?? 'viewer') !== 'viewer';

  const [showCreate, setShowCreate] = useState(false);
  const [agentName, setAgentName] = useState('');
  const [agentDesc, setAgentDesc] = useState('');
  const [agentModelId, setAgentModelId] = useState('');
  const [agentCaps, setAgentCaps] = useState<string[]>(['knowledge_retrieval', 'data_access']);
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editModelId, setEditModelId] = useState('');
  const [expandedTool, setExpandedTool] = useState<string | null>(null);

  const agents = useQuery({queryKey: ['agents'], queryFn: api.listAgents});
  const tools = useQuery({queryKey: ['agent-tools'], queryFn: api.listTools});
  const templates = useQuery({queryKey: ['agent-templates'], queryFn: api.listTemplates});
  const bus = useQuery({queryKey: ['agent-bus'], queryFn: api.busStats, refetchInterval: 10_000});
  const providers = useQuery({queryKey: ['llm-providers'], queryFn: api.llmProviders});
  const caps = useQuery({queryKey: ['agent-capabilities'], queryFn: api.capabilities});

  const providerName = (id: number | null | undefined) =>
    providers.data?.find((p) => p.id === id)?.name ?? (id ? `提供方#${id}` : '默认');

  const createAgent = useMutation({
    mutationFn: () =>
      api.createAgent({
        name: agentName,
        description: agentDesc || undefined,
        llm_provider_id: agentModelId ? Number(agentModelId) : null,
        capabilities: agentCaps,
        tools: [],
      }),
    onSuccess: (a) => {
      toast({body: `Agent「${a.name}」已注册`});
      setShowCreate(false);
      setAgentName('');
      setAgentDesc('');
      setAgentModelId('');
      setAgentCaps(['knowledge_retrieval', 'data_access']);
      qc.invalidateQueries({queryKey: ['agents']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '创建失败', type: 'error'}),
  });

  const updateAgent = useMutation({
    mutationFn: () =>
      api.updateAgent(editId!, {
        name: editName,
        description: editDesc || null,
        llm_provider_id: editModelId ? Number(editModelId) : null,
      }),
    onSuccess: (a) => {
      toast({body: `Agent「${a.name}」已更新`});
      setEditId(null);
      qc.invalidateQueries({queryKey: ['agents']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '更新失败', type: 'error'}),
  });

  const deleteAgent = useMutation({
    mutationFn: (id: number) => api.deleteAgent(id),
    onSuccess: () => {
      toast({body: 'Agent 已删除'});
      qc.invalidateQueries({queryKey: ['agents']});
      qc.invalidateQueries({queryKey: ['agent-tasks']});
    },
  });

  const createFromTemplate = useMutation({
    mutationFn: ({key, name}: {key: string; name?: string}) => api.createFromTemplate(key, name),
    onSuccess: (a) => {
      toast({body: `已从模板创建 Agent「${a.name}」`});
      qc.invalidateQueries({queryKey: ['agents']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '创建失败', type: 'error'}),
  });

  const startEdit = (a: AgentInfo) => {
    setEditId(a.id);
    setEditName(a.name);
    setEditDesc(a.description ?? '');
    setEditModelId(a.llm_provider_id ? String(a.llm_provider_id) : '');
  };

  const agentColumns = [
    {key: 'name', header: 'Agent', width: proportional(1.4), renderCell: (a: AgentInfo) => (
      <HStack gap={2} vAlign="center">
        <Bot size={16} className="muted" />
        <div>
          <Text weight="semibold">{a.name}</Text>
          <Text type="supporting"><span className="muted">{a.description ?? '暂无描述'}</span></Text>
        </div>
      </HStack>
    )},
    {key: 'model', header: '对接模型', width: proportional(0.9), renderCell: (a: AgentInfo) => (
      <HStack gap={1} vAlign="center">
        <BrainCircuit size={14} className="muted" />
        <Badge label={providerName(a.llm_provider_id)} variant={a.llm_provider_id ? 'success' : 'neutral'} />
      </HStack>
    )},
    {key: 'capabilities', header: '能力声明', width: proportional(1.3), renderCell: (a: AgentInfo) => (
      <HStack gap={1} wrap="wrap">
        {a.capabilities.map((c) => <Badge key={c} label={c} variant="neutral" />)}
      </HStack>
    )},
    {key: 'status', header: '状态', width: proportional(0.6), renderCell: (a: AgentInfo) => <StatusBadge status={a.status} />},
    {key: 'actions', header: '', width: proportional(0.7), renderCell: (a: AgentInfo) => (
      <HStack gap={1}>
        <Button label="编辑" size="sm" variant="ghost" icon={<Pencil size={13} />} isDisabled={!canEdit} onClick={() => startEdit(a)} />
        <Button label="删除" size="sm" variant="ghost" icon={<Trash2 size={13} />} isDisabled={!canEdit} onClick={() => deleteAgent.mutate(a.id)} />
      </HStack>
    )},
  ];

  return (
    <div className="page-stack">
      <PageHeader
        title="Agent 协同"
        description="多 Agent 协同层: 注册中心 / 工具注册中心 (MCP) / 大模型绑定"
        actions={
          canEdit ? (
            <Button
              label={showCreate ? '收起' : '注册 Agent'}
              variant="primary"
              icon={<Plus size={15} />}
              onClick={() => setShowCreate(!showCreate)}
            />
          ) : undefined
        }
      />

      {showCreate && canEdit && (
        <Card variant="muted" style={{padding: 20}}>
          <VStack gap={3}>
            <Text weight="semibold">注册新 Agent</Text>
            <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12}}>
              <TextInput label="Agent 名称" value={agentName} onChange={setAgentName} isRequired placeholder="如 经营分析助手" />
              <TextInput label="职责描述" value={agentDesc} onChange={setAgentDesc} placeholder="负责检索业务口径并定位数据" />
            </div>
            <CheckboxList
              label="能力声明 (来自能力注册表, 可多选)"
              value={agentCaps}
              onChange={setAgentCaps}
              description="编排会按能力动态分工; 新能力在注册表声明即可"
            >
              {(caps.data ?? []).map((c) => (
                <CheckboxListItem key={c.code} label={`${c.label} (${c.code}) · ${c.description}`} value={c.code} />
              ))}
            </CheckboxList>
            <Selector
              label="对接模型 (留空 = 默认提供方)"
              value={agentModelId}
              onChange={setAgentModelId}
              options={[
                {label: '默认提供方 (未绑定)', value: ''},
                ...(providers.data ?? []).map((p) => ({
                  label: `${p.name} · ${p.model}${p.is_default ? ' (默认)' : ''}`,
                  value: String(p.id),
                })),
              ]}
            />
            <HStack hAlign="end">
              <Button label="注册" variant="primary" isDisabled={!agentName} isLoading={createAgent.isPending} onClick={() => createAgent.mutate()} />
            </HStack>
          </VStack>
        </Card>
      )}

      {/* 编辑表单 */}
      {editId !== null && (
        <Card variant="muted" style={{padding: 20}}>
          <VStack gap={3}>
            <HStack gap={2} vAlign="center">
              <Pencil size={16} />
              <Text weight="semibold">编辑 Agent #{editId}</Text>
            </HStack>
            <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12}}>
              <TextInput label="Agent 名称" value={editName} onChange={setEditName} isRequired />
              <TextInput label="职责描述" value={editDesc} onChange={setEditDesc} />
            </div>
            <Selector
              label="对接模型"
              value={editModelId}
              onChange={setEditModelId}
              options={[
                {label: '默认提供方 (未绑定)', value: ''},
                ...(providers.data ?? []).map((p) => ({
                  label: `${p.name} · ${p.model}${p.is_default ? ' (默认)' : ''}`,
                  value: String(p.id),
                })),
              ]}
            />
            <HStack gap={2} hAlign="end">
              <Button label="取消" variant="ghost" onClick={() => setEditId(null)} />
              <Button label="保存" variant="primary" isDisabled={!editName} isLoading={updateAgent.isPending} onClick={() => updateAgent.mutate()} />
            </HStack>
          </VStack>
        </Card>
      )}

      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center" hAlign="between">
            <HStack gap={2} vAlign="center">
              <Wrench size={17} />
              <Text weight="semibold">工具注册中心 ({tools.data?.length ?? 0})</Text>
              <Text type="supporting"><span className="muted">数据能力以标准 Schema 暴露, 由 MCP Server 供外部 Agent 调用</span></Text>
            </HStack>
            <Button
              label="MCP 端点 /mcp/mcp"
              size="sm"
              variant="ghost"
              icon={<ExternalLink size={13} />}
              onClick={() => window.open('http://127.0.0.1:8000/docs', '_blank')}
            />
          </HStack>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12}}>
            {(tools.data ?? []).map((t: ToolInfo) => {
              const params = Object.entries((t.parameters.properties as Record<string, unknown>) ?? {});
              const open = expandedTool === t.name;
              return (
                <Card
                  key={t.name}
                  variant="default"
                  style={{padding: 14, cursor: 'pointer'}}
                  onClick={() => setExpandedTool(open ? null : t.name)}
                >
                  <HStack gap={2} vAlign="center" hAlign="between">
                    <Text weight="semibold" className="mono">{t.name}</Text>
                    {open ? <ChevronDown size={14} className="muted" /> : <ChevronRight size={14} className="muted" />}
                  </HStack>
                  <Text type="supporting" style={{margin: '4px 0'}}><span className="muted">{t.description}</span></Text>
                  {open && (
                    <VStack gap={1} style={{marginTop: 8}}>
                      <Text type="supporting" className="mono muted">参数 ({params.length}):</Text>
                      {params.map(([k, v]) => (
                        <Text key={k} type="supporting" className="mono muted">
                          · <span style={{color: '#2f6db8'}}>{k}</span>: {(v as {description?: string}).description ?? (v as {type?: string}).type ?? ''}
                        </Text>
                      ))}
                      <Text type="supporting" className="muted" style={{marginTop: 6}}>
                        ↑ 通过 MCP 端点 <span className="mono">/mcp/mcp</span> 暴露给 Claude / Cursor 等外部 Agent
                      </Text>
                    </VStack>
                  )}
                </Card>
              );
            })}
          </div>
        </VStack>
      </Card>

      {/* M4: Agent 模板市场 */}
      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center" hAlign="between">
            <HStack gap={2} vAlign="center">
              <Layers size={17} />
              <Text weight="semibold">Agent 模板市场 ({templates.data?.length ?? 0})</Text>
              <Text type="supporting"><span className="muted">预置角色模板, 一键创建专业化 Agent</span></Text>
            </HStack>
            {bus.data && (
              <Badge label={`事件总线 ${bus.data.type} · 已发布 ${bus.data.published ?? 0}`} variant={bus.data.published ? 'success' : 'neutral'} />
            )}
          </HStack>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12}}>
            {(templates.data ?? []).map((tpl) => (
              <Card key={tpl.key} variant="default" style={{padding: 14}}>
                <HStack gap={2} vAlign="center">
                  <Bot size={15} className="muted" />
                  <Text weight="semibold">{tpl.name}</Text>
                </HStack>
                <Text type="supporting" style={{margin: '6px 0'}}><span className="muted">{tpl.description}</span></Text>
                <HStack gap={1} style={{marginBottom: 10}} wrap="wrap">
                  {tpl.capabilities.map((c) => <Badge key={c} label={c} variant="neutral" />)}
                </HStack>
                <Button
                  label="从模板创建"
                  size="sm"
                  variant="secondary"
                  icon={<Plus size={13} />}
                  isDisabled={!canEdit || createFromTemplate.isPending}
                  onClick={() => createFromTemplate.mutate({key: tpl.key})}
                />
              </Card>
            ))}
          </div>
        </VStack>
      </Card>

      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>Agent 注册中心 ({agents.data?.length ?? 0})</Text>
        {agents.isLoading ? (
          <Text type="supporting">加载中...</Text>
        ) : agents.data && agents.data.length > 0 ? (
          <Table data={agents.data as never} columns={agentColumns as never} density="compact" dividers="rows" hasHover />
        ) : (
          <EmptyState title="尚未注册 Agent" description="注册第一个 Agent, 再到问答工作台发起任务" />
        )}
      </div>
    </div>
  );
}
