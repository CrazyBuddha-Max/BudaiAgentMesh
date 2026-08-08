import {useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api} from '@/api/client';
import {PageHeader} from '@/components/PageHeader';
import {StatusBadge} from '@/components/StatusBadge';
import {Card} from '@astryxdesign/core/Card';
import {Text} from '@astryxdesign/core/Text';
import {TextInput} from '@astryxdesign/core/TextInput';
import {TextArea} from '@astryxdesign/core/TextArea';
import {Button} from '@astryxdesign/core/Button';
import {Badge} from '@astryxdesign/core/Badge';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {Selector} from '@astryxdesign/core/Selector';
import {CheckboxList, CheckboxListItem} from '@astryxdesign/core/CheckboxList';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {useToast} from '@astryxdesign/core/Toast';
import type {AgentEvent, AgentTask} from '@/api/types';
import {ListTree, MessageSquareText, Sparkles, Star, Zap} from 'lucide-react';
import {useAuthStore} from '@/store/auth';

const EVENT_LABEL: Record<string, {label: string; variant: string}> = {
  task_started: {label: '任务启动', variant: 'info'},
  plan: {label: '制定计划', variant: 'neutral'},
  'llm.plan': {label: 'LLM 规划', variant: 'purple'},
  tool_call: {label: '调用工具', variant: 'blue'},
  tool_result: {label: '工具结果', variant: 'green'},
  retrieval: {label: '知识检索', variant: 'cyan'},
  'llm.summary': {label: 'LLM 汇总', variant: 'purple'},
  completion: {label: '任务完成', variant: 'success'},
  error: {label: '执行异常', variant: 'error'},
};

export function TasksPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = (user?.role ?? 'viewer') !== 'viewer';

  const [objective, setObjective] = useState('');
  const [mainAgentId, setMainAgentId] = useState('');
  const [collaborators, setCollaborators] = useState<string[]>([]);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [expanded, setExpanded] = useState<number | null>(null);

  const agents = useQuery({queryKey: ['agents'], queryFn: api.listAgents});
  const tasks = useQuery({queryKey: ['agent-tasks'], queryFn: api.listTasks, refetchInterval: 8_000});

  const agentNameOf = (id: number) => agents.data?.find((a) => a.id === id)?.name ?? `Agent#${id}`;

  const createTask = useMutation({
    mutationFn: (agentId: number) =>
      api.createTask(agentId, objective, objective.slice(0, 40), collaborators.map(Number).filter((id) => id !== agentId)),
    onSuccess: async (task) => {
      toast({body: `任务 #${task.id} 已创建, 团队集结, 开始执行`});
      setObjective('');
      setExpanded(task.id);
      qc.invalidateQueries({queryKey: ['agent-tasks']});
      await runTask.mutateAsync(task.id);
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '任务创建失败', type: 'error'}),
  });

  const runTask = useMutation({
    mutationFn: (taskId: number) => api.runTask(taskId),
    onSuccess: () => {
      toast({body: '任务执行完成'});
      qc.invalidateQueries({queryKey: ['agent-tasks']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '执行失败', type: 'error'}),
  });

  const submitFeedback = useMutation({
    mutationFn: (taskId: number) => api.submitFeedback(taskId, rating, comment || undefined),
    onSuccess: () => {
      toast({body: '反馈已提交, 将驱动系统迭代'});
      setComment('');
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '反馈提交失败', type: 'error'}),
  });

  const recentTasks = (tasks.data ?? []).slice(0, 5);

  return (
    <div className="page-stack">
      <PageHeader
        title="问答工作台"
        description="向系统提问, 多 Agent 协作回答: 检索口径 → 定位数据 → 采样分析 → 主控汇总 (真实大模型驱动)"
      />

      {/* 主输入区 */}
      <Card variant="muted" style={{padding: 24}}>
        <VStack gap={4}>
          <HStack gap={2} vAlign="center">
            <MessageSquareText size={18} />
            <Text weight="semibold">发起一个问题 / 分析任务</Text>
            <Text type="supporting"><span className="muted">主控 Agent 负责规划与汇总</span></Text>
          </HStack>
          <TextArea
            label="任务目标"
            value={objective}
            onChange={setObjective}
            rows={3}
            placeholder="例如: 分析订单数据, 参考毛利率口径说明, 给出按区域的结论"
          />
          <div style={{display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12}}>
            <Selector
              label="主控 Agent"
              value={mainAgentId}
              onChange={(v) => setMainAgentId(v)}
              options={(agents.data ?? []).map((a) => ({label: `${a.name}`, value: String(a.id)}))}
              description="负责规划与汇总"
            />
            <CheckboxList
              label="协作 Agent (可选)"
              value={collaborators}
              onChange={setCollaborators}
              description="按能力分工: 检索员 / 分析员"
            >
              {(agents.data ?? []).map((a) => (
                <CheckboxListItem key={a.id} label={`${a.name} (${(a.capabilities ?? []).join('/') || '通用'})`} value={String(a.id)} />
              ))}
            </CheckboxList>
          </div>
          <HStack hAlign="end">
            <Button
              label="创建并执行"
              variant="primary"
              icon={<Zap size={15} />}
              isDisabled={!canEdit || !objective.trim() || !mainAgentId}
              isLoading={createTask.isPending || runTask.isPending}
              onClick={() => createTask.mutate(Number(mainAgentId))}
            />
          </HStack>
        </VStack>
      </Card>

      {/* 最近任务 */}
      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>最近任务 ({tasks.data?.length ?? 0})</Text>
        {recentTasks.length === 0 ? (
          <EmptyState title="还没有任务" description="在上方输入目标, 让多 Agent 团队为你工作" />
        ) : (
          <VStack gap={2}>
            {recentTasks.map((t: AgentTask) => (
              <Card key={t.id} variant="default" style={{padding: 14}}>
                <VStack gap={2}>
                  <HStack gap={2} vAlign="center">
                    <Badge label={`#${t.id}`} variant="neutral" />
                    <Text weight="semibold" style={{flex: 1}}>{t.objective}</Text>
                    <StatusBadge status={t.status} />
                    <Button
                      label={expanded === t.id ? '收起' : '查看链路'}
                      size="sm"
                      variant="ghost"
                      icon={<ListTree size={13} />}
                      onClick={() => setExpanded(expanded === t.id ? null : t.id)}
                    />
                  </HStack>
                  {t.result && (
                    <Card variant="muted" style={{padding: 10}}>
                      <Text type="body" className="mono" style={{whiteSpace: 'pre-wrap', fontSize: 13}}>
                        {t.result.split('\n').slice(1).join('\n').trim().slice(0, 300)}
                        {t.result.split('\n').length > 1 && t.result.length > 300 ? '...' : ''}
                      </Text>
                    </Card>
                  )}
                  {expanded === t.id && (
                    <TaskDetail
                      task={t}
                      agentNameOf={agentNameOf}
                      rating={rating}
                      setRating={setRating}
                      comment={comment}
                      setComment={setComment}
                      submitFeedback={submitFeedback}
                      canEdit={canEdit}
                    />
                  )}
                </VStack>
              </Card>
            ))}
          </VStack>
        )}
      </div>
    </div>
  );
}

