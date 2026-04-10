"use client";

import { useState } from "react";
import type { GraphicItem, LibraryItemPayload, SymbolPin } from "@/lib/kicad-render-types";
import { SYMBOL_THEME } from "@/lib/kicad-theme";

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
  const sweepFlag = cross > 0 ? 0 : 1;

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

function KiCadGraphic({ item }: { item: GraphicItem }) {
  const strokeColor = SYMBOL_THEME.bodyStroke;
  const sw = item.stroke_width || SYMBOL_THEME.defaultLineWidth;
  const fillColor =
    item.fill === "background" ? SYMBOL_THEME.bodyFill :
    item.fill === "outline" ? strokeColor :
    "none";

  switch (item.type) {
    case "rectangle": {
      if (!item.start || !item.end) return null;
      const x = Math.min(item.start[0], item.end[0]);
      const y = Math.min(item.start[1], item.end[1]);
      const w = Math.abs(item.end[0] - item.start[0]);
      const h = Math.abs(item.end[1] - item.start[1]);
      return (
        <rect
          x={x} y={y} width={w} height={h}
          stroke={strokeColor} strokeWidth={sw} fill={fillColor}
        />
      );
    }
    case "polyline": {
      if (!item.pts || item.pts.length === 0) return null;
      const points = item.pts.map(p => `${p[0]},${p[1]}`).join(" ");
      return (
        <polyline
          points={points}
          stroke={strokeColor} strokeWidth={sw} fill={fillColor}
          strokeLinejoin="round"
        />
      );
    }
    case "arc": {
      if (!item.start || !item.mid || !item.end) return null;
      const d = arcPath(item.start, item.mid, item.end);
      return (
        <path d={d} stroke={strokeColor} strokeWidth={sw} fill={fillColor} />
      );
    }
    case "circle": {
      if (!item.center) return null;
      return (
        <circle
          cx={item.center[0]} cy={item.center[1]} r={item.radius || 0}
          stroke={strokeColor} strokeWidth={sw} fill={fillColor}
        />
      );
    }
    case "bezier": {
      if (!item.pts || item.pts.length < 4) return null;
      const [p0, p1, p2, p3] = item.pts;
      const d = `M ${p0[0]} ${p0[1]} C ${p1[0]} ${p1[1]}, ${p2[0]} ${p2[1]}, ${p3[0]} ${p3[1]}`;
      return (
        <path d={d} stroke={strokeColor} strokeWidth={sw} fill={fillColor} />
      );
    }
    case "text": {
      if (!item.at) return null;
      const fs = item.font_size || SYMBOL_THEME.pinFontSize;
      return (
        <g transform={`translate(${item.at[0]}, ${item.at[1]})`}>
          <text
            transform={`scale(1, -1)${item.angle ? ` rotate(${-item.angle})` : ""}`}
            textAnchor="middle"
            fill={strokeColor}
            fontSize={fs}
            fontFamily="Inter, sans-serif"
          >
            {item.text}
          </text>
        </g>
      );
    }
    default:
      return null;
  }
}

