import {useEffect, useRef} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from '@/api/client';
import {PageHeader} from '@/components/PageHeader';
import {StatCard} from '@/components/StatCard';
import {Card} from '@astryxdesign/core/Card';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Badge} from '@astryxdesign/core/Badge';
import * as echarts from 'echarts';
import {Activity, Timer, Gauge, AlertTriangle, Star, ThumbsUp} from 'lucide-react';
import {useThemeStore, effectiveTheme} from '@/store/theme';

const WINDOW = 60; // 自动刷新间隔 (秒)

export function ObservabilityPage() {
  const themeMode = useThemeStore((s) => s.mode);
  const metrics = useQuery({
    queryKey: ['metrics'],
    queryFn: api.metrics,
    refetchInterval: WINDOW * 1000,
  });

  // M3: 反馈闭环统计
  const feedback = useQuery({
    queryKey: ['feedback-stats'],
    queryFn: api.feedbackStats,
    refetchInterval: WINDOW * 1000,
  });

  const chartRef = useRef<HTMLDivElement>(null);
  const dist = metrics.data?.status_distribution ?? {};
  const entries = Object.entries(dist).sort((a, b) => Number(a[0]) - Number(b[0]));
  const maxCount = Math.max(1, ...entries.map(([, v]) => v));

  useEffect(() => {
    if (!chartRef.current) return;
    // 图表颜色随主题明暗自适应 (兼容手动切换的亮/暗主题)
    const dark = effectiveTheme(themeMode) === 'dark';
    const axis = dark ? 'rgba(255,255,255,0.55)' : 'rgba(0,0,0,0.5)';
    const line = dark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)';
    const grid = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
    const chart = echarts.init(chartRef.current);
    chart.setOption({
      grid: {left: 44, right: 16, top: 24, bottom: 28},
      tooltip: {trigger: 'axis'},
      xAxis: {
        type: 'category',
        data: ['1m', '2m', '3m', '4m', '5m'],
        axisLabel: {fontSize: 11, color: axis},
        axisLine: {lineStyle: {color: line}},
      },
      yAxis: {
        type: 'value',
        splitLine: {lineStyle: {color: grid}},
        axisLabel: {fontSize: 11, color: axis},
      },
      series: [
        {
          name: '请求数 (近5分钟)',
          type: 'bar',
          data: [0, 0, 0, 0, metrics.data?.requests ?? 0],
          barWidth: '46%',
          itemStyle: {color: '#2f6db8', borderRadius: [4, 4, 0, 0]},
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      chart.dispose();
    };
  }, [metrics.data, themeMode]);

  return (
    <div className="page-stack">
      <PageHeader
        title="运行观测"
        description={`近 ${metrics.data?.window_seconds ?? 300} 秒运行指标, 每 ${WINDOW} 秒自动刷新`}
      />

      <div style={{display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16}}>
        <StatCard label="请求数" value={metrics.data?.requests ?? '--'} hint="窗口内总请求" icon={<Activity size={20} />} />
        <StatCard label="平均时延" value={metrics.data ? `${metrics.data.avg_latency_ms.toFixed(1)} ms` : '--'} hint="含观测请求" icon={<Timer size={20} />} />
        <StatCard label="P95 时延" value={metrics.data ? `${metrics.data.p95_latency_ms.toFixed(1)} ms` : '--'} hint="长尾体验" icon={<Gauge size={20} />} />
        <StatCard label="错误率" value={metrics.data ? `${metrics.data.error_rate}%` : '--'} hint="5xx 占比" icon={<AlertTriangle size={20} />} />
      </div>

      {/* M3: 反馈闭环 */}
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16}}>
        <StatCard label="反馈总数" value={feedback.data?.total ?? '--'} hint="Agent 任务评价" icon={<Star size={20} />} />
        <StatCard label="平均评分" value={feedback.data ? `${feedback.data.avg_rating.toFixed(1)} / 5` : '--'} hint="满意度基线" icon={<ThumbsUp size={20} />} />
        <div style={{gridColumn: 'span 2'}}>
          <Card variant="muted" style={{padding: 16, height: '100%'}}>
            <VStack gap={2}>
              <Text weight="semibold">评分分布 (驱动迭代闭环)</Text>
              {[5, 4, 3, 2, 1].map((v) => {
                const count = feedback.data?.by_rating[String(v)] ?? 0;
                const total = feedback.data?.total ?? 0;
                const pct = total ? (count / total) * 100 : 0;
                return (
                  <HStack key={v} gap={2} vAlign="center">
                    <Text type="supporting" className="mono" style={{width: 18}}>{v}★</Text>
                    <div className="bar-track" style={{flex: 1}}>
                      <div className="bar-fill q-good" style={{width: `${pct}%`}} />
                    </div>
                    <Text type="supporting" className="mono muted" style={{width: 36, textAlign: 'right'}}>{count}</Text>
                  </HStack>
                );
              })}
            </VStack>
          </Card>
        </div>
      </div>

      <div style={{display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16}}>
        <Card variant="muted" style={{padding: 16}}>
          <Text weight="semibold" style={{marginBottom: 8}}>请求趋势</Text>
          <div ref={chartRef} style={{height: 240}} />
        </Card>

        <Card variant="muted" style={{padding: 16}}>
          <VStack gap={3}>
            <Text weight="semibold">状态码分布</Text>
            {entries.length === 0 && <Text type="supporting"><span className="muted">暂无样本</span></Text>}
            {entries.map(([code, count]) => (
              <div key={code}>
                <HStack hAlign="between" style={{marginBottom: 4}}>
                  <Badge label={`HTTP ${code}`} variant={Number(code) >= 500 ? 'error' : Number(code) >= 400 ? 'warning' : 'success'} />
                  <Text type="supporting" className="mono">{count} 次</Text>
                </HStack>
                <div className="bar-track">
                  <div
                    className={`bar-fill ${Number(code) >= 500 ? 'q-bad' : Number(code) >= 400 ? 'q-mid' : 'q-good'}`}
                    style={{width: `${(count / maxCount) * 100}%`}}
                  />
                </div>
              </div>
            ))}
            <Text type="supporting" style={{marginTop: 6}}>
              <span className="muted">
                M6 将接入 OpenTelemetry 全链路 Trace 与数据血缘可视化, 覆盖 LLM 请求 → 检索 → 生成
              </span>
            </Text>
          </VStack>
        </Card>
      </div>
    </div>
  );
}
