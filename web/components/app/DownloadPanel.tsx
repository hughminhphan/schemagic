"use client";

import { useEffect, useState } from "react";
import JSZip from "jszip";
import { useWizard, useWizardDispatch } from "./WizardProvider";
import { apiBase } from "@/lib/api-base";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

declare global {
  interface Window {
    __TAURI__?: {
      core?: {
        invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
      };
    };
  }
}

function minimizeWindow() {
  try {
    window.__TAURI__?.core?.invoke("plugin:window|minimize", {
      label: "main",
    });
  } catch {
    // Not in Tauri or permission missing - ignore
  }
}

export default function DownloadPanel() {
  const { files, jobId, partNumber, datasheet, model, detectedProject } =
    useWizard();
  const dispatch = useWizardDispatch();
  const [downloading, setDownloading] = useState(false);
  const [imported, setImported] = useState(false);

  // Detect if this was a direct import (files were saved to project, not temp)
  const wasImported = detectedProject && files.length > 0;

  // Auto-minimize after successful import
  useEffect(() => {
    if (wasImported && !imported) {
      setImported(true);
      const timer = setTimeout(() => {
        minimizeWindow();
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [wasImported, imported]);

  if (files.length === 0) return null;

  const folderName = partNumber || "schemagic-output";

  async function handleDownload() {
    setDownloading(true);
    try {
      const zip = new JSZip();
      const folder = zip.folder(folderName)!;

      await Promise.all(
        files.map(async (f) => {
          const res = await fetch(
            `${apiBase()}/api/download/${jobId}/${f.filename}`
          );
          const blob = await res.blob();
          folder.file(f.filename, blob);
        })
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

  // Import success view
  if (wasImported) {
    return (
      <div className="mt-[48px]">
        <div className="border border-green-500/30 bg-green-500/5 p-[24px] mb-[24px]">
          <p className="font-mono text-sm text-green-400 mb-[8px]">
            Imported to {detectedProject.name}
          </p>
          <p className="text-xs text-text-secondary">
            {files.length} file{files.length !== 1 ? "s" : ""} saved. Press A in
            eeschema to add the symbol.
          </p>
        </div>

        {/* 3D Model info */}
        {model?.ref && (
          <div className="border border-border bg-surface-raised p-[16px] mb-[24px]">
            <p className="font-mono text-xs text-text-secondary uppercase tracking-wider mb-[8px]">
              3D Model
            </p>
            <p className="font-mono text-sm text-text-primary">{model.ref}</p>
            <p className="text-xs text-text-secondary mt-[4px]">
              {model.inferred
                ? "Inferred from footprint naming convention. Verify in KiCad's 3D viewer."
                : "Resolves automatically from your KiCad installation."}
            </p>
          </div>
        )}

        <button
          onClick={() => dispatch({ type: "RESET" })}
          className="border border-border h-[48px] px-[24px] text-sm text-text-secondary hover:text-text-primary hover:border-accent transition-colors"
        >
          Generate another
        </button>
      </div>
    );
  }

  // Download fallback view (no project detected)
  return (
    <div className="mt-[48px]">
      <p className="font-mono text-xs text-text-secondary uppercase tracking-wider mb-[12px]">
        Generated files
      </p>

      <div className="space-y-[1px] bg-border mb-[24px]">
        {files.map((f, i) => (
          <div
            key={i}
            className="flex items-center justify-between bg-surface h-[48px] px-[24px]"
          >
            <span className="font-mono text-sm">{f.filename}</span>
            <span className="text-xs text-text-secondary">
              {formatBytes(f.size_bytes)}
            </span>
          </div>
        ))}
      </div>

      <p className="text-xs text-text-secondary mb-[16px]">
        Open a KiCad project to enable one-click import.
      </p>

      <div className="flex gap-[24px]">
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="bg-accent text-background h-[48px] px-[24px] text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {downloading ? "Preparing..." : "Download files"}
        </button>
        <button
          onClick={() => dispatch({ type: "RESET" })}
          className="border border-border h-[48px] px-[24px] text-sm text-text-secondary hover:text-text-primary hover:border-accent transition-colors"
        >
          Generate another
        </button>
      </div>

      {/* 3D Model info */}
      <div className="mt-[24px] border border-border bg-surface-raised p-[16px]">
        <p className="font-mono text-xs text-text-secondary uppercase tracking-wider mb-[8px]">
          3D Model
        </p>
        {model?.ref ? (
          <>
            <p className="font-mono text-sm text-text-primary">{model.ref}</p>
            <p className="text-xs text-text-secondary mt-[4px]">
              {model.inferred
                ? "Inferred from footprint naming convention. Verify in KiCad's 3D viewer."
                : "Resolves automatically from your KiCad installation."}
            </p>
          </>
        ) : (
          <p className="text-xs text-yellow-400">
            No 3D model reference found. Footprint will appear flat in KiCad's
            3D viewer.
          </p>
        )}
      </div>

      {datasheet && (
        <p className="mt-[24px] font-mono text-xs text-text-secondary">
          {datasheet.part_number}
          {datasheet.manufacturer ? ` / ${datasheet.manufacturer}` : ""}
          {datasheet.package ? ` / ${datasheet.package.name}` : ""}
        </p>
      )}
    </div>
  );
}
