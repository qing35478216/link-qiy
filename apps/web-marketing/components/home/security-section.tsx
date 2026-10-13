import { home } from '@/lib/site';
import { Icon } from '../icons';

export function SecuritySection() {
  const { security } = home;
  return (
    <section id="security" className="border-y py-16 sm:py-24" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-soft)' }}>
      <div className="container-site">
        <div className="text-center">
          <h2 className="section-title">{security.title}</h2>
          <p className="text-secondary mt-3">{security.subtitle}</p>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {security.items.map((item) => (
            <div key={item.title} className="card flex items-start gap-4 p-6">
              <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-white/10 dark:text-brand-100">
                <Icon name="shield" className="h-5 w-5" />
              </span>
              <div>
                <h3 className="font-semibold">{item.title}</h3>
                <p className="text-secondary mt-1 text-sm">{item.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
