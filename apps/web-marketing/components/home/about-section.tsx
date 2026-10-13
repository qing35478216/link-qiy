import { home } from '@/lib/site';

export function AboutSection() {
  const { about } = home;
  return (
    <section id="about" className="border-t py-16 sm:py-24" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-soft)' }}>
      <div className="container-site max-w-3xl text-center">
        <h2 className="section-title">{about.title}</h2>
        {about.paragraphs.map((p) => (
          <p key={p.slice(0, 16)} className="text-secondary mt-5 leading-relaxed">
            {p}
          </p>
        ))}
        <p className="mt-8 text-sm font-medium">
          愿景：<span className="text-brand-accent">{about.vision}</span>
        </p>
        <p className="text-secondary mt-2 text-xs">{about.teamNote}</p>
      </div>
    </section>
  );
}
