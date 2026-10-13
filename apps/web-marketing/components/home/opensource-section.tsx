import { home } from '@/lib/site';
import { Icon } from '../icons';

export function OpenSourceSection() {
  const { openSource } = home;
  return (
    <section id="opensource" className="container-site py-16 sm:py-24">
      <div className="text-center">
        <h2 className="section-title">{openSource.title}</h2>
        <p className="text-secondary mt-3">{openSource.subtitle}</p>
      </div>
      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {openSource.items.map((item) => (
          <a
            key={item.name}
            href={item.href}
            target="_blank"
            rel="noopener noreferrer"
            className="card group p-6 transition-shadow hover:shadow-lg"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold group-hover:text-brand-500">{item.name}</h3>
              <span className="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs" style={{ borderColor: 'var(--border)' }}>
                <Icon name="star" className="h-3.5 w-3.5 text-amber-500" />
                {item.stars}
              </span>
            </div>
            <p className="text-secondary mt-2 text-sm leading-relaxed">{item.description}</p>
          </a>
        ))}
      </div>
    </section>
  );
}
