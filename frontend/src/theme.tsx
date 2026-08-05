import React from 'react';
import {Theme} from '@astryxdesign/core/theme';
import {LinkProvider} from '@astryxdesign/core/Link';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {Link} from 'react-router';
import {useThemeStore} from '@/store/theme';

/**
 * Astryx 主题提供者: 中性极简主题 + 路由链接适配 + 亮/暗/跟随系统切换
 * 说明: 页面禁用表情符号, 遵循信息密度优先的极简规范
 */
export function ThemeProvider({children}: {children: React.ReactNode}) {
  const mode = useThemeStore((s) => s.mode);
  return (
    <Theme theme={neutralTheme} mode={mode}>
      <LinkProvider component={Link}>{children}</LinkProvider>
    </Theme>
  );
}
