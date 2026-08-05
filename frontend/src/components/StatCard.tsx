import {Card} from '@astryxdesign/core/Card';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import type {ReactNode} from 'react';

interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  trend?: ReactNode;
  icon?: ReactNode;
}

export function StatCard({label, value, hint, trend, icon}: StatCardProps) {
  return (
    <Card variant="muted" style={{minWidth: 0}}>
      <HStack hAlign="between" vAlign="start">
        <VStack gap={2}>
          <Text type="supporting">{label}</Text>
          <Heading level={3} type="display-3" style={{fontSize: 30, lineHeight: 1.15}}>
            {value}
          </Heading>
          {hint && (
            <Text type="supporting">
              <span className="muted">{hint}</span>
            </Text>
          )}
        </VStack>
        {icon && <div style={{opacity: 0.65}}>{icon}</div>}
      </HStack>
      {trend}
    </Card>
  );
}