function TaskDetail(props: {
  task: AgentTask;
  agentNameOf: (id: number) => string;
  rating: number;
  setRating: (v: number) => void;
  comment: string;
  setComment: (v: string) => void;
  submitFeedback: {mutate: (taskId: number) => void; isPending: boolean};
  canEdit: boolean;
}) {
  const {task, agentNameOf, rating, setRating, comment, setComment, submitFeedback, canEdit} = props;

  return (
    <VStack gap={3}>
      <VStack gap={1}>
        <Text weight="semibold" style={{marginTop: 4}}>执行链路</Text>
        {task.events.map((e: AgentEvent) => {
          const meta = EVENT_LABEL[e.event_type] ?? {label: e.event_type, variant: 'neutral'};
          const payload = e.payload as Record<string, unknown> | null;
          const summary =
            e.event_type === 'llm.plan'
              ? `模型 ${String(payload?.provider ?? '')} · 步骤: ${String((payload?.steps as string[])?.join(' → ') ?? '')}${payload?.fallback ? ' (降级模板)' : ''}`
              : e.event_type === 'llm.summary'
                ? `模型 ${String(payload?.provider ?? '')} · 生成最终结论${payload?.fallback ? ' (降级模板)' : ''}`
                : e.event_type === 'tool_call'
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
        {task.events.length === 0 && <Text type="supporting"><span className="muted">暂无事件</span></Text>}
      </VStack>

      {task.result && (
        <Card variant="default" style={{padding: 14}}>
          <HStack gap={2} vAlign="center" style={{marginBottom: 6}}>
            <Sparkles size={14} className="muted" />
            <Text weight="semibold">回答结果</Text>
          </HStack>
          <Text type="body" className="mono" style={{whiteSpace: 'pre-wrap'}}>{task.result}</Text>
        </Card>
      )}

      {task.status === 'succeeded' && (
        <Card variant="default" style={{padding: 14}}>
          <VStack gap={2}>
            <HStack gap={2} vAlign="center">
              <Star size={15} className="muted" />
              <Text weight="semibold">效果反馈</Text>
              <Text type="supporting"><span className="muted">评分驱动知识修正与检索优化</span></Text>
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
                onClick={() => submitFeedback.mutate(task.id)}
              />
            </HStack>
          </VStack>
        </Card>
      )}

      {task.error && (
        <Text type="supporting" style={{color: '#c0392b'}}>
          <span className="mono">错误: {task.error}</span>
        </Text>
      )}
    </VStack>
  );
}
