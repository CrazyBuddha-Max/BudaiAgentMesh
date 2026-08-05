import {PageHeader} from '@/components/PageHeader';
import {Table, proportional} from '@astryxdesign/core/Table';
import {Card} from '@astryxdesign/core/Card';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Badge} from '@astryxdesign/core/Badge';
import {ShieldCheck, ScanSearch} from 'lucide-react';

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
  {name: '细粒度权限 (行/列/单元格)', desc: '基于血缘传导的上下文感知授权', stage: '规划中 (M3)'},
  {name: '动态脱敏', desc: 'PII 识别 + 掩码/泛化/令牌化', stage: '规划中 (M3)'},
  {name: '审计日志', desc: '全链路操作审计, 追加式存储不可篡改', stage: '规划中 (M3)'},
  {name: '数据血缘', desc: '源表 → 加工 → 知识 → Agent 输出全链路追溯', stage: '规划中 (M3)'},
  {name: '生命周期治理', desc: '保留期限 / 归档 / 销毁, 合规 (PIPL/GDPR)', stage: '规划中 (M4)'},
];

export function SecurityPage() {
  const cell = (ok: boolean) => (
    <span className={`matrix-cell ${ok ? 'matrix-yes' : 'matrix-no'}`}>{ok ? '有' : '无'}</span>
  );

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
            <Text weight="semibold">RBAC 权限矩阵 (M1 已启用)</Text>
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
    </div>
  );
}
