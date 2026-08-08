import {useState} from 'react';
import {useQuery, useMutation, useQueryClient} from '@tanstack/react-query';
import {api} from '@/api/client';
import {PageHeader} from '@/components/PageHeader';
import {Card} from '@astryxdesign/core/Card';
import {Text} from '@astryxdesign/core/Text';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Selector} from '@astryxdesign/core/Selector';
import {Button} from '@astryxdesign/core/Button';
import {Badge} from '@astryxdesign/core/Badge';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {useToast} from '@astryxdesign/core/Toast';
import type {LLMProvider} from '@/api/types';
import {Bot, KeyRound, Plus, PlugZap, Star, Trash2} from 'lucide-react';
import {useAuthStore} from '@/store/auth';

const PROVIDER_META: Record<string, {label: string; base: string; hint: string}> = {
  openai: {label: 'OpenAI', base: 'https://api.openai.com/v1', hint: 'gpt-4o-mini / text-embedding-3-small'},
  deepseek: {label: 'DeepSeek', base: 'https://api.deepseek.com/v1', hint: 'deepseek-chat'},
  qwen: {label: '通义千问', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', hint: 'qwen-plus'},
  ollama: {label: 'Ollama (本地)', base: 'http://localhost:11434/v1', hint: 'llama3.2 / nomic-embed-text'},
  custom: {label: '自定义 (OpenAI 兼容)', base: '', hint: '任意 OpenAI 兼容端点'},
};

interface Form {
  name: string;
  provider_type: string;
  api_base: string;
  api_key: string;
  model: string;
  embedding_model: string;
  temperature: string;
  max_tokens: string;
  is_default: boolean;
}

const EMPTY: Form = {
  name: '', provider_type: 'openai', api_base: 'https://api.openai.com/v1', api_key: '',
  model: '', embedding_model: '', temperature: '0.2', max_tokens: '2048', is_default: false,
};

export function ModelsPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isAdmin = (user?.role ?? '') === 'admin';

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<Form>(EMPTY);
  const [editingId, setEditingId] = useState<number | null>(null);

  const providers = useQuery({queryKey: ['llm-providers'], queryFn: api.llmProviders});
  const agents = useQuery({queryKey: ['agents'], queryFn: () => api.agents()});

  const set = (k: keyof Form) => (v: string | boolean) => setForm((f) => ({...f, [k]: v}));

  const selectType = (t: string) => {
    const meta = PROVIDER_META[t];
    setForm((f) => ({
      ...f,
      provider_type: t,
      api_base: meta?.base ?? '',
      model: '',
      embedding_model: t === 'ollama' ? 'nomic-embed-text' : '',
    }));
  };

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name.trim(),
        provider_type: form.provider_type,
        api_base: form.api_base.trim(),
        api_key: form.api_key || undefined,
        model: form.model.trim(),
        embedding_model: form.embedding_model.trim() || null,
        temperature: Number(form.temperature) || 0.2,
        max_tokens: Number(form.max_tokens) || 2048,
        is_default: form.is_default,
      };
      return editingId ? api.updateLlmProvider(editingId, payload) : api.createLlmProvider(payload);
    },
    onSuccess: (p) => {
      toast({body: editingId ? `已更新「${p.name}」` : `已接入「${p.name}」`});
      setShowForm(false);
      setForm(EMPTY);
      setEditingId(null);
      qc.invalidateQueries({queryKey: ['llm-providers']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '保存失败', type: 'error'}),
  });

  const testConn = useMutation({
    mutationFn: (id: number) => api.testLlmProvider(id),
    onSuccess: (d) => toast({body: `${d.name}: ${d.message}`}),
    onError: (e) => toast({body: e instanceof Error ? e.message : '测试失败', type: 'error'}),
  });

  const setDefault = useMutation({
    mutationFn: (id: number) => api.setLlmDefault(id),
    onSuccess: () => {
      toast({body: '已设为默认提供方'});
      qc.invalidateQueries({queryKey: ['llm-providers']});
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteLlmProvider(id),
    onSuccess: () => {
      toast({body: '提供方已删除'});
      qc.invalidateQueries({queryKey: ['llm-providers']});
    },
  });

  const startEdit = (p: LLMProvider) => {
    setEditingId(p.id);
    setForm({
      name: p.name, provider_type: p.provider_type, api_base: p.api_base, api_key: '',
      model: p.model, embedding_model: p.embedding_model ?? '', temperature: String(p.temperature),
      max_tokens: String(p.max_tokens), is_default: p.is_default,
    });
    setShowForm(true);
  };

  const providerName = (id: number | null | undefined) =>
    providers.data?.find((p) => p.id === id)?.name ?? '默认/未绑定';

  return (
    <div className="page-stack">
      <PageHeader
        title="大模型接入"
        description="管理不同智能体对接的大模型提供方: OpenAI / DeepSeek / 通义 / Ollama 等 OpenAI 兼容协议"
        actions={
          isAdmin ? (
            <Button
              label={showForm ? '收起表单' : '接入模型'}
              variant={showForm ? 'ghost' : 'primary'}
              icon={<Plus size={16} />}
              onClick={() => {
                setShowForm((v) => !v);
                setEditingId(null);
                if (!showForm) setForm(EMPTY);
              }}
            />
          ) : undefined
        }
      />

      {showForm && isAdmin && (
        <Card variant="muted" style={{padding: 20}}>
          <VStack gap={4}>
            <HStack gap={2} vAlign="center">
              <Bot size={18} />
              <Text weight="semibold">{editingId ? '编辑模型提供方' : '接入大模型'}</Text>
            </HStack>

            <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16}}>
              <TextInput label="提供方名称" value={form.name} onChange={set('name')} isRequired placeholder="如 生产 DeepSeek" />
              <div>
                <Text type="supporting" style={{marginBottom: 4}}><span className="muted">提供方类型</span></Text>
                <Selector
                  label=""
                  value={form.provider_type}
                  onChange={(v) => selectType(v)}
                  options={Object.entries(PROVIDER_META).map(([v, m]) => ({label: m.label, value: v}))}
                />
              </div>
              <TextInput label="API 地址" value={form.api_base} onChange={set('api_base')} isRequired description="OpenAI 兼容 base URL" />
              <TextInput
                label="API Key"
                type="password"
                value={form.api_key}
                onChange={set('api_key')}
                description={editingId ? '留空则不修改' : '加密存储, 绝不回显'}
              />
              <TextInput label="对话模型" value={form.model} onChange={set('model')} isRequired placeholder={PROVIDER_META[form.provider_type]?.hint} />
              <TextInput label="Embedding 模型" value={form.embedding_model} onChange={set('embedding_model')} description="可空, 缺省用对话模型" />
              <TextInput label="温度" value={form.temperature} onChange={set('temperature')} />
              <TextInput label="最大 Tokens" value={form.max_tokens} onChange={set('max_tokens')} />
              <div style={{display: 'flex', alignItems: 'center', gap: 8, paddingTop: 22}}>
                <input
                  id="is-default"
                  type="checkbox"
                  checked={form.is_default}
                  onChange={(e) => set('is_default')(e.target.checked)}
                />
                <label htmlFor="is-default" style={{cursor: 'pointer'}}>设为默认 (未绑定 Agent / 向量化使用)</label>
              </div>
            </div>

            <HStack gap={2} hAlign="end">
              <Button label="取消" variant="ghost" onClick={() => { setShowForm(false); setEditingId(null); }} />
              <Button
                label={save.isPending ? '保存中...' : '保存'}
                variant="primary"
                isLoading={save.isPending}
                isDisabled={!form.name || !form.api_base || !form.model}
                onClick={() => save.mutate()}
              />
            </HStack>
          </VStack>
        </Card>
      )}

      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>已接入提供方 ({providers.data?.length ?? 0})</Text>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12}}>
          {(providers.data ?? []).map((p) => (
            <Card key={p.id} variant="default" style={{padding: 14}}>
              <VStack gap={2}>
                <HStack gap={2} vAlign="center" hAlign="between">
                  <HStack gap={2} vAlign="center">
                    <Bot size={16} />
                    <Text weight="semibold">{p.name}</Text>
                    {p.is_default && <Badge label="默认" variant="success" />}
                  </HStack>
                  <Badge label={PROVIDER_META[p.provider_type]?.label ?? p.provider_type} variant={p.enabled ? 'info' : 'neutral'} />
                </HStack>
                <Text className="mono muted" type="supporting">{p.api_base}</Text>
                <HStack gap={1} wrap="wrap">
                  <Badge label={`对话: ${p.model}`} variant="neutral" />
                  {p.embedding_model && <Badge label={`向量: ${p.embedding_model}`} variant="neutral" />}
                </HStack>
                <Text type="supporting" className="muted">
                  温度 {p.temperature} · 上限 {p.max_tokens} tok
                </Text>
                <HStack gap={1}>
                  {isAdmin && (
                    <>
                      <Button label="测试" size="sm" variant="ghost" icon={<PlugZap size={13} />} isLoading={testConn.isPending && testConn.variables === p.id} onClick={() => testConn.mutate(p.id)} />
                      {!p.is_default && (
                        <Button label="设默认" size="sm" variant="ghost" icon={<Star size={13} />} onClick={() => setDefault.mutate(p.id)} />
                      )}
                      <Button label="编辑" size="sm" variant="ghost" onClick={() => startEdit(p)} />
                      <Button label="" size="sm" variant="ghost" icon={<Trash2 size={13} />} onClick={() => remove.mutate(p.id)} />
                    </>
                  )}
                </HStack>
              </VStack>
            </Card>
          ))}
          {(providers.data ?? []).length === 0 && (
            <Card variant="default" style={{padding: 16}}>
              <Text type="supporting" className="muted">
                尚未接入任何模型提供方。点击右上角「接入模型」配置后，Agent 任务将真实调用大模型规划与汇总，知识入库将真实向量化。
              </Text>
            </Card>
          )}
        </div>
      </div>

      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <KeyRound size={17} />
            <Text weight="semibold">Agent ↔ 模型绑定</Text>
            <Text type="supporting"><span className="muted">每个智能体可绑定独立提供方; 未绑定使用默认</span></Text>
          </HStack>
          {(agents.data ?? []).length > 0 ? (
            <VStack gap={2}>
              {(agents.data ?? []).map((a) => (
                <HStack key={a.id} gap={2} vAlign="center">
                  <Badge label={a.name} variant="blue" />
                  <Text className="muted">→</Text>
                  <Badge label={providerName(a.llm_provider_id)} variant={a.llm_provider_id ? 'success' : 'neutral'} />
                </HStack>
              ))}
            </VStack>
          ) : (
            <Text type="supporting"><span className="muted">暂无 Agent, 到 Agent 协同页创建后可在此查看绑定</span></Text>
          )}
        </VStack>
      </Card>
    </div>
  );
}
