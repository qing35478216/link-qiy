import type { Metadata } from 'next';
import { agentPage } from '@/lib/site';
import { SuperAssistantSection } from '@/components/home/super-assistant-section';
import { Icon } from '@/components/icons';

export const metadata: Metadata = {
  title: '超级 AI 助理 — 你的专属 SuperAgent',
  description: agentPage.hero.description,
};

export default function AgentPage() {
  const { capabilities, sections } = agentPage;
  return (
    <>
      <SuperAssistantSection content={agentPage.hero} />

      <section className="container-site py-16 sm:py-24">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {capabilities.map((c) => (
            <article key={c.title} className="card p-6">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-white/10 dark:text-brand-100">
                <Icon name={c.icon} className="h-6 w-6" />
              </span>
              <h2 className="mt-4 font-semibold">{c.title}</h2>
              <p className="text-secondary mt-2 text-sm leading-relaxed">{c.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="border-t py-16 sm:py-24" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-soft)' }}>
        <div className="container-site space-y-16">
          {sections.map((s, i) => (
            <div key={s.title} className={`grid items-center gap-8 lg:grid-cols-2 ${i % 2 === 1 ? 'lg:[&>*:first-child]:order-2' : ''}`}>
              <div>
                <h2 className="section-title text-xl sm:text-2xl">{s.title}</h2>
                <p className="text-secondary mt-2">{s.subtitle}</p>
                <ul className="mt-5 space-y-2.5">
                  {s.bullets.map((b) => (
                    <li key={b} className="flex items-center gap-2 text-sm">
                      <Icon name="check" className="h-4 w-4 shrink-0 text-brand-accent" />
                      {b}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="card flex h-48 items-center justify-center sm:h-64" aria-hidden>
                <Icon name="sparkles" className="text-brand-accent/40 h-12 w-12" />
              </div>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
