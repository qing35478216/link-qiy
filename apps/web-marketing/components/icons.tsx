/**
 * 内联 SVG 图标集（stroke 风格，零第三方依赖，见 ADOPTED-TOOLS.md）。
 * 图标名来自 content/*.json 中的 icon 字段。
 */
import type { SVGProps } from 'react';

type P = SVGProps<SVGSVGElement>;

const base: P = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
};

const ICONS: Record<string, (p: P) => JSX.Element> = {
  headset: (p) => (
    <svg {...base} {...p}><path d="M4 13a8 8 0 0 1 16 0" /><path d="M4 13v3a2 2 0 0 0 2 2h1v-5H6a2 2 0 0 0-2 2Z" /><path d="M20 13v3a2 2 0 0 1-2 2h-1v-5h1a2 2 0 0 1 2 2Z" /><path d="M17 18v1a2 2 0 0 1-2 2h-2" /></svg>
  ),
  health: (p) => (
    <svg {...base} {...p}><path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3.4 1-4.5 2.2C10.9 4 9.3 3 7.5 3A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z" /><path d="M8 12h2l1.5-3 2 5L15 12h2" /></svg>
  ),
  factory: (p) => (
    <svg {...base} {...p}><path d="M3 21V10l6 4V10l6 4V6l6-3v18H3Z" /></svg>
  ),
  chart: (p) => (
    <svg {...base} {...p}><path d="M3 3v18h18" /><path d="M7 15v-4M12 15V7M17 15v-6" /></svg>
  ),
  users: (p) => (
    <svg {...base} {...p}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.8-3.2 3.4-5 6.5-5s5.7 1.8 6.5 5" /><circle cx="17" cy="9" r="2.5" /><path d="M17.5 14.5c2.3.4 3.7 1.9 4 4.5" /></svg>
  ),
  chip: (p) => (
    <svg {...base} {...p}><rect x="6" y="6" width="12" height="12" rx="2" /><rect x="10" y="10" width="4" height="4" /><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" /></svg>
  ),
  app: (p) => (
    <svg {...base} {...p}><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></svg>
  ),
  workflow: (p) => (
    <svg {...base} {...p}><circle cx="5" cy="6" r="2.5" /><circle cx="19" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M7.5 6h9M6 8.5 10.5 16M18 8.5 13.5 16" /></svg>
  ),
  knowledge: (p) => (
    <svg {...base} {...p}><path d="M4 19V6a2 2 0 0 1 2-2h13v13H6a2 2 0 0 0-2 2Zm0 0a2 2 0 0 0 2 2h13" /><path d="M9 8h7M9 12h5" /></svg>
  ),
  database: (p) => (
    <svg {...base} {...p}><ellipse cx="12" cy="5.5" rx="8" ry="2.5" /><path d="M4 5.5v13c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5v-13" /><path d="M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5" /></svg>
  ),
  plugins: (p) => (
    <svg {...base} {...p}><path d="M9 3v5H4a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h5v5h6v-5h5a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1h-5V3H9Z" /><circle cx="12" cy="12" r="2.5" /></svg>
  ),
  models: (p) => (
    <svg {...base} {...p}><rect x="7" y="7" width="10" height="10" rx="2" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5.5 5.5 7 7M17 17l1.5 1.5M18.5 5.5 17 7M7 17l-1.5 1.5" /></svg>
  ),
  channels: (p) => (
    <svg {...base} {...p}><path d="M4 11a8 8 0 0 1 16 0" /><path d="M7.5 14.5a4.5 4.5 0 0 1 9 0" /><circle cx="12" cy="18" r="1.2" fill="currentColor" /></svg>
  ),
  chat: (p) => (
    <svg {...base} {...p}><path d="M21 12a8 8 0 0 1-8 8H4l2-3.2A8 8 0 1 1 21 12Z" /><path d="M8.5 11h.01M12 11h.01M15.5 11h.01" /></svg>
  ),
  team: (p) => (
    <svg {...base} {...p}><circle cx="8" cy="8" r="3" /><circle cx="16.5" cy="9.5" r="2.5" /><path d="M2.5 20c.7-3 2.9-4.7 5.5-4.7s4.8 1.7 5.5 4.7" /><path d="M14.5 15.7c2.2.2 3.8 1.7 4.5 4.3" /></svg>
  ),
  shield: (p) => (
    <svg {...base} {...p}><path d="M12 2 4 5.5V11c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5.5L12 2Z" /><path d="m8.5 12 2.5 2.5 4.5-4.5" /></svg>
  ),
  opensource: (p) => (
    <svg {...base} {...p}><path d="M9.5 3C5.5 4 3 7.5 3.8 11.5c.5 2.7 2.3 4.4 4 5.5-.4 1.4-.8 2.6-1.3 4" /><path d="M14.5 3c4 1 6.5 4.5 5.7 8.5-.5 2.7-2.3 4.4-4 5.5.4 1.4.8 2.6 1.3 4" /><path d="M15 21c-1.5-1-2-3-1.5-4.5" /></svg>
  ),
  rocket: (p) => (
    <svg {...base} {...p}><path d="M12 15c-1.5-4.5 0-9 4-12 3 1 5.5 3.5 6 6.5-3 4-7.5 5.5-10 5.5Z" /><path d="M9 12c-2 .5-4 2-5 5 1.5 1.5 3.5 2.5 6 2-.5-2.5-.5-4.5-1-7Z" /><path d="M12 15c-.5 2.5-.5 4.5 0 7 2.5-.5 4.5-1.5 6-3.5-3-1-4.5-2-6-3.5Z" /><circle cx="15.5" cy="8.5" r="1.5" /></svg>
  ),
  sliders: (p) => (
    <svg {...base} {...p}><path d="M4 6h8M16 6h4M4 12h4M12 12h8M4 18h10M18 18h2" /><circle cx="14" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="16" cy="18" r="2" /></svg>
  ),
  brain: (p) => (
    <svg {...base} {...p}><path d="M9.5 3A3.5 3.5 0 0 0 6 6.5c-1.8.6-3 2.2-3 4A4 4 0 0 0 5 14a4 4 0 0 0 8 .5V5.5A3.5 3.5 0 0 0 9.5 3Z" /><path d="M14.5 3A3.5 3.5 0 0 1 18 6.5c1.8.6 3 2.2 3 4a4 4 0 0 1-2 3.5 4 4 0 0 1-8 .5" /></svg>
  ),
  plan: (p) => (
    <svg {...base} {...p}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 10h8M8 14h5" /><path d="m15 16.5 2 2 3.5-3.5" /></svg>
  ),
  multimodal: (p) => (
    <svg {...base} {...p}><path d="M2 12a3 3 0 0 1 3-3h1a2 2 0 0 0 2-2 2 2 0 0 1 4 0 2 2 0 0 0 2 2h4a3 3 0 0 1 3 3v1a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1Z" /><path d="M12 12v5M9.5 14.5 12 12l2.5 2.5" /></svg>
  ),
  clock: (p) => (
    <svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></svg>
  ),
  sparkles: (p) => (
    <svg {...base} {...p}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" /><path d="M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z" /></svg>
  ),
  moon: (p) => (
    <svg {...base} {...p}><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z" /></svg>
  ),
  sun: (p) => (
    <svg {...base} {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" /></svg>
  ),
  menu: (p) => (
    <svg {...base} {...p}><path d="M4 7h16M4 12h16M4 17h16" /></svg>
  ),
  close: (p) => (
    <svg {...base} {...p}><path d="M6 6l12 12M18 6 6 18" /></svg>
  ),
  check: (p) => (
    <svg {...base} {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
  ),
  star: (p) => (
    <svg {...base} {...p}><path d="m12 3 2.7 5.8 6.3.8-4.6 4.3 1.2 6.1L12 17l-5.6 3 1.2-6.1L3 9.6l6.3-.8L12 3Z" /></svg>
  ),
  arrowRight: (p) => (
    <svg {...base} {...p}><path d="M4 12h15M13 6l6 6-6 6" /></svg>
  ),
};

export function Icon({ name, ...props }: P & { name: string }) {
  const Cmp = ICONS[name] ?? ICONS.sparkles!;
  return <Cmp {...props} />;
}
