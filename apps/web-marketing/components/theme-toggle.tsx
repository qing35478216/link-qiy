'use client';

import { useEffect, useState } from 'react';
import { Icon } from './icons';

type Theme = 'light' | 'dark';

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  try {
    localStorage.setItem('theme', theme);
  } catch {
    /* SSR / privacy mode */
  }
}

/** 暗色模式开关。初始化逻辑见 app/layout.tsx 的内联脚本（防 FOUC）。 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('light');

  useEffect(() => {
    setTheme(document.documentElement.classList.contains('dark') ? 'dark' : 'light');
  }, []);

  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    setTheme(next);
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === 'dark' ? '切换到浅色模式' : '切换到暗色模式'}
      className="inline-flex h-9 w-9 items-center justify-center rounded-full border"
      style={{ borderColor: 'var(--border)' }}
    >
      <Icon name={theme === 'dark' ? 'sun' : 'moon'} className="h-4.5 w-4.5 h-[18px] w-[18px]" />
    </button>
  );
}
