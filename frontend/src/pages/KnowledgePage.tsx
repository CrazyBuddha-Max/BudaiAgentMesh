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
import {FileInput} from '@astryxdesign/core/FileInput';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {useToast} from '@astryxdesign/core/Toast';
import type {KnowledgeDoc, RetrieveHit} from '@/api/types';
import {Upload, Search, Trash2, BookOpen, FileText} from 'lucide-react';
import {useAuthStore} from '@/store/auth';

export function KnowledgePage() {
  const toast = useToast();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = (user?.role ?? 'viewer') !== 'viewer';

  const [file, setFile] = useState<File | null>(null);
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<RetrieveHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');

  const docs = useQuery({queryKey: ['knowledge-docs'], queryFn: api.listKnowledgeDocs});

  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('请先选择文件');
      return api.uploadKnowledgeDoc(file);
    },
    onSuccess: (doc) => {
      toast({body: `「${doc.title}」已入库, 生成 ${doc.chunk_count} 个知识切块`});
      setFile(null);
      qc.invalidateQueries({queryKey: ['knowledge-docs']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '上传失败', type: 'error'}),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteKnowledgeDoc(id),
    onSuccess: () => {
      toast({body: '知识文档已删除'});
      qc.invalidateQueries({queryKey: ['knowledge-docs']});
    },
    onError: (e) => toast({body: e instanceof Error ? e.message : '删除失败', type: 'error'}),
  });

  const doSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setSearchError('');
    try {
      const result = await api.retrieve(query.trim(), 5);
      setHits(result);
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : '检索失败');
    } finally {
      setSearching(false);
    }
  };

  const columns = [
    {key: 'title', header: '知识文档', width: proportional(1.6), renderCell: (d: KnowledgeDoc) => (
      <HStack gap={2} vAlign="center">
        <FileText size={15} className="muted" />
        <div>
          <Text weight="semibold">{d.title}</Text>
          <Text type="supporting" className="mono muted">{d.file_name}</Text>
        </div>
      </HStack>
    )},
    {key: 'source_type', header: '类型', width: proportional(0.7), renderCell: (d: KnowledgeDoc) => (
      <Text className="mono">{d.source_type}</Text>
    )},
    {key: 'chunk_count', header: '切块', width: proportional(0.7), renderCell: (d: KnowledgeDoc) => (
      <Text className="mono">{d.chunk_count}</Text>
    )},
    {key: 'file_size', header: '大小', width: proportional(0.8), renderCell: (d: KnowledgeDoc) => (
      <Text className="mono">{(d.file_size / 1024).toFixed(1)} KB</Text>
    )},
    {key: 'status', header: '状态', width: proportional(0.8), renderCell: (d: KnowledgeDoc) => <StatusBadge status={d.status} />},
    {key: 'created_at', header: '入库时间', width: proportional(1), renderCell: (d: KnowledgeDoc) => (
      <Text type="supporting" className="mono">{d.created_at.slice(0, 16).replace('T', ' ')}</Text>
    )},
    {key: 'actions', header: '', width: proportional(0.5), renderCell: (d: KnowledgeDoc) => (
      <Button
        label="删除"
        size="sm"
        variant="ghost"
        icon={<Trash2 size={13} />}
        isDisabled={!canEdit}
        onClick={() => remove.mutate(d.id)}
      />
    )},
  ];

  return (
    <div className="page-stack">
      <PageHeader
        title="知识工作台"
        description="RAG 知识沉淀: 上传文档自动解析切分向量化, 语义检索直接可用"
      />

      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <BookOpen size={18} />
            <Text weight="semibold">知识入库</Text>
            <Text type="supporting"><span className="muted">支持 txt / md / html / pdf, 自动切分并向量化</span></Text>
          </HStack>
          <HStack gap={3} vAlign="end" wrap="wrap">
            <FileInput
              label="选择文档"
              accept=".txt,.md,.markdown,.html,.htm,.pdf"
              value={file}
              onChange={(f) => setFile(f as File | null)}
              isDisabled={!canEdit}
            />
            <Button
              label={upload.isPending ? '解析入库中...' : '上传入库'}
              variant="primary"
              icon={<Upload size={15} />}
              isDisabled={!canEdit || !file}
              isLoading={upload.isPending}
              onClick={() => upload.mutate()}
            />
          </HStack>
        </VStack>
      </Card>

      <Card variant="muted" style={{padding: 20}}>
        <VStack gap={3}>
          <HStack gap={2} vAlign="center">
            <Search size={18} />
            <Text weight="semibold">语义检索</Text>
            <Text type="supporting"><span className="muted">基于向量相似度, 返回最相关知识切块</span></Text>
          </HStack>
          <HStack gap={2} vAlign="end">
            <TextInput
              label="检索问题"
              value={query}
              onChange={setQuery}
              placeholder="例如: 毛利率的计算口径是什么"
              style={{flex: 1}}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void doSearch();
              }}
            />
            <Button label="检索" variant="primary" icon={<Search size={14} />} isLoading={searching} onClick={() => void doSearch()} />
          </HStack>

          {searchError && <Text style={{color: '#d64545'}}>{searchError}</Text>}

          {hits && hits.length > 0 && (
            <VStack gap={2}>
              {hits.map((h) => (
                <Card key={h.chunk_id} variant="default" style={{padding: 14}}>
                  <HStack hAlign="between" vAlign="start" gap={3}>
                    <Text type="body" style={{flex: 1}}>{h.content}</Text>
                    <div style={{minWidth: 90, textAlign: 'right'}}>
                      <Text weight="semibold" className="mono" style={{color: '#2f6db8'}}>
                        {(h.score * 100).toFixed(1)}%
                      </Text>
                      <Text type="supporting" className="muted">相似度</Text>
                    </div>
                  </HStack>
                </Card>
              ))}
            </VStack>
          )}
          {hits && hits.length === 0 && !searching && (
            <Text type="supporting"><span className="muted">未检索到相关内容, 可尝试换一种问法</span></Text>
          )}
        </VStack>
      </Card>

      <div>
        <Text weight="semibold" style={{marginBottom: 8}}>知识库文档 ({docs.data?.length ?? 0})</Text>
        {docs.isLoading ? (
          <Text type="supporting">加载中...</Text>
        ) : docs.data && docs.data.length > 0 ? (
          <Table data={docs.data as never} columns={columns as never} density="compact" dividers="rows" hasHover />
        ) : (
          <EmptyState title="知识库为空" description="上传第一份业务文档, 开始沉淀企业知识" />
        )}
      </div>
    </div>
  );
}
