import DownloadButtons from "./DownloadButtons";

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
            <DownloadButtons />
          </div>
          <p className="mt-[48px] font-mono text-xs text-text-secondary">
            KiCad 10 recommended.
          </p>
        </div>
      </div>
    </section>
  );
}
