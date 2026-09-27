import { useState } from "react";
import { BackendNote } from "./BackendNote";
import { AgentsSection } from "./landing/AgentsSection";
import { ArchitectureSection } from "./landing/ArchitectureSection";
import { CapabilitySection } from "./landing/CapabilitySection";
import { ContextSection } from "./landing/ContextSection";
import { CTASection } from "./landing/CTASection";
import { DemoSection } from "./landing/DemoSection";
import { EvaluationSection } from "./landing/EvaluationSection";
import { Footer } from "./landing/Footer";
import { HeroSection } from "./landing/HeroSection";
import { LandingNavbar } from "./landing/LandingNavbar";
import { ModelsSection } from "./landing/ModelsSection";
import { ProcessSection } from "./landing/ProcessSection";
import { ProductSection } from "./landing/ProductSection";
import { SecuritySection } from "./landing/SecuritySection";
import { ToolsSection } from "./landing/ToolsSection";
import { WhySection } from "./landing/WhySection";
import "./landing/landing.css";

type LandingProps = {
  onEnter: () => void;
};

export function Landing({ onEnter }: LandingProps) {
  const [scroller, setScroller] = useState<HTMLDivElement | null>(null);

  function goArchitecture() {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById("architecture")?.scrollIntoView({
      behavior: reduce ? "auto" : "smooth",
      block: "start",
    });
  }

  return (
    <div ref={setScroller} className="scroll h-full min-h-0 overflow-x-hidden overflow-y-auto bg-[var(--bg)]">
      <BackendNote />
      <LandingNavbar scroller={scroller} onLaunch={onEnter} />
      <main>
        <HeroSection onLaunch={onEnter} onArchitecture={goArchitecture} />
        <ProductSection />
        <ProcessSection />
        <AgentsSection />
        <ModelsSection />
        <ToolsSection />
        <CapabilitySection />
        <ArchitectureSection />
        <ContextSection />
        <EvaluationSection />
        <SecuritySection />
        <DemoSection />
        <WhySection />
        <CTASection onLaunch={onEnter} />
      </main>
      <Footer onLaunch={onEnter} />
    </div>
  );
}
