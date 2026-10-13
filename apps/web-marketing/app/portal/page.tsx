import type { Metadata } from 'next';
import { portal } from '@/lib/site';
import { CtaButton } from '@/components/cta-button';
import { Icon } from '@/components/icons';

export const metadata: Metadata = {
  title: '产品门户 — 一起探索 AI 生产力',
  description: portal.hero.subtitle,
};

export default function PortalPage() {
  const { hero, toolchain, highlights } = portal;
  return (
    <>
      <section className="relative overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-0" style={{ background: 'radial-gradient(600px 300px at 50% -10%, rgba(46,107,230,0.18), transparent 70%)' }} />
        <div className="container-site relative flex flex-col items-center py-20 text-center sm:py-24">
          <span className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium text-brand-500" style={{ borderColor: 'var(--border)' }}>
            {hero.badge}
          </span>
          <h1 className="mt-5 max-w-3xl text-3xl font-bold leading-tight sm:text-5xl">
            {hero.title}
            <span className="text-brand-500">{hero.titleHighlight}</span>
          </h1>
          <p className="text-secondary mt-5 max-w-2xl leading-relaxed sm:text-lg">{hero.subtitle}</p>
          <div className="mt-8 flex flex-wrap justify-center gap-4">
            {hero.ctas.map((cta) => (
              <CtaButton key={cta.label} cta={cta} />
            ))}
          </div>
        </div>
      </section>

      <section className="border-t py-16" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-soft)' }}>
        <div className="container-site">
          <div className="text-center">
            <h2 className="section-title">{toolchain.title}</h2>
            <p className="text-secondary mt-3">{toolchain.subtitle}</p>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {toolchain.items.map((item) => (
              <article key={item.title} className="card p-6">
                <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-white/10 dark:text-brand-100">
                  <Icon name={item.icon} className="h-6 w-6" />
                </span>
                <h3 className="mt-4 text-lg font-semibold">{item.title}</h3>
                <p className="text-secondary mt-2 text-sm leading-relaxed">{item.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="container-site py-16">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {highlights.map((h) => (
            <article key={h.title} className="card p-6 text-center">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-white/10 dark:text-brand-100">
                <Icon name={h.icon} className="h-6 w-6" />
              </span>
              <h3 className="mt-4 font-semibold">{h.title}</h3>
              <p className="text-secondary mt-2 text-sm leading-relaxed">{h.description}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
