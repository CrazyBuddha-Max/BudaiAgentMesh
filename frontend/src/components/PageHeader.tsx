import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import type {ReactNode} from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

export function PageHeader({title, description, actions}: PageHeaderProps) {
  return (
    <HStack hAlign="between" vAlign="center" gap={4}>
      <VStack gap={1}>
        <Heading level={1}>{title}</Heading>
        {description && <Text type="body"><span className="muted">{description}</span></Text>}
      </VStack>
      {actions && <HStack gap={2}>{actions}</HStack>}
    </HStack>
  );
}
