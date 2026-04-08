"""wx.Panel that renders a KiCad schematic symbol using BufferedPaintDC.

Handles Y-flip (KiCad symbols use Y-up, screen uses Y-down), pin rendering
with inverted bubbles, click detection on pin tips, and selection highlighting.
"""

import math

import wx


# Hot pink for selected elements
_PINK = wx.Colour(255, 45, 120)
_GREY = wx.Colour(136, 136, 136)
_DARK_GREY = wx.Colour(102, 102, 102)
_TEXT_GREY = wx.Colour(204, 204, 204)
_BG = wx.Colour(10, 10, 10)
_BODY_FILL = wx.Colour(26, 26, 26)


class SymbolPanel(wx.Panel):
    """Renders a KiCad symbol from a RenderPayload."""

    def __init__(self, parent, size=(420, 350)):
        super().__init__(parent, size=size)
        self.SetBackgroundColour(_BG)
        self.SetMinSize(size)

        self._payload = None
        self._selected_pin = None
        self.on_pin_click = None   # callback: fn(pin_number: str)

        # Transform state (recomputed on paint)
        self._scale = 1.0
        self._cx_kicad = 0.0
        self._cy_kicad = 0.0

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def set_data(self, payload):
        self._payload = payload
        self.Refresh()

    def set_selected_pin(self, pin_number):
        self._selected_pin = pin_number
        self.Refresh()

    # ------------------------------------------------------------------
    # Coordinate transforms
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
        """KiCad coords to screen coords (with Y-flip)."""
        W, H = self.GetClientSize()
        sx = W / 2.0 + (kx - self._cx_kicad) * self._scale
        sy = H / 2.0 - (ky - self._cy_kicad) * self._scale
        return int(sx), int(sy)

    def _s2k(self, sx, sy):
        """Screen coords to KiCad coords."""
        W, H = self.GetClientSize()
        kx = self._cx_kicad + (sx - W / 2.0) / self._scale
        ky = self._cy_kicad - (sy - H / 2.0) / self._scale
        return kx, ky

    def _scale_px(self, mm):
        """Convert mm to screen pixels."""
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
            tw, th = dc.GetTextExtent("No symbol preview")
            W, H = self.GetClientSize()
            dc.DrawText("No symbol preview", (W - tw) // 2, (H - th) // 2)
            return

        W, H = self.GetClientSize()
        self._compute_transform(W, H)

        # Draw header
        dc.SetTextForeground(wx.Colour(100, 100, 100))
        dc.SetFont(wx.Font(8, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                           wx.FONTWEIGHT_NORMAL))
        label = "SYMBOL"
        if not self._payload.found:
            label += "  (generated)"
        dc.DrawText(label, 8, 4)

        self._draw_graphics(dc)
        self._draw_pins(dc)

    def _on_left_down(self, event):
        if not self._payload or not self.on_pin_click:
            return

        mx, my = event.GetPosition()
        hit_r = max(8, int(0.6 * self._scale))

        for pin in self._payload.pins:
            angle_rad = math.radians(pin.angle)
            tip_kx = pin.at[0] + pin.length * math.cos(angle_rad)
            tip_ky = pin.at[1] + pin.length * math.sin(angle_rad)
            tip_sx, tip_sy = self._k2s(tip_kx, tip_ky)

            if abs(mx - tip_sx) < hit_r and abs(my - tip_sy) < hit_r:
                self.on_pin_click(pin.number)
                return

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_graphics(self, dc):
        for g in self._payload.graphics:
            stroke_col = _DARK_GREY
            pen_w = self._scale_px(g.stroke_width or 0.254)
            dc.SetPen(wx.Pen(stroke_col, pen_w))

            if g.fill == "background":
                dc.SetBrush(wx.Brush(_BODY_FILL))
            elif g.fill == "outline":
                dc.SetBrush(wx.Brush(stroke_col))
            else:
                dc.SetBrush(wx.TRANSPARENT_BRUSH)

            if g.type == "rectangle" and g.start and g.end:
                x1, y1 = self._k2s(g.start[0], g.start[1])
                x2, y2 = self._k2s(g.end[0], g.end[1])
                rx = min(x1, x2)
                ry = min(y1, y2)
                rw = abs(x2 - x1)
                rh = abs(y2 - y1)
                dc.DrawRectangle(rx, ry, rw, rh)

            elif g.type == "polyline" and g.pts:
                points = [wx.Point(*self._k2s(p[0], p[1])) for p in g.pts]
                dc.SetBrush(wx.TRANSPARENT_BRUSH)
                dc.DrawLines(points)

            elif g.type == "arc" and g.start and g.mid and g.end:
                self._draw_arc(dc, g.start, g.mid, g.end, pen_w, stroke_col)

            elif g.type == "circle" and g.center:
                cx, cy = self._k2s(g.center[0], g.center[1])
                r_px = self._scale_px(g.radius)
                dc.DrawCircle(cx, cy, r_px)

    def _draw_arc(self, dc, start, mid, end, pen_w, color):
        """Draw a 3-point arc using wx.DC.DrawArc."""
        ax, ay = start
        bx, by = mid
        cx, cy = end

        D = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(D) < 1e-10:
            # Degenerate: draw line
            s = self._k2s(ax, ay)
            e = self._k2s(cx, cy)
            dc.DrawLine(s[0], s[1], e[0], e[1])
            return

        ux = ((ax*ax+ay*ay)*(by-cy) + (bx*bx+by*by)*(cy-ay) + (cx*cx+cy*cy)*(ay-by)) / D
        uy = ((ax*ax+ay*ay)*(cx-bx) + (bx*bx+by*by)*(ax-cx) + (cx*cx+cy*cy)*(bx-ax)) / D

        # Cross product to determine direction
        cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

        # wx.DC.DrawArc draws counter-clockwise from pt1 to pt2 around center.
        # After Y-flip, the sense of CW/CCW reverses.
        # If cross > 0 in KiCad space, the arc is CCW. After Y-flip, it becomes CW.
        # So if cross > 0 (originally CCW), we need to swap start/end for DrawArc
        # (which always draws CCW in screen space).
        sx1, sy1 = self._k2s(ax, ay)
        sx2, sy2 = self._k2s(cx, cy)
        scx, scy = self._k2s(ux, uy)

        dc.SetPen(wx.Pen(color, pen_w))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)

        if cross > 0:
            # Originally CCW, after Y-flip becomes CW. Swap for DrawArc (CCW).
            dc.DrawArc(sx2, sy2, sx1, sy1, scx, scy)
        else:
            dc.DrawArc(sx1, sy1, sx2, sy2, scx, scy)

    def _draw_pins(self, dc):
        font_size = max(7, min(10, int(0.9 * self._scale)))
        dc.SetFont(wx.Font(font_size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                           wx.FONTWEIGHT_NORMAL))

        for pin in self._payload.pins:
            is_sel = (pin.number == self._selected_pin)
            color = _PINK if is_sel else _GREY
            text_col = _PINK if is_sel else _TEXT_GREY
            pen_w = self._scale_px(0.35 if is_sel else 0.2)

            angle_rad = math.radians(pin.angle)
            tip_kx = pin.at[0] + pin.length * math.cos(angle_rad)
            tip_ky = pin.at[1] + pin.length * math.sin(angle_rad)

            at_sx, at_sy = self._k2s(pin.at[0], pin.at[1])
            tip_sx, tip_sy = self._k2s(tip_kx, tip_ky)

            # Pin line
            dc.SetPen(wx.Pen(color, pen_w))
            dc.DrawLine(at_sx, at_sy, tip_sx, tip_sy)

            # Inverted bubble
            if pin.shape == "inverted":
                bub_kx = pin.at[0] + 0.4 * math.cos(angle_rad)
                bub_ky = pin.at[1] + 0.4 * math.sin(angle_rad)
                bub_sx, bub_sy = self._k2s(bub_kx, bub_ky)
                bub_r = self._scale_px(0.35)
                dc.SetBrush(wx.TRANSPARENT_BRUSH)
                dc.SetPen(wx.Pen(color, max(1, pen_w // 2)))
                dc.DrawCircle(bub_sx, bub_sy, bub_r)

            # Selection highlight circle at tip
            if is_sel:
                r_px = self._scale_px(0.6)
                dc.SetBrush(wx.Brush(wx.Colour(255, 45, 120, 50)))
                dc.SetPen(wx.TRANSPARENT_PEN)
                dc.DrawCircle(tip_sx, tip_sy, r_px)

            # Pin number at midpoint
            mid_sx = (at_sx + tip_sx) // 2
            mid_sy = (at_sy + tip_sy) // 2
            dc.SetTextForeground(wx.Colour(text_col.Red(), text_col.Green(),
                                           text_col.Blue(), 150))
            tw, th = dc.GetTextExtent(pin.number)

            if pin.angle == 0 or pin.angle == 180:
                dc.DrawText(pin.number, mid_sx - tw // 2, mid_sy - th - 2)
            else:
                dc.DrawText(pin.number, mid_sx + 3, mid_sy - th // 2)

            # Pin name at body end
            dc.SetTextForeground(text_col)
            tw, th = dc.GetTextExtent(pin.name)
            name_offset_px = self._scale_px(0.5)

            if pin.angle == 0:
                # Pin extends right, name goes left of body end (inside body)
                dc.DrawText(pin.name, at_sx - tw - name_offset_px, at_sy - th // 2)
            elif pin.angle == 180:
                # Pin extends left, name goes right of body end
                dc.DrawText(pin.name, at_sx + name_offset_px, at_sy - th // 2)
            elif pin.angle == 90:
                # Pin extends up, name goes below body end
                dc.DrawText(pin.name, at_sx - tw // 2, at_sy + name_offset_px)
            elif pin.angle == 270:
                # Pin extends down, name goes above body end
                dc.DrawText(pin.name, at_sx - tw // 2, at_sy - th - name_offset_px)
            else:
                # Non-standard angle: just place near body end
                dc.DrawText(pin.name, at_sx + 3, at_sy - th - 2)
