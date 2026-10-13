import Link from 'next/link';
import type { CTALink } from '@/lib/content';

/** CMS 配置的 CTA 按钮渲染器（服务端组件安全） */
export function CtaButton({ cta, className = '' }: { cta: CTALink; className?: string }) {
  const cls = `btn-${cta.variant} ${className}`;
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
