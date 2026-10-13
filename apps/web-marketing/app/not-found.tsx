import Link from 'next/link';
import { notFoundContent } from '@/lib/site';
import { CtaButton } from '@/components/cta-button';

export default function NotFound() {
  return (
    <section className="container-site flex min-h-[60vh] flex-col items-center justify-center py-24 text-center">
      <p className="text-7xl font-bold text-brand-500/30">404</p>
      <h1 className="section-title mt-4">{notFoundContent.title}</h1>
      <p className="text-secondary mt-3">{notFoundContent.description}</p>
      <div className="mt-8 flex flex-wrap justify-center gap-4">
        <CtaButton cta={notFoundContent.primaryCta} />
        <CtaButton cta={notFoundContent.secondaryCta} />
      </div>
    </section>
  );
}
