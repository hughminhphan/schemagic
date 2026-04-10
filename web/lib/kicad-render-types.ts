export interface GraphicItem {
  type: string;
  layer?: string;
  start?: [number, number];
  end?: [number, number];
  mid?: [number, number];
  pts?: [number, number][];
  center?: [number, number];
  radius?: number;
  at?: [number, number];
  angle?: number;
  text?: string;
  stroke_width?: number;
  fill?: string;
  font_size?: number;
  unit?: number;
}

export interface SymbolPin {
  number: string;
  name: string;
  pin_type: string;
  shape: string;
  at: [number, number];
  angle: number;
  length: number;
  unit?: number;
}

export interface FootprintPad {
  number: string;
  shape: string;
  at: [number, number];
  size: [number, number];
  angle: number;
  roundrect_rratio: number;
  pad_type?: string;
  drill?: number[];
}

export interface BoundingBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface LibraryItemPayload {
  kind: string;
  found: boolean;
  bounding_box: BoundingBox | null;
  graphics: GraphicItem[];
  pins: SymbolPin[];
  pads: FootprintPad[];
  unit_count?: number;
  pin_names_offset?: number;
  pin_names_hide?: boolean;
  pin_numbers_hide?: boolean;
}
