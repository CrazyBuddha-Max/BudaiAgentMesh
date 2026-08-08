import {useEffect, useRef, useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api} from '@/api/client';
import {StatusBadge} from '@/components/StatusBadge';
import {Card} from '@astryxdesign/core/Card';
import {Text} from '@astryxdesign/core/Text';
import {Button} from '@astryxdesign/core/Button';
import {Badge} from '@astryxdesign/core/Badge';
import {Selector} from '@astryxdesign/core/Selector';
import {useToast} from '@astryxdesign/core/Toast';
import type {AgentEvent, AgentTask} from '@/api/types';
import {Bot, ListTree, MessageSquareText, Plus, Send, Star, User as UserIcon} from 'lucide-react';
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

/** 从任务结果提取回答正文 (去掉 "【LLM 汇总 · xx】" 标记行) */
function answerText(t: AgentTask): string {
  if (!t.result) return t.error ?? '';
  return t.result.split('\n').slice(1).join('\n').trim() || t.result;
}

export function TasksPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = (user?.role ?? 'viewer') !== 'viewer';

  const [input, setInput] = useState('');
  const [activeId, setActiveId] = useState<number | null>(null);
  const [mainAgentId, setMainAgentId] = useState('');
  const [collaborators, setCollaborators] = useState<string[]>([]);
  const [addCollab, setAddCollab] = useState('');
  const [autoCollab, setAutoCollab] = useState(false);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [showChain, setShowChain] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const agents = useQuery({queryKey: ['agents'], queryFn: api.listAgents});
  const tasks = useQuery({queryKey: ['agent-tasks'], queryFn: api.listTasks, refetchInterval: 5_000});

  const agentNameOf = (id: number) => agents.data?.find((a) => a.id === id)?.name ?? `Agent#${id}`;
  const activeTask = tasks.data?.find((t) => t.id === activeId) ?? null;
  const running = tasks.data?.find((t) => t.status === 'running');

  // 智能推荐协作 Agent (M7): 按目标关键词匹配能力, 自动选 1 个 (排除主控)
  const recommendCollaborator = (): string => {
    const list = agents.data ?? [];
    const main = Number(mainAgentId);
    const others = list.filter((a) => a.id !== main);
    if (others.length === 0) return '';
    const q = input;
    const needKnowledge = /知识|口径|说明|定义|规范|文档/.test(q);
    const needData = /数据|分析|订单|销售|金额|统计|毛利|库存|客户/.test(q);
    const score = (a: {capabilities: string[]}): number => {
      const caps = a.capabilities ?? [];
      let s = 0;
      if (needKnowledge && caps.includes('knowledge_retrieval')) s += 2;
      if (needData && caps.includes('data_access')) s += 2;
      if (caps.includes('report_draft')) s += 0.5;
      return s;
    };
    const ranked = [...others].sort((a, b) => score(b) - score(a));
    return score(ranked[0]) > 0 ? String(ranked[0].id) : '';
  };

  // 输入变化时自动推荐 (仅当用户未手动指定过)
  useEffect(() => {
    if (autoCollab || !input.trim() || !mainAgentId) return;
    const rec = recommendCollaborator();
    if (rec) setCollaborators([rec]);
  }, [input, mainAgentId, agents.data]);

  // 自动滚动到底部
  useEffect(() => {
    scrollRef.current?.scrollTo({top: scrollRef.current.scrollHeight, behavior: 'smooth'});
  }, [activeTask?.result, activeTask?.events.length, running?.id]);

  const ask = useMutation({
    mutationFn: (agentId: number) =>
      api.createTask(agentId, input, input.slice(0, 40), collaborators.map(Number).filter((id) => id !== agentId)),
    onSuccess: async (task) => {
      setInput('');
      setActiveId(task.id);
      qc.invalidateQueries({queryKey: ['agent-tasks']});
      await runTask.mutateAsync(task.id);
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '发送失败', type: 'error'}),
  });

  const runTask = useMutation({
    mutationFn: (taskId: number) => api.runTask(taskId),
    onSuccess: () => {
      toast({body: '回答完成'});
      qc.invalidateQueries({queryKey: ['agent-tasks']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '执行失败', type: 'error'}),
  });

  const submitFeedback = useMutation({
    mutationFn: (taskId: number) => api.submitFeedback(taskId, rating, comment || undefined),
    onSuccess: () => {
      toast({body: '反馈已提交'});
      setComment('');
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '提交失败', type: 'error'}),
  });

  const send = () => {
    if (!input.trim() || !mainAgentId || !canEdit) return;
    ask.mutate(Number(mainAgentId));
  };

  // 最近 50 条历史, 倒序展示 (最新在上)
  const history = [...(tasks.data ?? [])];

  return (
    <div className="page-stack" style={{height: 'calc(100vh - 120px)'}}>
      <div style={{display: 'grid', gridTemplateColumns: '280px 1fr', gap: 16, height: '100%', minHeight: 0}}>
        {/* 历史会话侧栏 */}
        <Card variant="muted" style={{padding: 12, display: 'flex', flexDirection: 'column', minHeight: 0}}>
          <VStack gap={2} style={{flex: 1, minHeight: 0, overflowY: 'auto'}}>
            <HStack gap={2} vAlign="center" hAlign="between" style={{padding: '4px 6px'}}>
              <Text weight="semibold">历史会话 ({tasks.data?.length ?? 0})</Text>
              <Button
                label="新建"
                size="sm"
                variant="ghost"
                icon={<Plus size={13} />}
                onClick={() => setActiveId(null)}
              />
            </HStack>
            {history.length === 0 && (
              <Text type="supporting" style={{padding: 8}}><span className="muted">还没有会话, 开始提问吧</span></Text>
            )}
            {history.map((t: AgentTask) => (
              <button
                key={t.id}
                onClick={() => setActiveId(t.id)}
                style={{
                  display: 'flex', flexDirection: 'column', gap: 4, textAlign: 'left', cursor: 'pointer',
                  padding: '8px 10px', borderRadius: 8, border: 'none', width: '100%',
                  background: activeId === t.id ? 'rgba(43, 109, 232, 0.1)' : 'transparent',
                }}
              >
                <HStack gap={1} vAlign="center" hAlign="between">
                  <Text weight="semibold" style={{fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 150}}>
                    {t.objective}
                  </Text>
                  <StatusBadge status={t.status} />
                </HStack>
                <Text type="supporting" style={{fontSize: 11}}><span className="muted">
                  #{t.id} · {t.created_at.slice(5, 16).replace('T', ' ')}
                </span></Text>
              </button>
            ))}
          </VStack>
        </Card>

        {/* 对话窗口 */}
        <Card variant="muted" style={{padding: 0, display: 'flex', flexDirection: 'column', minHeight: 0}}>
          {/* 顶部: 紧凑工具栏 */}
          <div style={{padding: '10px 14px', borderBottom: '1px solid rgba(0,0,0,0.06)', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap'}}>
            <Selector
              label="主控 Agent"
              size="sm"
              value={mainAgentId}
              onChange={(v) => setMainAgentId(v)}
              options={(agents.data ?? []).map((a) => ({label: a.name, value: String(a.id)}))}
            />
            <div style={{display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap'}}>
              <Text type="supporting" style={{fontSize: 12}}><span className="muted">协作:</span></Text>
              {collaborators.map((id) => {
                const a = agents.data?.find((x) => String(x.id) === id);
                return (
                  <span key={id} style={{display: 'inline-flex', alignItems: 'center', gap: 4}}>
                    <Badge label={a?.name ?? `#${id}`} variant="blue" />
                    <button
                      onClick={() => setCollaborators(collaborators.filter((c) => c !== id))}
                      style={{border: 'none', background: 'none', cursor: 'pointer', color: '#999', fontSize: 12, padding: 0}}
                      title="移除"
                    >×</button>
                  </span>
                );
              })}
              {!autoCollab && collaborators.length > 0 && <Badge label="✨智能" variant="success" />}
              <Selector
                label=""
                size="sm"
                placeholder="+ 添加协作"
                value={addCollab}
                onChange={(v) => {
                  setAutoCollab(true);
                  if (v && !collaborators.includes(v)) setCollaborators([...collaborators, v]);
                  setAddCollab('');
                }}
                options={(agents.data ?? [])
                  .filter((a) => String(a.id) !== mainAgentId && !collaborators.includes(String(a.id)))
                  .map((a) => ({label: a.name, value: String(a.id)}))}
              />
              {autoCollab && (
                <Button
                  label="智能"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setAutoCollab(false);
                    const rec = recommendCollaborator();
                    setCollaborators(rec ? [rec] : []);
                  }}
                />
              )}
            </div>
            <div style={{flex: 1}} />
            {activeTask && (
              <Button
                label={showChain ? '收起链路' : '执行链路'}
                size="sm"
                variant="ghost"
                icon={<ListTree size={13} />}
                onClick={() => setShowChain(!showChain)}
              />
            )}
          </div>

          {/* 消息区 */}
          <div ref={scrollRef} style={{flex: 1, minHeight: 0, overflowY: 'auto', padding: '20px 24px'}}>
            {!activeTask ? (
              // 空态: 欢迎提示
              <div style={{height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                <VStack gap={2} style={{textAlign: 'center', maxWidth: 420}}>
                  <MessageSquareText size={36} className="muted" style={{margin: '0 auto'}} />
                  <Text weight="semibold">向系统提问</Text>
                  <Text type="supporting"><span className="muted">
                    多 Agent 团队将协作回答: 检索知识口径 → 定位数据表 → 采样分析 → 大模型汇总结论
                  </span></Text>
                </VStack>
              </div>
            ) : (
              <VStack gap={3}>
                {/* 用户问题 */}
                <Bubble side="user">
                  <HStack gap={2} vAlign="start">
                    <UserIcon size={15} className="muted" style={{marginTop: 2, flexShrink: 0}} />
                    <div style={{flex: 1}}>
                      <Text weight="semibold" style={{fontSize: 13, marginBottom: 2}}>你 · {agentNameOf(activeTask.agent_id)}</Text>
                      <Text>{activeTask.objective}</Text>
                    </div>
                  </HStack>
                </Bubble>

                {/* 执行中 loading */}
                {activeTask.status === 'running' && (
                  <Bubble side="ai">
                    <HStack gap={2} vAlign="center">
                      <Bot size={15} className="muted" />
                      <Text type="supporting"><span className="muted">团队执行中: 检索口径 → 定位数据 → 采样分析 → 汇总…</span></Text>
                    </HStack>
                  </Bubble>
                )}

                {/* AI 回答 */}
                {(activeTask.status === 'succeeded' || activeTask.status === 'failed') && (
                  <Bubble side="ai">
                    <HStack gap={2} vAlign="start">
                      <Bot size={15} style={{marginTop: 2, flexShrink: 0}} />
                      <div style={{flex: 1, minWidth: 0}}>
                        <Text weight="semibold" style={{fontSize: 13, marginBottom: 4}}>
                          BudaiAgentMesh · 多 Agent 团队
                          {activeTask.result?.startsWith('【LLM 汇总') && (
                            <span className="muted" style={{fontWeight: 400}}> · {activeTask.result.split('\n')[0].replace('【LLM 汇总 · ', '').replace('】', '')}</span>
                          )}
                        </Text>
                        <Text className="mono" style={{whiteSpace: 'pre-wrap'}}>{answerText(activeTask)}</Text>
                        {activeTask.status === 'failed' && (
                          <Button
                            label="重新执行"
                            size="sm"
                            variant="secondary"
                            style={{marginTop: 8}}
                            icon={<Bot size={13} />}
                            isDisabled={!!running || !canEdit}
                            isLoading={runTask.isPending && runTask.variables === activeTask.id}
                            onClick={() => runTask.mutate(activeTask.id)}
                          />
                        )}
                      </div>
                    </HStack>
                  </Bubble>
                )}

                {/* 执行链路 (可展开) */}
                {showChain && activeTask.events.length > 0 && (
                  <Card variant="default" style={{padding: 12}}>
                    <VStack gap={1}>
                      <Text weight="semibold" style={{marginBottom: 4}}>执行链路</Text>
                      {activeTask.events.map((e: AgentEvent) => {
                        const meta = EVENT_LABEL[e.event_type] ?? {label: e.event_type, variant: 'neutral'};
                        const payload = e.payload as Record<string, unknown> | null;
                        const summary =
                          e.event_type === 'llm.plan'
                            ? `模型 ${String(payload?.provider ?? '')} · 关键词 "${String(payload?.keyword ?? '')}" · 步骤: ${String((payload?.steps as string[])?.join(' → ') ?? '')}`
                            : e.event_type === 'llm.summary'
                              ? `模型 ${String(payload?.provider ?? '')}${payload?.fallback ? ' (降级模板)' : ''}`
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
                    </VStack>
                  </Card>
                )}

                {/* 反馈 */}
                {activeTask.status === 'succeeded' && (
                  <Card variant="default" style={{padding: 12}}>
                    <VStack gap={2}>
                      <HStack gap={2} vAlign="center">
                        <Star size={14} className="muted" />
                        <Text weight="semibold" style={{fontSize: 13}}>效果反馈</Text>
                        <Text type="supporting"><span className="muted">评分驱动知识修正与检索优化</span></Text>
                      </HStack>
                      <HStack gap={1}>
                        {[1, 2, 3, 4, 5].map((v) => (
                          <Button
                            key={v} label={String(v)} size="sm"
                            variant={rating === v ? 'primary' : 'ghost'}
                            onClick={() => setRating(v)}
                          />
                        ))}
                      </HStack>
                      <HStack gap={2} vAlign="center">
                        <input
                          value={comment}
                          onChange={(e) => setComment(e.target.value)}
                          placeholder="评论 (可选)"
                          style={{flex: 1, padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.12)'}}
                        />
                        <Button
                          label="提交"
                          size="sm"
                          variant="primary"
                          isLoading={submitFeedback.isPending}
                          isDisabled={!canEdit}
                          onClick={() => submitFeedback.mutate(activeTask.id)}
                        />
                      </HStack>
                    </VStack>
                  </Card>
                )}
              </VStack>
            )}
          </div>

          {/* 输入区 */}
          <div style={{padding: '12px 16px', borderTop: '1px solid rgba(0,0,0,0.06)'}}>
            <div style={{display: 'flex', gap: 8, alignItems: 'flex-end'}}>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="输入问题, 回车发送 (Shift+Enter 换行)…"
                rows={2}
                style={{
                  flex: 1, padding: '10px 14px', borderRadius: 10, resize: 'none',
                  border: '1px solid rgba(0,0,0,0.12)', fontFamily: 'inherit', fontSize: 14,
                }}
              />
              <Button
                label={running ? '执行中…' : '发送'}
                variant="primary"
                icon={<Send size={14} />}
                isDisabled={!canEdit || !input.trim() || !mainAgentId || !!running}
                isLoading={!!running}
                onClick={send}
              />
            </div>
            <Text type="supporting" style={{marginTop: 4, fontSize: 11}}>
              <span className="muted">主控 Agent 负责规划与汇总 · {running ? `任务 ${running.id} 执行中, 完成后自动刷新` : '真实大模型驱动'}</span>
            </Text>
          </div>
        </Card>
      </div>
    </div>
  );
}

function VStack(props: {children: React.ReactNode; gap?: number; style?: React.CSSProperties; className?: string}) {
  return (
    <div className={props.className} style={{display: 'flex', flexDirection: 'column', gap: (props.gap ?? 2) * 4, ...props.style}}>
      {props.children}
    </div>
  );
}

function HStack(props: {children: React.ReactNode; gap?: number; vAlign?: string; hAlign?: string; style?: React.CSSProperties; className?: string}) {
  return (
    <div className={props.className} style={{
      display: 'flex', gap: (props.gap ?? 2) * 4, alignItems: props.vAlign === 'center' ? 'center' : 'flex-start',
      justifyContent: props.hAlign === 'between' ? 'space-between' : 'flex-start', ...props.style,
    }}>
      {props.children}
    </div>
  );
}

function Bubble(props: {side: 'user' | 'ai'; children: React.ReactNode}) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: props.side === 'user' ? 'flex-end' : 'flex-start',
    }}>
      <div style={{
        maxWidth: '85%',
        padding: '10px 14px',
        borderRadius: 12,
        background: props.side === 'user' ? 'rgba(43, 109, 232, 0.08)' : 'rgba(255,255,255,0.9)',
        border: props.side === 'user' ? 'none' : '1px solid rgba(0,0,0,0.08)',
      }}>
        {props.children}
      </div>
    </div>
  );
}
