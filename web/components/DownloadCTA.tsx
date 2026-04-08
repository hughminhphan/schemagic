import InstallCommand from "./InstallCommand";

export default function DownloadCTA() {
  return (
    <section id="download">
      <div className="mx-auto max-w-6xl px-6 py-[96px]">
        <div className="flex flex-col items-center text-center">
          <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
            Get scheMAGIC
          </h2>
          <p className="mt-[24px] text-text-secondary">
            Stop drawing symbols by hand.
          </p>
          <div className="mt-[48px]">
            <InstallCommand />
            <p className="mt-[24px] font-mono text-xs text-text-secondary">
              or{" "}
              <a
                href="https://github.com/hughminhphan/schemagic-webapp/releases/download/v0.1.0/scheMAGIC.dmg"
                className="underline hover:text-text-primary transition-colors"
              >
                download DMG directly
              </a>
            </p>
          </div>
          <p className="mt-[48px] font-mono text-xs text-text-secondary">
            Requires KiCad 8.0+
          </p>
        </div>
      </div>
    </section>
  );
}