/** Render pin decorator shapes per KiCad spec. */
function PinDecorator({
  pin, color,
}: {
  pin: SymbolPin;
  color: string;
}) {
  const angleRad = (pin.angle * Math.PI) / 180;
  const dx = Math.cos(angleRad);
  const dy = Math.sin(angleRad);
  // Perpendicular (clockwise 90)
  const px = -dy;
  const py = dx;
  const tipX = pin.at[0] + pin.length * dx;
  const tipY = pin.at[1] + pin.length * dy;
  const ds = SYMBOL_THEME.decorSize;
  const sw = SYMBOL_THEME.defaultLineWidth;

  switch (pin.shape) {
    case "inverted": {
      // Circle at pin tip, radius = ds/2
      const r = ds / 2;
      const cx = tipX - r * dx;
      const cy = tipY - r * dy;
      return (
        <circle
          cx={cx} cy={cy} r={r}
          stroke={color} strokeWidth={sw} fill="none"
        />
      );
    }
    case "clock": {
      // Triangle inside body at pin entry (at) pointing inward
      const bx = pin.at[0];
      const by = pin.at[1];
      return (
        <polygon
          points={`${bx + ds * px},${by + ds * py} ${bx - ds * dx},${by - ds * dy} ${bx - ds * px},${by - ds * py}`}
          stroke={color} strokeWidth={sw} fill="none"
        />
      );
    }
    case "inverted_clock": {
      // Bubble at tip + clock triangle at body
      const r = ds / 2;
      const bcx = tipX - r * dx;
      const bcy = tipY - r * dy;
      const bx = pin.at[0];
      const by = pin.at[1];
      return (
        <>
          <circle
            cx={bcx} cy={bcy} r={r}
            stroke={color} strokeWidth={sw} fill="none"
          />
          <polygon
            points={`${bx + ds * px},${by + ds * py} ${bx - ds * dx},${by - ds * dy} ${bx - ds * px},${by - ds * py}`}
            stroke={color} strokeWidth={sw} fill="none"
          />
        </>
      );
    }
    case "input_low": {
      // L-shaped flag at tip: line from tip perpendicular, then diagonal back
      const flagEnd = [tipX + ds * px, tipY + ds * py];
      const diagEnd = [tipX - ds * dx, tipY - ds * dy];
      return (
        <>
          <line x1={tipX} y1={tipY} x2={flagEnd[0]} y2={flagEnd[1]}
            stroke={color} strokeWidth={sw} />
          <line x1={flagEnd[0]} y1={flagEnd[1]} x2={diagEnd[0]} y2={diagEnd[1]}
            stroke={color} strokeWidth={sw} />
        </>
      );
    }
    case "output_low": {
      // Angled line from tip
      const flagEnd = [tipX + ds * px, tipY + ds * py];
      const diagEnd = [tipX - ds * dx, tipY - ds * dy];
      return (
        <polyline
          points={`${flagEnd[0]},${flagEnd[1]} ${tipX},${tipY} ${diagEnd[0]},${diagEnd[1]}`}
          stroke={color} strokeWidth={sw} fill="none"
        />
      );
    }
    case "falling_edge_clock": {
      // Triangle pointing outward at tip
      return (
        <polygon
          points={`${tipX + ds * px},${tipY + ds * py} ${tipX + ds * dx},${tipY + ds * dy} ${tipX - ds * px},${tipY - ds * py}`}
          stroke={color} strokeWidth={sw} fill="none"
        />
      );
    }
    case "non_logic": {
      // X cross at tip
      const half = ds * 0.7;
      return (
        <>
          <line
            x1={tipX - half * (dx + px)} y1={tipY - half * (dy + py)}
            x2={tipX + half * (dx + px)} y2={tipY + half * (dy + py)}
            stroke={color} strokeWidth={sw} />
          <line
            x1={tipX - half * (dx - px)} y1={tipY - half * (dy - py)}
            x2={tipX + half * (dx - px)} y2={tipY + half * (dy - py)}
            stroke={color} strokeWidth={sw} />
        </>
      );
    }
    default:
      return null;
  }
}

function PinElement({
  pin,
  isSelected,
  onClick,
  pinNamesOffset,
  pinNamesHide,
  pinNumbersHide,
}: {
  pin: SymbolPin;
  isSelected: boolean;
  onClick: () => void;
  pinNamesOffset: number;
  pinNamesHide: boolean;
  pinNumbersHide: boolean;
}) {
  const color = isSelected ? SYMBOL_THEME.selected : SYMBOL_THEME.pinLine;
  const nameColor = isSelected ? SYMBOL_THEME.selected : SYMBOL_THEME.pinName;
  const numColor = isSelected ? SYMBOL_THEME.selected : SYMBOL_THEME.pinNumber;
  const sw = isSelected ? 0.35 : SYMBOL_THEME.defaultLineWidth;

  const angleRad = (pin.angle * Math.PI) / 180;
  const dx = Math.cos(angleRad);
  const dy = Math.sin(angleRad);
  const tipX = pin.at[0] + pin.length * dx;
  const tipY = pin.at[1] + pin.length * dy;

  // For inverted/inverted_clock, shorten the pin line by one decorator size
  const hasInversion = pin.shape === "inverted" || pin.shape === "inverted_clock";
  const ds = SYMBOL_THEME.decorSize;
  const lineEndX = hasInversion ? tipX - ds * dx : tipX;
  const lineEndY = hasInversion ? tipY - ds * dy : tipY;

  // Pin midpoint for number placement
  const midX = (pin.at[0] + tipX) / 2;
  const midY = (pin.at[1] + tipY) / 2;

  // Pin name: inside body, offset from at point in the opposite direction of the pin
  // bodyDir is the direction from at toward the body interior (opposite to pin direction)
  const bodyDirX = -dx;
  const bodyDirY = -dy;
  const nameX = pin.at[0] + bodyDirX * pinNamesOffset;
  const nameY = pin.at[1] + bodyDirY * pinNamesOffset;

  // Perpendicular offset for pin number (above the line)
  const perpX = -dy;
  const perpY = dx;
  const numOffsetDist = 0.3;

  // Determine text anchors and rotation based on pin orientation
  const isHorizontal = pin.angle === 0 || pin.angle === 180;
  const nameAnchor = pin.angle === 0 ? "end" :
                     pin.angle === 180 ? "start" :
                     "middle";

  return (
    <g onClick={onClick} className="cursor-pointer">
      {/* Pin line */}
      <line
        x1={pin.at[0]} y1={pin.at[1]}
        x2={lineEndX} y2={lineEndY}
        stroke={color} strokeWidth={sw}
      />

      {/* Pin decorator */}
      <PinDecorator pin={pin} color={color} />

      {/* Hit target at tip */}
      <circle
        cx={tipX} cy={tipY} r={0.6}
        fill={isSelected ? SYMBOL_THEME.selectedBg : "transparent"}
        stroke="none"
      />

      {/* Pin number (near midpoint, offset perpendicular) */}
      {!pinNumbersHide && (
        <g transform={`translate(${midX}, ${midY})`}>
          <text
            transform={`scale(1, -1)${!isHorizontal ? " rotate(-90)" : ""}`}
            textAnchor="middle"
            dy={isHorizontal ? -numOffsetDist : 0}
            dx={!isHorizontal ? numOffsetDist : 0}
            fill={numColor}
            fontSize={SYMBOL_THEME.pinFontSize * 0.8}
            fontFamily="Inter, sans-serif"
            opacity={0.8}
          >
            {pin.number}
          </text>
        </g>
      )}

      {/* Pin name (inside body) */}
      {!pinNamesHide && pin.name && pin.name !== "~" && (
        <g transform={`translate(${nameX}, ${nameY})`}>
          <text
            transform={`scale(1, -1)${!isHorizontal ? " rotate(-90)" : ""}`}
            textAnchor={nameAnchor}
            fill={nameColor}
            fontSize={SYMBOL_THEME.pinFontSize}
            fontFamily="Inter, sans-serif"
          >
            {pin.name}
          </text>
        </g>
      )}
    </g>
  );
}

