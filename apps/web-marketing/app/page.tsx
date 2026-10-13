import { HeroSection } from '@/components/home/hero-section';
import { LogoWall } from '@/components/home/logo-wall';
import { ScenarioCarousel } from '@/components/home/scenario-carousel';
import { SuperAssistantSection } from '@/components/home/super-assistant-section';
import { FeatureTabs } from '@/components/home/feature-tabs';
import { SecuritySection } from '@/components/home/security-section';
import { OpenSourceSection } from '@/components/home/opensource-section';
import { AboutSection } from '@/components/home/about-section';
import { home } from '@/lib/site';

export default function HomePage() {
  return (
    <>
      <HeroSection />
      <LogoWall />
      <ScenarioCarousel />
      <SuperAssistantSection content={home.superAssistant} />
      <FeatureTabs />
      <SecuritySection />
      <OpenSourceSection />
      <AboutSection />
    </>
  );
}
