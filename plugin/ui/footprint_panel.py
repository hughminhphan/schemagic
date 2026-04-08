"""wx.Panel that renders a KiCad PCB footprint using BufferedPaintDC.

No Y-flip needed (KiCad footprint coords are Y-down, matching screen).
Draws layer graphics (silkscreen, courtyard, fab) and pads with
selection highlighting and click detection.
"""

import math

import wx


_PINK = wx.Colour(255, 45, 120)
_BG = wx.Colour(10, 10, 10)
_PAD_FILL = wx.Colour(200, 50, 50, 100)
_PAD_STROKE = wx.Colour(255, 80, 80, 150)

_LAYER_COLORS = {
    "F.SilkS": wx.Colour(204, 204, 0),
    "F.CrtYd": wx.Colour(204, 0, 204),
    "F.Fab":   wx.Colour(102, 102, 255),
    "B.SilkS": wx.Colour(102, 102, 0),
    "B.CrtYd": wx.Colour(102, 0, 102),
    "B.Fab":   wx.Colour(51, 51, 153),
}
_DEFAULT_LAYER_COLOR = wx.Colour(85, 85, 85)


class FootprintPanel(wx.Panel):
    """Renders a KiCad footprint from a RenderPayload."""

    def __init__(self, parent, size=(420, 350)):
        super().__init__(parent, size=size)
        self.SetBackgroundColour(_BG)
        self.SetMinSize(size)

        self._payload = None
        self._highlighted_pads = set()
        self.on_pad_click = None   # callback: fn(pad_number: str)

        self._scale = 1.0
        self._cx_kicad = 0.0
        self._cy_kicad = 0.0

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def set_data(self, payload):
        self._payload = payload
        self.Refresh()

    def set_highlighted_pads(self, pad_set):
        self._highlighted_pads = set(pad_set) if pad_set else set()
        self.Refresh()

    # ------------------------------------------------------------------
    # Coordinate transforms (no Y-flip)
    # ------------------------------------------------------------------

    def _compute_transform(self, W, H):
        bb = self._payload.bounding_box
        if not bb or bb.w < 0.001 or bb.h < 0.001:
            self._scale = 1.0
            self._cx_kicad = 0.0
            self._cy_kicad = 0.0
            return
        self._scale = min(W / bb.w, H / bb.h) * 0.9
        self._cx_kicad = bb.x + bb.w / 2.0
        self._cy_kicad = bb.y + bb.h / 2.0

    def _k2s(self, kx, ky):
        """KiCad footprint coords to screen coords (no Y-flip)."""
        W, H = self.GetClientSize()
        sx = W / 2.0 + (kx - self._cx_kicad) * self._scale
        sy = H / 2.0 + (ky - self._cy_kicad) * self._scale
        return int(sx), int(sy)

    def _scale_px(self, mm):
        return max(1, int(mm * self._scale))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_size(self, event):
        self.Refresh()
        event.Skip()

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(_BG))
        dc.Clear()

        if not self._payload or not self._payload.bounding_box:
            dc.SetTextForeground(wx.Colour(100, 100, 100))
            dc.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                               wx.FONTWEIGHT_NORMAL))
            tw, th = dc.GetTextExtent("No footprint preview")
            W, H = self.GetClientSize()
            dc.DrawText("No footprint preview", (W - tw) // 2, (H - th) // 2)
            return

        W, H = self.GetClientSize()
        self._compute_transform(W, H)

        # Header
        dc.SetTextForeground(wx.Colour(100, 100, 100))
        dc.SetFont(wx.Font(8, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                           wx.FONTWEIGHT_NORMAL))
        dc.DrawText("FOOTPRINT", 8, 4)

        self._draw_graphics(dc)
        self._draw_pads(dc)

    def _on_left_down(self, event):
        if not self._payload or not self.on_pad_click:
            return

        mx, my = event.GetPosition()

        for pad in self._payload.pads:
            if not pad.number:
                continue
            cx, cy = self._k2s(pad.at[0], pad.at[1])
            w_px = pad.size[0] * self._scale
            h_px = pad.size[1] * self._scale
            slack = 3

            x0 = cx - w_px / 2 - slack
            y0 = cy - h_px / 2 - slack
            x1 = cx + w_px / 2 + slack
            y1 = cy + h_px / 2 + slack

            if x0 <= mx <= x1 and y0 <= my <= y1:
                self.on_pad_click(pad.number)
                return

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_graphics(self, dc):
        for g in self._payload.graphics:
            color = _LAYER_COLORS.get(g.layer, _DEFAULT_LAYER_COLOR)
            pen_w = self._scale_px(g.stroke_width or 0.12)
            dc.SetPen(wx.Pen(color, pen_w))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)

            if g.type == "line" and g.start and g.end:
                s = self._k2s(g.start[0], g.start[1])
                e = self._k2s(g.end[0], g.end[1])
                dc.DrawLine(s[0], s[1], e[0], e[1])

            elif g.type == "arc" and g.start and g.mid and g.end:
                self._draw_arc(dc, g.start, g.mid, g.end, pen_w, color)

            elif g.type == "circle" and g.center:
                cx, cy = self._k2s(g.center[0], g.center[1])
                r_px = self._scale_px(g.radius)
                dc.DrawCircle(cx, cy, r_px)

            elif g.type == "poly" and g.pts:
                points = [wx.Point(*self._k2s(p[0], p[1])) for p in g.pts]
                fill_val = g.fill in ("solid", "outline")
                if fill_val:
                    dc.SetBrush(wx.Brush(wx.Colour(color.Red(), color.Green(),
                                                    color.Blue(), 75)))
                dc.DrawPolygon(points)
                if fill_val:
                    dc.SetBrush(wx.TRANSPARENT_BRUSH)

            elif g.type == "text" and g.at:
                dc.SetTextForeground(color)
                font_size = max(6, self._scale_px(0.6))
                dc.SetFont(wx.Font(font_size, wx.FONTFAMILY_TELETYPE,
                                   wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
                sx, sy = self._k2s(g.at[0], g.at[1])
                tw, th = dc.GetTextExtent(g.text or "")
                dc.DrawText(g.text or "", sx - tw // 2, sy - th // 2)

    def _draw_arc(self, dc, start, mid, end, pen_w, color):
        ax, ay = start
        bx, by = mid
        cx, cy = end

        D = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(D) < 1e-10:
            s = self._k2s(ax, ay)
            e = self._k2s(cx, cy)
            dc.DrawLine(s[0], s[1], e[0], e[1])
            return

        ux = ((ax*ax+ay*ay)*(by-cy) + (bx*bx+by*by)*(cy-ay) + (cx*cx+cy*cy)*(ay-by)) / D
        uy = ((ax*ax+ay*ay)*(cx-bx) + (bx*bx+by*by)*(ax-cx) + (cx*cx+cy*cy)*(bx-ax)) / D

        cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

        sx1, sy1 = self._k2s(ax, ay)
        sx2, sy2 = self._k2s(cx, cy)
        scx, scy = self._k2s(ux, uy)

        dc.SetPen(wx.Pen(color, pen_w))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)

        # No Y-flip for footprints, so sweep direction is preserved.
        # wx.DC.DrawArc goes counter-clockwise.
        # cross > 0 means CCW in original coords = CCW on screen -> normal order
        # cross < 0 means CW -> swap for CCW DrawArc
        if cross < 0:
            dc.DrawArc(sx2, sy2, sx1, sy1, scx, scy)
        else:
            dc.DrawArc(sx1, sy1, sx2, sy2, scx, scy)

    def _draw_pads(self, dc):
        font_size = max(5, min(9, int(0.5 * self._scale)))
        dc.SetFont(wx.Font(font_size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                           wx.FONTWEIGHT_NORMAL))

        for pad in self._payload.pads:
            is_sel = pad.number in self._highlighted_pads
            fill = _PINK if is_sel else _PAD_FILL
            stroke = _PINK if is_sel else _PAD_STROKE

            cx, cy = self._k2s(pad.at[0], pad.at[1])
            w_px = max(2, int(pad.size[0] * self._scale))
            h_px = max(2, int(pad.size[1] * self._scale))

            dc.SetPen(wx.Pen(stroke, 1))
            dc.SetBrush(wx.Brush(fill))

            x = cx - w_px // 2
            y = cy - h_px // 2

            if pad.shape == "circle":
                dc.DrawCircle(cx, cy, w_px // 2)
            elif pad.shape == "oval":
                r = min(w_px, h_px) // 2
                dc.DrawRoundedRectangle(x, y, w_px, h_px, r)
            elif pad.shape == "roundrect":
                rr = pad.roundrect_rratio or 0.25
                r = int(rr * min(w_px, h_px))
                dc.DrawRoundedRectangle(x, y, w_px, h_px, r)
            else:
                dc.DrawRectangle(x, y, w_px, h_px)

            # Pad number label
            if pad.number:
                text_col = wx.WHITE if is_sel else wx.Colour(220, 220, 220)
                dc.SetTextForeground(text_col)
                tw, th = dc.GetTextExtent(pad.number)
                # Only draw if text fits in pad
                if tw < w_px + 4 and th < h_px + 4:
                    dc.DrawText(pad.number, cx - tw // 2, cy - th // 2)
