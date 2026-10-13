import Link from 'next/link';
import { site } from '@/lib/site';
import { Icon } from './icons';

export function SiteFooter() {
  return (
    <footer className="border-t" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-soft)' }}>
      <div className="container-site grid gap-10 py-14 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <div className="flex items-center gap-2 text-lg font-bold">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-white">
              <Icon name="sparkles" className="h-5 w-5" />
            </span>
            {site.brand.logoText}
          </div>
          <p className="text-secondary mt-4 max-w-sm text-sm leading-relaxed">{site.footer.about}</p>
        </div>
        {site.footer.columns.map((col) => (
          <nav key={col.title} aria-label={col.title}>
            <h3 className="text-sm font-semibold">{col.title}</h3>
            <ul className="mt-4 space-y-2.5">
              {col.links.map((link) => (
                <li key={link.label}>
                  <Link href={link.href} className="text-secondary text-sm hover:text-brand-accent">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="border-t" style={{ borderColor: 'var(--border)' }}>
        <div className="container-site flex flex-col items-center justify-between gap-3 py-5 text-xs text-secondary sm:flex-row">
          <div className="flex items-center gap-4">
            {site.footer.agreements.map((a) => (
              <Link key={a.label} href={a.href} className="hover:text-brand-accent">
                {a.label}
              </Link>
            ))}
            <span>{site.footer.icp}</span>
          </div>
          <p>{site.footer.copyright}</p>
        </div>
      </div>
    </footer>
  );
}
