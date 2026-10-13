import type { HomeContent } from '@/lib/content';
import { CtaButton } from '../cta-button';
import { Icon } from '../icons';

type Props = { content: HomeContent['superAssistant'] };

/** 超级 AI 助理大图区（首页与 /agent 页复用） */
export function SuperAssistantSection({ content }: Props) {
  return (
    <section className="border-y py-16 sm:py-24" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-soft)' }}>
      <div className="container-site grid items-center gap-10 lg:grid-cols-2">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium text-brand-500" style={{ borderColor: 'var(--border)' }}>
            <Icon name="sparkles" className="h-3.5 w-3.5" />
            {content.badge}
          </span>
          <h2 className="section-title mt-5">
            {content.title}
            <span className="text-brand-500">{content.titleHighlight}</span>
          </h2>
          <p className="text-secondary mt-4 leading-relaxed">{content.description}</p>
          <ul className="mt-6 space-y-2.5">
            {['持久记忆，越用越懂你', '自主拆解复杂目标，智能规划', '多模态交互与技能扩展'].map((s) => (
              <li key={s} className="flex items-center gap-2 text-sm">
                <Icon name="check" className="h-4 w-4 text-brand-500" />
                {s}
              </li>
            ))}
          </ul>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            {content.ctas.map((cta) => (
              <CtaButton key={cta.label} cta={cta} />
            ))}
            <CtaButton cta={content.docLink} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {content.stats.map((s) => (
            <div key={s.label} className="card p-6 text-center">
              <p className="text-2xl font-bold text-brand-500 sm:text-3xl">{s.value}</p>
              <p className="text-secondary mt-1 text-sm">{s.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
