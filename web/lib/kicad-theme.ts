/** KiCad color conventions adapted for dark background rendering. */

export const SYMBOL_THEME = {
  background: "#0a0a0a",
  bodyStroke: "#CC3333",
  bodyFill: "#1A1A0A",
  pinLine: "#CC3333",
  pinName: "#00CCCC",
  pinNumber: "#CC4444",
  selected: "#FF2D78",
  selectedBg: "rgba(255,45,120,0.2)",
  defaultLineWidth: 0.152,  // 6 mil
  pinFontSize: 1.27,        // 50 mil
  pinNameOffset: 0.508,     // 20 mil
  decorSize: 0.635,         // 25 mil (externalPinDecoSize)
} as const;

export const FOOTPRINT_THEME = {
  background: "#001023",
  layers: {
    "F.Cu": "#C83434",
    "B.Cu": "#4D7FC4",
    "F.SilkS": "#F2EDA1",
    "B.SilkS": "#E8B2A7",
    "F.CrtYd": "#FF26E2",
    "B.CrtYd": "#26E9FF",
    "F.Fab": "#AFAFAF",
    "B.Fab": "#585D84",
  } as Record<string, string>,
  padSMD: "rgba(200, 52, 52, 0.6)",
  padSMDStroke: "#C83434",
  padTH: "rgba(200, 52, 52, 0.5)",
  padTHStroke: "#C83434",
  drillPTH: "#C2C200",
  drillNPTH: "#1AC4D2",
  defaultLineWidth: 0.152,
  fallbackColor: "#555",
} as const;
