import Nav from "@/components/Nav";
import Hero from "@/components/Hero";
import HowItWorks from "@/components/HowItWorks";
import Features from "@/components/Features";
import Pricing from "@/components/Pricing";
import DownloadCTA from "@/components/DownloadCTA";

export default function Home() {
  return (
    <div className="grid-bg min-h-screen">
      <Nav />
      <main>
        <Hero />
        <HowItWorks />
        <Features />
        <Pricing />
        <DownloadCTA />
      </main>
    </div>
  );
}
