"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import JSZip from "jszip";
import AppShell from "@/components/app/AppShell";
import AuthGate from "@/components/app/AuthGate";
import {
  useWizard,
  useWizardDispatch,
} from "@/components/app/WizardProvider";
import { useLicenseContext } from "@/components/app/LicenseContext";
import SymbolViewer from "@/components/app/SymbolViewer";
import FootprintViewer from "@/components/app/FootprintViewer";
import PinEditPanel from "@/components/app/PinEditPanel";
import PinReviewTable from "@/components/app/PinReviewTable";
import { usePinReviewData } from "@/hooks/usePinReviewData";
import { generateSyntheticSymbol } from "@/lib/generate-synthetic-symbol";
import { apiBase, fetchWithLicense } from "@/lib/api-base";
import { Button, Card, CardRow, TerminalLine } from "@/components/ui";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

async function minimizeTauriWindow() {
  if (typeof window === "undefined") return;
  try {
    const mod = await import("@tauri-apps/api/window");
    await mod.getCurrentWindow().minimize();
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("[schemagic] minimize failed:", err);
  }
}

function WizardPinReview() {
  const router = useRouter();
  const {
    pins,
    match,
    datasheet,
    jobId,
    partNumber,
    candidates,
    detectedProject,
    selectedPinNumber,
    files,
    model,
    step,
    error,
  } = useWizard();
  const dispatch = useWizardDispatch();
  const { acquireToken } = useLicenseContext();
  const { symbolData, footprintData, loading } = usePinReviewData(match);
  const [showTable, setShowTable] = useState(false);
  const [switchingPackage, setSwitchingPackage] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const minimizedRef = useRef(false);

  // Redirect to idle if there's no pipeline data (e.g. direct navigation)
  useEffect(() => {
    if (step === "IDLE") {
      router.replace("/wizard/idle");
    } else if (step === "ERROR") {
      router.replace("/wizard/running?error=1");
    }
  }, [step, router]);

  const effectiveSymbolData = symbolData ?? generateSyntheticSymbol(pins);

  // Resolve "EP" (exposed pad) to the real footprint pad number
  const epPadNumber = useMemo(() => {
    if (!footprintData?.pads) return null;
    let largest: { number: string; area: number } | null = null;
    for (const pad of footprintData.pads) {
      if (!pad.number) continue;
      const area = pad.size[0] * pad.size[1];
      if (!largest || area > largest.area) {
        largest = { number: pad.number, area };
      }
    }
    if (!largest) return null;
    const areas = footprintData.pads
      .filter((p) => p.number)
      .map((p) => p.size[0] * p.size[1])
      .sort((a, b) => a - b);
    const median = areas[Math.floor(areas.length / 2)] || 1;
    return largest.area > median * 3 ? largest.number : null;
  }, [footprintData]);

  const { padToPinMap, highlightedPads } = useMemo(() => {
    const nameGroups = new Map<string, string[]>();
    for (const pin of pins) {
      const key = pin.name.toUpperCase();
      const group = nameGroups.get(key);
      if (group) group.push(pin.number);
      else nameGroups.set(key, [pin.number]);
    }

    const map = new Map<string, string>();
    for (const pin of pins) {
      const key = pin.name.toUpperCase();
      const group = nameGroups.get(key)!;
      const primary = group[0];
      map.set(pin.number, primary);
      for (const alt of pin.alt_numbers) {
        if (alt === "EP" && epPadNumber) map.set(epPadNumber, primary);
        else map.set(alt, primary);
      }
    }
    const epPin = pins.find((p) => p.number === "EP");
    if (epPin && epPadNumber) {
      const key = epPin.name.toUpperCase();
      const group = nameGroups.get(key);
      map.set(epPadNumber, group ? group[0] : epPin.number);
    }

    const highlighted = new Set<string>();
    if (selectedPinNumber) {
      const selectedPin = pins.find((p) => p.number === selectedPinNumber);
      if (selectedPin) {
        const key = selectedPin.name.toUpperCase();
        const group = nameGroups.get(key) || [selectedPin.number];
        for (const num of group) {
          highlighted.add(num);
          const p = pins.find((pp) => pp.number === num);
          if (p) {
            for (const alt of p.alt_numbers) {
              if (alt === "EP" && epPadNumber) highlighted.add(epPadNumber);
              else highlighted.add(alt);
            }
          }
        }
      }
    }
    return { padToPinMap: map, highlightedPads: highlighted };
  }, [pins, selectedPinNumber, epPadNumber]);

  function handlePinSelect(pinNumber: string) {
    dispatch({
      type: "SELECT_PIN",
      pinNumber: selectedPinNumber === pinNumber ? null : pinNumber,
    });
  }

  function handlePadSelect(padNumber: string) {
    const primary = padToPinMap.get(padNumber) ?? padNumber;
    dispatch({
      type: "SELECT_PIN",
      pinNumber: selectedPinNumber === primary ? null : primary,
    });
  }

  async function handlePackageSwitch(packageName: string) {
    const candidate = candidates.find((c) => c.name === packageName);
    if (!candidate || switchingPackage) return;
    setSwitchingPackage(true);
    try {
      const token = await acquireToken();
      if (!token) return;
      const res = await fetchWithLicense(
        `${apiBase()}/api/select-package`,
        token,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: jobId, package: candidate }),
        },
      );
      const data = await res.json();
      dispatch({
        type: "SWITCH_PACKAGE",
        datasheet: data.datasheet,
        match: data.match,
        pins: data.pins,
      });
    } catch (err) {
      dispatch({
        type: "ERROR",
        message: err instanceof Error ? err.message : "Package switch failed",
      });
    } finally {
      setSwitchingPackage(false);
    }
  }

  async function handleGenerate() {
    dispatch({ type: "START_GENERATE" });
    try {
      const token = await acquireToken();
      if (!token) return;
      const body: Record<string, unknown> = { job_id: jobId, pins };
      if (detectedProject) body.project_dir = detectedProject.dir;

      const res = await fetchWithLicense(`${apiBase()}/api/finalize`, token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Server error (${res.status})`);
      const data = await res.json();
      dispatch({
        type: "GENERATED",
        files: data.files,
        model: data.model || null,
        imported: data.imported || false,
      });
    } catch (err) {
      dispatch({
        type: "ERROR",
        message: err instanceof Error ? err.message : "Generation failed",
      });
    }
  }

  async function handleDownload() {
    setDownloading(true);
    try {
      const zip = new JSZip();
      const folderName = partNumber || "schemagic-output";
      const folder = zip.folder(folderName)!;
      await Promise.all(
        files.map(async (f) => {
          const res = await fetch(
            `${apiBase()}/api/download/${jobId}/${f.filename}`,
          );
          const blob = await res.blob();
          folder.file(f.filename, blob);
        }),
      );
      const zipBlob = await zip.generateAsync({ type: "blob" });
      const url = URL.createObjectURL(zipBlob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${folderName}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }

  // Auto-minimize on successful import. Uses a ref (not state) so setting
  // the "already scheduled" flag doesn't re-run the effect and clear the timer
  // before it fires.
  const wasImported = Boolean(detectedProject && files.length > 0);
  useEffect(() => {
    if (step !== "DONE" || !wasImported || minimizedRef.current) return;
    minimizedRef.current = true;
    const timer = setTimeout(minimizeTauriWindow, 1500);
    return () => clearTimeout(timer);
  }, [step, wasImported]);

  const isGenerating = step === "GENERATING";
  const isDone = step === "DONE";

  // No pipeline data yet (direct navigation before COMPLETE)
  if (!datasheet && pins.length === 0 && !isDone) {
    return (
      <AppShell header="withBack" backHref="/wizard/idle">
        <div className="flex-1 flex items-center justify-center px-12 py-24">
          <TerminalLine>
            <span className="animate-pulse">loading</span>
          </TerminalLine>
        </div>
      </AppShell>
    );
  }

  const backHref =
    candidates.length > 1 ? "/wizard/package-select" : "/wizard/idle";

  const pkgLabel = datasheet?.package
    ? `${datasheet.package.name} (${datasheet.package.pin_count} pins)`
    : "unknown";
  const footprintLabel = match?.footprint_name
    ? `${match.footprint_lib}/${match.footprint_name}`
    : "no match";
  const symbolLabel = match?.symbol_name
    ? `${match.symbol_lib}/${match.symbol_name}`
    : "synthetic";

  return (
    <AppShell header="withBack" backHref={backHref}>
      <div className="flex-1 px-12 py-24">
        <div className="mx-auto max-w-6xl flex flex-col gap-12">
          <div className="flex flex-col gap-6">
            <TerminalLine>wizard/pin-review</TerminalLine>
            <h1 className="font-sans text-h1 text-text-primary">
              {isDone ? "Done" : "Review pins"}
            </h1>
            <p className="font-sans text-body text-text-secondary">
              {isDone
                ? wasImported
                  ? `Imported to ${detectedProject?.name}. Press A in eeschema to place the symbol.`
                  : "Files ready to download."
                : "Double-check pin numbers, names, and types before writing to KiCad."}
            </p>
          </div>

          {isDone ? (
            <DoneView
              files={files}
              partNumber={partNumber}
              model={model}
              wasImported={wasImported}
              downloading={downloading}
              onDownload={handleDownload}
              onReset={() => {
                dispatch({ type: "RESET" });
                router.push("/wizard/idle");
              }}
            />
          ) : (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)] gap-12">
                <Card header={<span>Meta</span>}>
                  <CardRow label="Part" value={partNumber || "—"} />
                  <CardRow
                    label="Package"
                    value={
                      candidates.length > 1 && datasheet?.package ? (
                        <select
                          value={datasheet.package.name}
                          onChange={(e) => handlePackageSwitch(e.target.value)}
                          disabled={switchingPackage}
                          className="bg-surface border border-border text-body px-2 py-1 text-text-primary focus:outline-none focus:border-accent"
                        >
                          {candidates.map((c) => (
                            <option key={c.name} value={c.name}>
                              {c.name} ({c.pin_count} pins)
                            </option>
                          ))}
                        </select>
                      ) : (
                        pkgLabel
                      )
                    }
                  />
                  <CardRow label="Pin count" value={pins.length} />
                  <CardRow label="Symbol" value={symbolLabel} />
                  <CardRow label="Footprint" value={footprintLabel} />
                </Card>

                {loading ? (
                  <div className="bg-surface-raised border border-border min-h-[320px] animate-pulse" />
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <SymbolViewer
                      data={effectiveSymbolData}
                      selectedPinNumber={selectedPinNumber}
                      onPinClick={handlePinSelect}
                    />
                    <FootprintViewer
                      data={footprintData}
                      highlightedPads={highlightedPads}
                      onPadClick={handlePadSelect}
                    />
                  </div>
                )}
              </div>

              <PinEditPanel />

              <div>
                <button
                  onClick={() => setShowTable((s) => !s)}
                  className="font-mono text-mono-label uppercase tracking-wider text-text-secondary hover:text-text-primary transition-colors"
                >
                  {showTable ? "Hide" : "Show"} all pins ({pins.length})
                </button>
                {showTable && (
                  <div className="mt-3">
                    <PinReviewTable />
                  </div>
                )}
              </div>

              <div className="flex items-center gap-6">
                <Button onClick={handleGenerate} disabled={isGenerating || pins.length === 0}>
                  {isGenerating
                    ? "Generating..."
                    : detectedProject
                      ? `Import to ${detectedProject.name}`
                      : "Generate files"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => router.push("/wizard/idle")}
                >
                  Cancel
                </Button>
              </div>

              {error && step !== "ERROR" && (
                <p className="font-mono text-mono-xs text-accent">{error}</p>
              )}
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}

interface DoneViewProps {
  files: { filename: string; size_bytes: number }[];
  partNumber: string;
  model: { ref: string; inferred: boolean } | null;
  wasImported: boolean;
  downloading: boolean;
  onDownload: () => void;
  onReset: () => void;
}

function DoneView({
  files,
  partNumber,
  model,
  wasImported,
  downloading,
  onDownload,
  onReset,
}: DoneViewProps) {
  return (
    <>
      <Card header={<span>{wasImported ? "Imported files" : "Generated files"}</span>}>
        {files.map((f) => (
          <CardRow
            key={f.filename}
            label={
              <span className="font-mono text-body text-text-primary">
                {f.filename}
              </span>
            }
            value={
              <span className="font-mono text-mono-label text-text-secondary">
                {formatBytes(f.size_bytes)}
              </span>
            }
          />
        ))}
      </Card>

      <Card header={<span>3D model</span>}>
        {model?.ref ? (
          <>
            <CardRow
              label="Reference"
              value={
                <span className="font-mono text-body text-text-primary">
                  {model.ref}
                </span>
              }
            />
            <CardRow
              label="Source"
              value={model.inferred ? "inferred from footprint" : "KiCad library"}
            />
          </>
        ) : (
          <CardRow
            label="Reference"
            value={
              <span className="font-mono text-mono-label text-text-secondary">
                none found
              </span>
            }
          />
        )}
      </Card>

      <div className="flex items-center gap-6">
        {!wasImported && (
          <Button onClick={onDownload} disabled={downloading}>
            {downloading ? "Preparing..." : `Download ${partNumber || "files"}.zip`}
          </Button>
        )}
        <Button variant="secondary" onClick={onReset}>
          Generate another
        </Button>
      </div>
    </>
  );
}

export default function WizardPinReviewPage() {
  return (
    <AuthGate>
      <WizardPinReview />
    </AuthGate>
  );
}
