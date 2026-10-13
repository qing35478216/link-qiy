import Link from 'next/link';
import type { CTALink } from '@/lib/content';

/**
 * CMS 配置的 CTA 按钮渲染器（服务端组件安全）。
 *
 * variant → 类名必须是**完整字面量**，不能靠模板拼接（`btn-${variant}`）：
 * Tailwind 只扫描源码里出现过的完整类名，拼接出来的 btn-primary / btn-text
 * 永远匹配不到，@layer components 里的定义便不会产出，
 * 最终按钮会渲染成没有任何样式的纯文字。变体新增时记得同步 safelist/tailwind.config.ts。
 */
const VARIANT_CLASS: Record<CTALink['variant'], string> = {
  primary: 'btn-primary',
  secondary: 'btn-secondary',
  text: 'btn-text',
};

/** 这些字面量供 Tailwind 扫描器识别（写在源码中，不会产生冗余 CSS） */
export const CTA_VARIANT_CLASSES = ['btn-primary', 'btn-secondary', 'btn-text'] as const;

export function CtaButton({ cta, className = '' }: { cta: CTALink; className?: string }) {
  const cls = `${VARIANT_CLASS[cta.variant]} ${className}`;
  const external = /^https?:\/\//.test(cta.href);
  if (cta.variant === 'text') {
    return (
      <Link href={cta.href} className={`${cls} inline-flex items-center gap-1`}>
        {cta.label}
      </Link>
    );
  }
  return (
    <Link
      href={cta.href}
      className={cls}
      {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
    >
      {cta.label}
    </Link>
  );
}
