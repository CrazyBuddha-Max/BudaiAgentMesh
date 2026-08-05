import {Badge, type BadgeVariant} from '@astryxdesign/core/Badge';

const STATUS_META: Record<string, {label: string; variant: BadgeVariant}> = {
  active: {label: '已接入', variant: 'success'},
  pending: {label: '待校验', variant: 'warning'},
  error: {label: '连接异常', variant: 'error'},
  success: {label: '成功', variant: 'success'},
  failed: {label: '失败', variant: 'error'},
  running: {label: '运行中', variant: 'info'},
  ready: {label: '就绪', variant: 'success'},
  processing: {label: '解析中', variant: 'info'},
  succeeded: {label: '成功', variant: 'success'},
  offline: {label: '离线', variant: 'neutral'},
  paused: {label: '已暂停', variant: 'warning'},
};

export function StatusBadge({status}: {status: string}) {
  const meta = STATUS_META[status] ?? {label: status, variant: 'neutral'};
  return <Badge label={meta.label} variant={meta.variant} />;
}
