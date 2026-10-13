/**
 * CMS 内容加载与站点级常量。
 * 构建期静态导入 JSON，类型由 lib/content.ts 的 interfaces 保证（resolveJsonModule）。
 */
import type {
  SiteContent,
  HomeContent,
  PortalContent,
  AgentPageContent,
  PricingContent,
  NotFoundContent,
} from './content';

import siteJson from '@/content/site.json';
import homeJson from '@/content/home.json';
import portalJson from '@/content/portal.json';
import agentJson from '@/content/agent.json';
import pricingJson from '@/content/pricing.json';
import notFoundJson from '@/content/not-found.json';

export const site = siteJson as SiteContent;
export const home = homeJson as HomeContent;
export const portal = portalJson as PortalContent;
export const agentPage = agentJson as AgentPageContent;
export const pricing = pricingJson as PricingContent;
export const notFoundContent = notFoundJson as NotFoundContent;

export const SITE_URL = 'https://link-ai.tech';
export const SITE_NAME = site.brand.name;
export const SITE_DESCRIPTION =
  'LinkAI 一站式 AI 智能体平台：打造 7×24h 在线智能客服。平台做框架，用户做创造。';
