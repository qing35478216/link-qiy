import type { Metadata } from 'next';
import { pricing, SITE_URL } from '@/lib/site';
import { PricingTabs } from '@/components/pricing-tabs';

export const metadata: Metadata = {
  title: '定价 — 版本与积分套餐',
  description: pricing.hero.subtitle,
};

export default function PricePage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'Product',
            name: 'LinkAI 智能体平台',
            description: pricing.hero.subtitle,
            offers: pricing.plans.map((p) => ({
              '@type': 'Offer',
              name: p.name,
              price: p.price.replace(/[¥/,年月]/g, '').trim(),
              priceCurrency: 'CNY',
              availability: 'https://schema.org/InStock',
              url: `${SITE_URL}/price/`,
            })),
          }),
        }}
      />
      <section className="container-site py-16 sm:py-20">
        <div className="text-center">
          <h1 className="section-title sm:text-4xl">{pricing.hero.title}</h1>
          <p className="text-secondary mt-3">{pricing.hero.subtitle}</p>
        </div>
        <div className="mt-10">
          <PricingTabs />
        </div>
      </section>
    </>
  );
}