export default function SymbolViewer({
  data,
  selectedPinNumber,
  onPinClick,
}: {
  data: LibraryItemPayload | null;
  selectedPinNumber: string | null;
  onPinClick: (pinNumber: string) => void;
}) {
  const [selectedUnit, setSelectedUnit] = useState(1);

  if (!data || !data.bounding_box) {
    return (
      <div className="border border-border bg-surface-raised flex items-center justify-center h-[400px]">
        <p className="font-mono text-xs text-text-secondary">No symbol preview</p>
      </div>
    );
  }

  const bb = data.bounding_box;
  const viewBox = `${bb.x} ${-(bb.y + bb.h)} ${bb.w} ${bb.h}`;
  const isSynthetic = !data.found;
  const unitCount = data.unit_count || 1;
  const pinNamesOffset = data.pin_names_offset ?? SYMBOL_THEME.pinNameOffset;
  const pinNamesHide = data.pin_names_hide ?? false;
  const pinNumbersHide = data.pin_numbers_hide ?? false;

  // Filter by unit for multi-unit symbols
  const visibleGraphics = unitCount > 1
    ? data.graphics.filter(g => !g.unit || g.unit === selectedUnit)
    : data.graphics;
  const visiblePins = unitCount > 1
    ? data.pins.filter(p => !p.unit || p.unit === selectedUnit)
    : data.pins;

  return (
    <div className="border border-border" style={{ backgroundColor: SYMBOL_THEME.background }}>
      <div className="px-[16px] py-[8px] flex items-center gap-[8px] border-b border-border">
        <p className="font-mono text-xs text-text-secondary uppercase tracking-wider">
          Symbol
        </p>
        {isSynthetic && (
          <span className="font-mono text-[10px] text-accent/60 uppercase">
            generated
          </span>
        )}
        {unitCount > 1 && (
          <select
            value={selectedUnit}
            onChange={(e) => setSelectedUnit(Number(e.target.value))}
            className="ml-auto font-mono text-xs bg-surface text-text-primary border border-border px-1 py-0.5"
          >
            {Array.from({ length: unitCount }, (_, i) => (
              <option key={i + 1} value={i + 1}>Unit {String.fromCharCode(64 + i + 1)}</option>
            ))}
          </select>
        )}
      </div>
      <svg
        viewBox={viewBox}
        className="w-full"
        style={{ height: 400 }}
        preserveAspectRatio="xMidYMid meet"
      >
        <g transform="scale(1, -1)">
          {visibleGraphics.map((g, i) => (
            <KiCadGraphic key={i} item={g} />
          ))}
          {visiblePins.map((pin) => (
            <PinElement
              key={pin.number}
              pin={pin}
              isSelected={selectedPinNumber === pin.number}
              onClick={() => onPinClick(pin.number)}
              pinNamesOffset={pinNamesOffset}
              pinNamesHide={pinNamesHide}
              pinNumbersHide={pinNumbersHide}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}
