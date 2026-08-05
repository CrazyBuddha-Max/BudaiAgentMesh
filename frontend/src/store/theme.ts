import {create} from 'zustand';
import {persist} from 'zustand/middleware';

export type ThemeMode = 'system' | 'light' | 'dark';

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  /** 在亮/暗之间切换 (跟随系统时以系统当前偏好为准) */
  toggle: () => void;
}

export function effectiveTheme(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'light' || mode === 'dark') return mode;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      mode: 'system',
      setMode: (mode) => set({mode}),
      toggle: () => {
        const next = effectiveTheme(get().mode) === 'dark' ? 'light' : 'dark';
        set({mode: next});
      },
    }),
    {name: 'budai-theme'},
  ),
);
