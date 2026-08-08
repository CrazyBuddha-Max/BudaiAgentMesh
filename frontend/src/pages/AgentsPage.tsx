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
import {TextArea} from '@astryxdesign/core/TextArea';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {Badge} from '@astryxdesign/core/Badge';
import {Selector} from '@astryxdesign/core/Selector';
import {CheckboxList, CheckboxListItem} from '@astryxdesign/core/CheckboxList';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {useToast} from '@astryxdesign/core/Toast';
import type {AgentEvent, AgentInfo, AgentTask, ToolInfo} from '@/api/types';
import {Bot, Plus, Play, Trash2, Wrench, ListTree, Star, Layers} from 'lucide-react';
import {useAuthStore} from '@/store/auth';

const EVENT_LABEL: Record<string, {label: string; variant: string}> = {
  task_started: {label: '任务启动', variant: 'info'},
  plan: {label: '制定计划', variant: 'neutral'},
  tool_call: {label: '调用工具', variant: 'blue'},
  tool_result: {label: '工具结果', variant: 'green'},
  retrieval: {label: '知识检索', variant: 'cyan'},
  completion: {label: '任务完成', variant: 'success'},
  error: {label: '执行异常', variant: 'error'},
};

export function AgentsPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = (user?.role ?? 'viewer') !== 'viewer';

  const [showCreate, setShowCreate] = useState(false);
  const [agentName, setAgentName] = useState('');
  const [agentDesc, setAgentDesc] = useState('');
  const [objective, setObjective] = useState('');
  const [runTarget, setRunTarget] = useState<number | null>(null);
  const [mainAgentId, setMainAgentId] = useState('');
  const [collaborators, setCollaborators] = useState<string[]>([]);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');

  const agents = useQuery({queryKey: ['agents'], queryFn: api.listAgents});
  const tools = useQuery({queryKey: ['agent-tools'], queryFn: api.listTools});
  const tasks = useQuery({queryKey: ['agent-tasks'], queryFn: api.listTasks});
  const templates = useQuery({queryKey: ['agent-templates'], queryFn: api.listTemplates});
  const bus = useQuery({queryKey: ['agent-bus'], queryFn: api.busStats, refetchInterval: 10_000});

  const createAgent = useMutation({
    mutationFn: () =>
      api.createAgent({
        name: agentName,
        description: agentDesc || undefined,
        capabilities: ['knowledge_retrieval', 'data_access'],
        tools: [],
      }),
    onSuccess: (a) => {
      toast({body: `Agent「${a.name}」已注册`});
      setShowCreate(false);
      setAgentName('');
      setAgentDesc('');
      qc.invalidateQueries({queryKey: ['agents']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '创建失败', type: 'error'}),
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

  const createTask = useMutation({
    mutationFn: (agentId: number) =>
      api.createTask(
        agentId,
        objective,
        objective.slice(0, 40),
        collaborators.map(Number).filter((id) => id !== agentId),
      ),
    onSuccess: async (task) => {
      toast({body: `任务已创建 (#${task.id}), 协作团队已集结, 开始执行`});
      setObjective('');
      setRunTarget(task.id);
      qc.invalidateQueries({queryKey: ['agent-tasks']});
      await runTask.mutateAsync(task.id);
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '任务创建失败', type: 'error'}),
  });

  const runTask = useMutation({
    mutationFn: (taskId: number) => api.runTask(taskId),
    onSuccess: () => {
      toast({body: '任务执行完成' });
      qc.invalidateQueries({queryKey: ['agent-tasks']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '执行失败', type: 'error'}),
  });

  const submitFeedback = useMutation({
    mutationFn: (taskId: number) => api.submitFeedback(taskId, rating, comment || undefined),
    onSuccess: () => {
      toast({body: '反馈已提交, 将驱动系统迭代' });
      setComment('');
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '反馈提交失败', type: 'error'}),
  });

  const agentNameOf = (id: number) => agents.data?.find((a) => a.id === id)?.name ?? `Agent#${id}`;

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
    {key: 'capabilities', header: '能力声明', width: proportional(1.4), renderCell: (a: AgentInfo) => (
      <HStack gap={1} wrap="wrap">
        {a.capabilities.map((c) => <Badge key={c} label={c} variant="neutral" />)}
      </HStack>
    )},
    {key: 'status', header: '状态', width: proportional(0.6), renderCell: (a: AgentInfo) => <StatusBadge status={a.status} />},
    {key: 'actions', header: '', width: proportional(0.6), renderCell: (a: AgentInfo) => (
      <Button
        label="删除"
        size="sm"
        variant="ghost"
        icon={<Trash2 size={13} />}
        isDisabled={!canEdit}
        onClick={() => deleteAgent.mutate(a.id)}
      />
    )},
  ];

  const taskColumns = [
    {key: 'id', header: '#', width: proportional(0.4), renderCell: (t: AgentTask) => <Text className="mono">{t.id}</Text>},
    {key: 'objective', header: '目标', width: proportional(2), renderCell: (t: AgentTask) => (
      <Text style={{maxWidth: 460}}>{t.objective}</Text>
    )},
    {key: 'status', header: '状态', width: proportional(0.7), renderCell: (t: AgentTask) => <StatusBadge status={t.status} />},
    {key: 'result', header: '结果摘要', width: proportional(2), renderCell: (t: AgentTask) => (
      <Text type="supporting" className="mono" style={{maxWidth: 420, display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>
        {t.result?.split('\n').slice(1).join(' | ') || t.error || '--'}
      </Text>
    )},
    {key: 'actions', header: '', width: proportional(0.5), renderCell: (t: AgentTask) => (
      <Button
        label={runTarget === t.id ? '详情' : '查看'}
        size="sm"
        variant="ghost"
        onClick={() => setRunTarget(runTarget === t.id ? null : t.id)}
      />
    )},
  ];

  const selectedTask: AgentTask | undefined = tasks.data?.find((t) => t.id === runTarget) ?? undefined;

  return (
    <div className="page-stack">
      <PageHeader
        title="Agent 协同"
        description="多 Agent 协同层: 注册中心 / 工具注册中心 (MCP) / 任务编排与事件追溯"
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
            <HStack hAlign="end">
              <Button label="注册" variant="primary" isDisabled={!agentName} isLoading={createAgent.isPending} onClick={() => createAgent.mutate()} />
            </HStack>
          </VStack>
        </Card>
      )}

      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <Wrench size={17} />
            <Text weight="semibold">工具注册中心 ({tools.data?.length ?? 0})</Text>
            <Text type="supporting"><span className="muted">数据能力以标准 Schema 暴露, 已升级为完整 MCP Server (端点: /mcp/mcp)</span></Text>
          </HStack>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12}}>
            {(tools.data ?? []).map((t: ToolInfo) => (
              <Card key={t.name} variant="default" style={{padding: 14}}>
                <Text weight="semibold" className="mono">{t.name}</Text>
                <Text type="supporting" style={{margin: '4px 0'}}><span className="muted">{t.description}</span></Text>
                <Text type="supporting" className="mono muted">
                  参数: {Object.keys((t.parameters.properties as Record<string, unknown>) ?? {}).join(', ') || '无'}
                </Text>
              </Card>
            ))}
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

      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <Play size={17} />
            <Text weight="semibold">任务编排控制台</Text>
            <Text type="supporting"><span className="muted">目标 → 知识检索 → 目录检索 → 数据采样 → 主控汇总</span></Text>
          </HStack>
          <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12}}>
            <Selector
              label="主控 Agent"
              value={mainAgentId}
              onChange={(v) => setMainAgentId(v)}
              options={(agents.data ?? []).map((a) => ({label: `${a.name} (${(a.capabilities ?? []).join('/') || '通用'})`, value: String(a.id)}))}
              description="负责规划与汇总"
            />
            <CheckboxList
              label="协作 Agent"
              value={collaborators}
              onChange={setCollaborators}
              description="按能力分工: 检索员 / 分析员, 可多选"
            >
              {(agents.data ?? []).map((a) => (
                <CheckboxListItem key={a.id} label={`${a.name} (${(a.capabilities ?? []).join('/') || '通用'})`} value={String(a.id)} />
              ))}
            </CheckboxList>
          </div>
          <HStack gap={2} vAlign="end">
            <TextArea
              label="任务目标"
              value={objective}
              onChange={setObjective}
              rows={2}
              placeholder="例如: 分析订单数据, 参考毛利率口径说明"
              style={{flex: 1}}
            />
            <Button
              label="创建并执行"
              variant="primary"
              icon={<ListTree size={14} />}
              isDisabled={!canEdit || !objective.trim() || !mainAgentId}
              isLoading={createTask.isPending || runTask.isPending}
              onClick={() => createTask.mutate(Number(mainAgentId))}
            />
          </HStack>
        </VStack>
      </Card>

      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>Agent 注册中心 ({agents.data?.length ?? 0})</Text>
        {agents.isLoading ? (
          <Text type="supporting">加载中...</Text>
        ) : agents.data && agents.data.length > 0 ? (
          <Table data={agents.data as never} columns={agentColumns as never} density="compact" dividers="rows" hasHover />
        ) : (
          <EmptyState title="尚未注册 Agent" description="注册第一个 Agent, 开始编排数据任务" />
        )}
      </div>

      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>任务记录 ({tasks.data?.length ?? 0})</Text>
        {tasks.data && tasks.data.length > 0 ? (
          <Table data={tasks.data as never} columns={taskColumns as never} density="compact" dividers="rows" hasHover />
        ) : (
          <Text type="supporting"><span className="muted">暂无任务, 在上方控制台发起第一个任务</span></Text>
        )}
      </div>

      {selectedTask && (
        <Card variant="muted" style={{padding: 20}}>
          <VStack gap={3}>
            <HStack gap={2} vAlign="center" hAlign="between">
              <HStack gap={2} vAlign="center">
                <ListTree size={17} />
                <Text weight="semibold">任务 #{selectedTask.id} 执行链路</Text>
                <StatusBadge status={selectedTask.status} />
              </HStack>
              <Text type="supporting" className="mono muted">{selectedTask.created_at.slice(0, 19).replace('T', ' ')}</Text>
            </HStack>

            <VStack gap={1}>
              {selectedTask.events.map((e: AgentEvent) => {
                const meta = EVENT_LABEL[e.event_type] ?? {label: e.event_type, variant: 'neutral'};
                const payload = e.payload as Record<string, unknown> | null;
                const summary =
                  e.event_type === 'tool_call'
                    ? `工具 ${String(payload?.tool ?? '')} 参数 ${JSON.stringify(payload?.args ?? {})}`
                    : e.event_type === 'tool_result'
                      ? String(payload?.summary ?? '')
                      : e.event_type === 'plan'
                        ? String((payload?.steps as string[])?.join(' → ') ?? '')
                        : e.event_type === 'task_started'
                          ? String(payload?.objective ?? '')
                          : String(payload?.message ?? payload?.reason ?? '');
                return (
                  <HStack key={e.id} gap={2} vAlign="start">
                    <Badge label={meta.label} variant={meta.variant as never} />
                    <Badge label={agentNameOf(e.agent_id)} variant="neutral" />
                    <Text type="supporting" className="mono" style={{flex: 1}}>{summary || '--'}</Text>
                  </HStack>
                );
              })}
              {selectedTask.events.length === 0 && <Text type="supporting"><span className="muted">暂无事件</span></Text>}
            </VStack>

            {selectedTask.result && (
              <Card variant="default" style={{padding: 14}}>
                <Text weight="semibold" style={{marginBottom: 6}}>执行结果</Text>
                <Text type="body" className="mono" style={{whiteSpace: 'pre-wrap'}}>{selectedTask.result}</Text>
              </Card>
            )}

            {/* M3: 反馈闭环 */}
            {selectedTask.status === 'succeeded' && (
              <Card variant="default" style={{padding: 14}}>
                <VStack gap={2}>
                  <HStack gap={2} vAlign="center">
                    <Star size={15} className="muted" />
                    <Text weight="semibold">效果反馈</Text>
                    <Text type="supporting"><span className="muted">评分将驱动知识修正与检索优化</span></Text>
                  </HStack>
                  <HStack gap={1}>
                    {[1, 2, 3, 4, 5].map((v) => (
                      <Button
                        key={v}
                        label={String(v)}
                        size="sm"
                        variant={rating === v ? 'primary' : 'ghost'}
                        onClick={() => setRating(v)}
                      />
                    ))}
                  </HStack>
                  <HStack gap={2} vAlign="end">
                    <TextInput
                      label="评论 (可选)"
                      value={comment}
                      onChange={setComment}
                      placeholder="结果是否准确? 有哪些改进空间?"
                      style={{flex: 1}}
                    />
                    <Button
                      label="提交反馈"
                      variant="primary"
                      isLoading={submitFeedback.isPending}
                      isDisabled={!canEdit}
                      onClick={() => submitFeedback.mutate(selectedTask.id)}
                    />
                  </HStack>
                </VStack>
              </Card>
            )}
          </VStack>
        </Card>
      )}
    </div>
  );
}
