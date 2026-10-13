'use client';

import { useState } from 'react';
import { pricing } from '@/lib/site';
import { CtaButton } from './cta-button';
import { Icon } from './icons';

/** 定价页：版本升级 / 积分充值 双 Tab */
export function PricingTabs() {
  const [tab, setTab] = useState<'upgrade' | 'credits'>('upgrade');
  const { planTabs, plans, compare, credits } = pricing;
  const planCount = plans.length;

  return (
    <div>
      <div className="flex justify-center gap-2">
        {(['upgrade', 'credits'] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            aria-pressed={tab === key}
            className={`rounded-full px-6 py-2.5 text-sm font-medium transition-colors ${
              tab === key ? 'bg-brand-500 text-white' : 'border'
            }`}
            style={tab === key ? undefined : { borderColor: 'var(--border)' }}
          >
            {key === 'upgrade' ? planTabs.upgrade : planTabs.credits}
          </button>
        ))}
      </div>

      {tab === 'upgrade' && (
        <>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {plans.map((plan) => (
              <article key={plan.key} className="card relative flex flex-col p-6">
                {plan.badge && (
                  <span className="badge-red absolute -top-2.5 right-4 rounded-full px-2 py-0.5 text-[11px] font-medium text-white">
                    {plan.badge}
                  </span>
                )}
                {/* h1(页面 hero) 之后直接出现方案名，用 h2 保持标题层级连续 */}
                <h2 className="text-lg font-semibold">{plan.name}</h2>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="text-brand-accent text-2xl font-bold">{plan.price}</span>
                  {plan.originalPrice && (
                    <span className="text-secondary text-sm line-through">{plan.originalPrice}</span>
                  )}
                </div>
                {plan.billingOptions && (
                  <div className="mt-3 flex gap-2 text-xs">
                    {plan.billingOptions.map((o) => (
                      <span key={o.label} className="rounded-full border px-2 py-1" style={{ borderColor: 'var(--border)' }}>
                        {o.label}
                        {o.note && <em className="text-secondary not-italic">（{o.note}）</em>}
                      </span>
                    ))}
                  </div>
                )}
                <p className="text-secondary mt-3 flex-1 text-sm">{plan.tagline}</p>
                <div className="mt-5">
                  <CtaButton cta={plan.cta} className="w-full" />
                </div>
              </article>
            ))}
          </div>

          <h2 className="section-title mt-16 text-center text-xl sm:text-2xl">{compare.title}</h2>
          <div className="card mt-8 overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-b" style={{ borderColor: 'var(--border)' }}>
                  <th className="p-4 text-left font-medium">权益</th>
                  {plans.map((p) => (
                    <th key={p.key} className={`p-4 text-center font-semibold ${p.key === 'standard' ? 'text-brand-accent' : ''}`}>
                      {p.name}
                      <span className="text-secondary block text-xs font-normal">{p.price}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {compare.rows.map((row, i) =>
                  row.group ? (
                    <tr key={`g-${i}`} className="border-b" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-soft)' }}>
                      <td colSpan={planCount + 1} className="text-brand-accent px-4 py-2.5 text-xs font-semibold uppercase tracking-wide">
                        {row.group}
                      </td>
                    </tr>
                  ) : (
                    <tr key={`r-${i}`} className="border-b last:border-0" style={{ borderColor: 'var(--border)' }}>
                      <td className="p-4 align-top">{row.feature}</td>
                      {row.values.map((v, j) => (
                        <td key={j} className="p-4 text-center align-top">
                          {v === null ? (
                            <span className="text-secondary">✗</span>
                          ) : v === '✔' ? (
                            <Icon name="check" className="text-brand-accent mx-auto h-4 w-4" />
                          ) : (
                            v
                          )}
                        </td>
                      ))}
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'credits' && (
        <div className="mt-10">
          <div className="text-center">
            <h2 className="section-title text-xl sm:text-2xl">{credits.title}</h2>
            <p className="text-secondary mt-2 text-sm">{credits.subtitle}</p>
          </div>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {credits.packs.map((pack) => (
              <article key={pack.points} className="card relative p-6 text-center">
                {pack.badge && (
                  <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-brand-500 px-2 py-0.5 text-[11px] text-white">
                    {pack.badge}
                  </span>
                )}
                <p className="text-xl font-bold">{pack.points} 积分</p>
                <p className="text-brand-accent mt-2 text-2xl font-bold">{pack.price}</p>
                <p className="text-secondary mt-2 text-xs">{pack.tagline}</p>
              </article>
            ))}
          </div>
          <p className="text-secondary mt-6 text-center text-sm">{credits.freeNote}</p>
        </div>
      )}

      <div id="consult" className="card mt-12 flex flex-col items-center justify-between gap-4 p-6 text-center sm:flex-row sm:text-left">
        <div>
          <h3 className="font-semibold">企业版按需定制</h3>
          <p className="text-secondary mt-1 text-sm">私有化部署、最高优先级保障、训练调优，欢迎咨询。</p>
        </div>
        <CtaButton cta={{ label: pricing.consultation.label, href: pricing.consultation.href, variant: 'primary' }} />
      </div>
    </div>
  );
}
