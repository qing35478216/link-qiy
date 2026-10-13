'use client';

import { useState } from 'react';
import { home } from '@/lib/site';
import { Icon } from '../icons';
import { CtaButton } from '../cta-button';

/** 产品功能 9 Tab（默认展示"应用"） */
export function FeatureTabs() {
  const { featureTabs } = home;
  const [active, setActive] = useState(featureTabs.tabs[0]?.key ?? '');
  const tab = featureTabs.tabs.find((t) => t.key === active) ?? featureTabs.tabs[0]!;

  return (
    <section className="container-site py-16 sm:py-24">
      <div className="text-center">
        <h2 className="section-title">{featureTabs.title}</h2>
        <p className="text-secondary mt-3">{featureTabs.subtitle}</p>
      </div>
      <div className="mt-10 flex flex-wrap justify-center gap-2">
        {featureTabs.tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActive(t.key)}
            aria-pressed={t.key === active}
            className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm transition-colors ${
              t.key === active
                ? 'border-brand-500 bg-brand-500 text-white'
                : ''
            }`}
            style={t.key === active ? undefined : { borderColor: 'var(--border)', backgroundColor: 'var(--bg-card)', color: 'var(--text-secondary)' }}
          >
            <Icon name={t.icon} className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>
      <div className="card mx-auto mt-8 grid max-w-4xl gap-8 p-8 sm:p-10 lg:grid-cols-[auto_1fr]">
        <span className="hidden h-16 w-16 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 lg:inline-flex dark:bg-white/10 dark:text-brand-100">
          <Icon name={tab.icon} className="h-8 w-8" />
        </span>
        <div>
          <h3 className="text-xl font-bold">{tab.title}</h3>
          <p className="text-secondary mt-3 leading-relaxed">{tab.description}</p>
          <ul className="mt-5 grid gap-2.5 sm:grid-cols-2">
            {tab.bullets.map((b) => (
              <li key={b} className="flex items-center gap-2 text-sm">
                <Icon name="check" className="h-4 w-4 shrink-0 text-brand-500" />
                {b}
              </li>
            ))}
          </ul>
          <div className="mt-6">
            <CtaButton cta={tab.cta} />
          </div>
        </div>
      </div>
    </section>
  );
}
