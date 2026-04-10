"use client";

import type { FootprintPad, GraphicItem, LibraryItemPayload } from "@/lib/kicad-render-types";
import { FOOTPRINT_THEME } from "@/lib/kicad-theme";

function arcPath(
  start: [number, number],
  mid: [number, number],
  end: [number, number],
): string {
  const [x1, y1] = start;
  const [xm, ym] = mid;
  const [x2, y2] = end;

  const ax = x1, ay = y1;
  const bx = xm, by = ym;
  const cx = x2, cy = y2;

  const D = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
  if (Math.abs(D) < 1e-10) {
    return `M ${x1} ${y1} L ${x2} ${y2}`;
  }

  const ux =
    ((ax * ax + ay * ay) * (by - cy) +
      (bx * bx + by * by) * (cy - ay) +
      (cx * cx + cy * cy) * (ay - by)) / D;
  const uy =
    ((ax * ax + ay * ay) * (cx - bx) +
      (bx * bx + by * by) * (ax - cx) +
      (cx * cx + cy * cy) * (bx - ax)) / D;

  const r = Math.sqrt((ax - ux) ** 2 + (ay - uy) ** 2);
  const cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
  const sweepFlag = cross > 0 ? 1 : 0;

  const angleStart = Math.atan2(ay - uy, ax - ux);
  const angleMid = Math.atan2(ym - uy, xm - ux);
  const angleEnd = Math.atan2(y2 - uy, x2 - ux);

  let startToEnd = angleEnd - angleStart;
  let startToMid = angleMid - angleStart;

  if (sweepFlag === 1) {
    if (startToEnd < 0) startToEnd += 2 * Math.PI;
    if (startToMid < 0) startToMid += 2 * Math.PI;
  } else {
    if (startToEnd > 0) startToEnd -= 2 * Math.PI;
    if (startToMid > 0) startToMid -= 2 * Math.PI;
  }

  const largeArc = Math.abs(startToEnd) > Math.PI ? 1 : 0;

  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} ${sweepFlag} ${x2} ${y2}`;
}

function FpGraphic({ item }: { item: GraphicItem }) {
  const color = FOOTPRINT_THEME.layers[item.layer || ""] || FOOTPRINT_THEME.fallbackColor;
  const sw = item.stroke_width || FOOTPRINT_THEME.defaultLineWidth;

  switch (item.type) {
    case "line": {
      if (!item.start || !item.end) return null;
      return (
        <line
          x1={item.start[0]} y1={item.start[1]}
          x2={item.end[0]} y2={item.end[1]}
          stroke={color} strokeWidth={sw}
        />
      );
    }
    case "rectangle": {
      if (!item.start || !item.end) return null;
      const x = Math.min(item.start[0], item.end[0]);
      const y = Math.min(item.start[1], item.end[1]);
      const w = Math.abs(item.end[0] - item.start[0]);
      const h = Math.abs(item.end[1] - item.start[1]);
      const fillVal = item.fill === "solid" || item.fill === "outline" ? color : "none";
      return (
        <rect
          x={x} y={y} width={w} height={h}
          stroke={color} strokeWidth={sw}
          fill={fillVal} fillOpacity={item.fill === "solid" ? 0.3 : 0}
        />
      );
    }
    case "arc": {
      if (!item.start || !item.mid || !item.end) return null;
      const d = arcPath(item.start, item.mid, item.end);
      return <path d={d} stroke={color} strokeWidth={sw} fill="none" />;
    }
    case "circle": {
      if (!item.center) return null;
      const fillVal = item.fill === "solid" || item.fill === "outline" ? color : "none";
      return (
        <circle
          cx={item.center[0]} cy={item.center[1]} r={item.radius || 0}
          stroke={color} strokeWidth={sw}
          fill={fillVal} fillOpacity={item.fill === "solid" ? 0.3 : 0}
        />
      );
    }
    case "poly": {
      if (!item.pts || item.pts.length === 0) return null;
      const points = item.pts.map(p => `${p[0]},${p[1]}`).join(" ");
      const fillVal = item.fill === "solid" || item.fill === "outline" ? color : "none";
      return (
        <polygon
          points={points}
          stroke={color} strokeWidth={sw}
          fill={fillVal} fillOpacity={0.3}
        />
      );
    }
    case "text": {
      if (!item.at) return null;
      const fs = item.font_size || 1.0;
      const rotation = item.angle ? `rotate(${item.angle} ${item.at[0]} ${item.at[1]})` : undefined;
      return (
        <text
          x={item.at[0]} y={item.at[1]}
          fill={color} fontSize={fs}
          textAnchor="middle"
          fontFamily="Inter, sans-serif"
          transform={rotation}
        >
          {item.text}
        </text>
      );
    }
    default:
      return null;
  }
}

function PadElement({
  pad,
  isSelected,
  onClick,
}: {
  pad: FootprintPad;
  isSelected: boolean;
  onClick: () => void;
}) {
  const isThruHole = pad.pad_type === "thru_hole";
  const isNPTH = pad.pad_type === "np_thru_hole";

  const fill = isSelected ? "#FF2D78" :
               isNPTH ? "none" :
               isThruHole ? FOOTPRINT_THEME.padTH :
               FOOTPRINT_THEME.padSMD;
  const stroke = isSelected ? "#FF2D78" :
                 isNPTH ? FOOTPRINT_THEME.drillNPTH :
                 isThruHole ? FOOTPRINT_THEME.padTHStroke :
                 FOOTPRINT_THEME.padSMDStroke;
  const sw = 0.05;

  const [cx, cy] = pad.at;
  const [w, h] = pad.size;
  const x = cx - w / 2;
  const y = cy - h / 2;

  const transform = pad.angle ? `rotate(${pad.angle} ${cx} ${cy})` : undefined;

  let shape: React.ReactNode;

  if (isNPTH) {
    // Non-plated through-hole: just the drill hole
    const drillR = pad.drill && pad.drill.length > 0 ? pad.drill[0] / 2 : Math.min(w, h) / 2;
    shape = (
      <circle cx={cx} cy={cy} r={drillR}
        fill={FOOTPRINT_THEME.background} stroke={FOOTPRINT_THEME.drillNPTH} strokeWidth={sw * 2} />
    );
  } else {
    switch (pad.shape) {
      case "circle":
        shape = (
          <circle cx={cx} cy={cy} r={w / 2} fill={fill} stroke={stroke} strokeWidth={sw} />
        );
        break;
      case "oval":
        shape = (
          <rect
            x={x} y={y} width={w} height={h}
            rx={Math.min(w, h) / 2} ry={Math.min(w, h) / 2}
            fill={fill} stroke={stroke} strokeWidth={sw}
          />
        );
        break;
      case "roundrect": {
        const rr = pad.roundrect_rratio || 0.25;
        const rx = rr * Math.min(w, h);
        shape = (
          <rect
            x={x} y={y} width={w} height={h}
            rx={rx} ry={rx}
            fill={fill} stroke={stroke} strokeWidth={sw}
          />
        );
        break;
      }
      default: // rect, custom
        shape = (
          <rect
            x={x} y={y} width={w} height={h}
            fill={fill} stroke={stroke} strokeWidth={sw}
          />
        );
    }
  }

  // Drill hole overlay for through-hole pads
  const drillHole = isThruHole && pad.drill && pad.drill.length > 0 ? (
    <circle
      cx={cx} cy={cy}
      r={pad.drill[0] / 2}
      fill={FOOTPRINT_THEME.background}
      stroke={FOOTPRINT_THEME.drillPTH}
      strokeWidth={sw * 2}
    />
  ) : null;

  return (
    <g onClick={onClick} className="cursor-pointer" transform={transform}>
      {shape}
      {drillHole}
      {/* Pad number label */}
      {pad.number && !isNPTH && (
        <text
          x={cx} y={cy}
          textAnchor="middle"
          dominantBaseline="central"
          fill={isSelected ? "#fff" : "#ddd"}
          fontSize={Math.min(w, h) * 0.5}
          fontFamily="Inter, sans-serif"
        >
          {pad.number}
        </text>
      )}
    </g>
  );
}

export default function FootprintViewer({
  data,
  highlightedPads,
  onPadClick,
}: {
  data: LibraryItemPayload | null;
  highlightedPads: Set<string>;
  onPadClick: (padNumber: string) => void;
}) {
  if (!data || !data.bounding_box) {
    return (
      <div className="border border-border bg-surface-raised flex items-center justify-center h-[400px]">
        <p className="font-mono text-xs text-text-secondary">No footprint preview</p>
      </div>
    );
  }

  const bb = data.bounding_box;
  const viewBox = `${bb.x} ${bb.y} ${bb.w} ${bb.h}`;

  return (
    <div className="border border-border" style={{ backgroundColor: FOOTPRINT_THEME.background }}>
      <p className="px-[16px] py-[8px] font-mono text-xs text-text-secondary uppercase tracking-wider border-b border-border">
        Footprint
      </p>
      <svg
        viewBox={viewBox}
        className="w-full"
        style={{ height: 400 }}
        preserveAspectRatio="xMidYMid meet"
      >
        {data.graphics.map((g, i) => (
          <FpGraphic key={i} item={g} />
        ))}
        {data.pads.map((pad, i) => (
          <PadElement
            key={`${pad.number}-${i}`}
            pad={pad}
            isSelected={highlightedPads.has(pad.number)}
            onClick={() => pad.number && onPadClick(pad.number)}
          />
        ))}
      </svg>
    </div>
  );
}
