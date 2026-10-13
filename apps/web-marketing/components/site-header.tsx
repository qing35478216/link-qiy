'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { site } from '@/lib/site';
import { CtaButton } from './cta-button';
import { ThemeToggle } from './theme-toggle';
import { Icon } from './icons';

export function SiteHeader() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  const isActive = (href: string) => {
    const path = href.split('#')[0];
    return path !== '' && pathname === path;
  };

  return (
    <header className="sticky top-0 z-50 border-b backdrop-blur" style={{ borderColor: 'var(--border)', backgroundColor: 'color-mix(in srgb, var(--bg) 85%, transparent)' }}>
      <div className="container-site flex h-16 items-center justify-between gap-4">
        {/* 无 aria-label：可见文字（logoText）本身即品牌名，加 aria-label 会与可见文本不匹配 */}
        <Link href="/" className="flex items-center gap-2 text-lg font-bold tracking-tight">
          <span aria-hidden className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-white">
            <Icon name="sparkles" className="h-5 w-5" />
          </span>
          {site.brand.logoText}
        </Link>

        <nav className="hidden items-center gap-1 lg:flex" aria-label="主导航">
          {site.nav.map((item) => (
            <div key={item.label} className="group relative">
              <Link
                href={item.href}
                className={`inline-flex items-center gap-1 rounded-full px-3 py-2 text-sm transition-colors ${
                  isActive(item.href) ? 'text-brand-accent font-medium' : 'hover:text-brand-accent'
                }`}
              >
                {item.label}
                {item.badge && (
                  <span className="badge-red rounded-full px-1.5 py-0.5 text-[10px] font-medium leading-none text-white">
                    {item.badge}
                  </span>
                )}
                {item.children && <Icon name="arrowRight" className="h-3 w-3 rotate-90 opacity-60" />}
              </Link>
              {item.children && (
                <div className="invisible absolute left-0 top-full w-64 pt-2 opacity-0 transition-all group-hover:visible group-hover:opacity-100">
                  <div className="card p-2 shadow-xl">
                    {item.children.map((child) => (
                      <Link
                        key={child.label}
                        href={child.href}
                        className="block rounded-xl px-3 py-2 hover:bg-brand-50 dark:hover:bg-white/5"
                      >
                        <span className="block text-sm font-medium">{child.label}</span>
                        {child.description && (
                          <span className="text-secondary block text-xs">{child.description}</span>
                        )}
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </nav>

        <div className="hidden items-center gap-3 lg:flex">
          <ThemeToggle />
          {site.actions.login.variant === 'text' ? (
            <Link href={site.actions.login.href} className="text-sm hover:text-brand-accent">
              {site.actions.login.label}
            </Link>
          ) : null}
          <CtaButton cta={site.actions.primary} />
        </div>

        <div className="flex items-center gap-2 lg:hidden">
          <ThemeToggle />
          <button
            type="button"
            aria-label="打开菜单"
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((v) => !v)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border"
            style={{ borderColor: 'var(--border)' }}
          >
            <Icon name={mobileOpen ? 'close' : 'menu'} className="h-5 w-5" />
          </button>
        </div>
      </div>

      {mobileOpen && (
        <nav className="border-t lg:hidden" style={{ borderColor: 'var(--border)' }} aria-label="移动端导航">
          <div className="container-site flex flex-col gap-1 py-3">
            {site.nav.map((item) => (
              <Link
                key={item.label}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className="rounded-lg px-3 py-2.5 text-sm hover:bg-brand-50 dark:hover:bg-white/5"
              >
                {item.label}
                {item.badge && (
                  <span className="badge-red ml-2 rounded-full px-1.5 py-0.5 text-[10px] text-white">{item.badge}</span>
                )}
              </Link>
            ))}
            <div className="mt-2 flex items-center gap-3">
              <Link href={site.actions.login.href} className="btn-secondary flex-1">
                {site.actions.login.label}
              </Link>
              <CtaButton cta={site.actions.primary} className="flex-1" />
            </div>
          </div>
        </nav>
      )}
    </header>
  );
}
