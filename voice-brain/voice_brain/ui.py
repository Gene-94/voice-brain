"""Minimal visual feedback — Omarchy overlay style.

A small (~90x90) dark translucent rounded box anchored to the screen corner:
  armed       -> pulsing mic dot
  recording   -> live waveform bars (driven by real RMS levels)
  transcribing/processing -> spinner (covers whisper load + gemma thinking)
  success     -> checkmark (color-coded by route: dream 💜, stats 📊, notes ✅…)
  error       -> ✗
Auto-hides ~2.2 s after a terminal state. Falls back to notify-send headlessly.
"""

from __future__ import annotations

import math
import threading
import time

from .notify import notify_result


class BaseUI:
    def state(self, state: str, text: str | None = None, level: float = 0.0) -> None:
        raise NotImplementedError

    def result(self, state: str, title: str, body: str) -> None:
        notify_result(title, body)

    def run(self) -> None:  # block forever
        while True:
            time.sleep(3600)


class NullUI(BaseUI):
    def state(self, state, text=None, level=0.0):
        pass

    def result(self, state, title, body):
        pass

    def run(self):
        while True:
            time.sleep(3600)


class NotifyUI(BaseUI):
    def __init__(self):
        self._last_state = None
        self._lock = threading.Lock()

    def state(self, state, text=None, level=0.0):
        from .notify import notify
        with self._lock:
            if state == self._last_state:
                return
            self._last_state = state
        if state == "armed":
            notify("🎙️ Voice Brain", "Listening — speak when ready.", timeout_ms=4000)


ANIMATING = {"armed", "recording", "transcribing", "processing"}
TERMINAL = {"success", "dream", "journal", "note", "query", "stats",
            "error", "timeout", "cancelled"}
CHECK_COLOR = {
    "success": (0.29, 0.87, 0.50),   # green
    "journal": (0.29, 0.87, 0.50),
    "note": (0.29, 0.87, 0.50),
    "dream": (0.70, 0.53, 1.00),     # purple
    "stats": (0.38, 0.65, 0.98),    # blue
    "query": (0.38, 0.65, 0.98),
}


class OverlayUI(BaseUI):
    """GTK4 + gtk4-layer-shell visual box."""

    SIZE = 92  # content px — small on purpose
    WAVE_BARS = 18
    LEVEL_HISTORY = 48

    def __init__(self, position: str = "top-right"):
        self.position = position
        self._win = None
        self._da = None
        self._loop = None
        self._state = "idle"
        self._levels: list[float] = []
        self._hide_timer = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ build

    def _build(self):
        import gi
        gi.require_version("Gtk", "4.0")
        try:
            gi.require_version("gtk4-layer-shell", "1.0")
            from gi.repository import GtkLayerShell
        except (ValueError, ImportError) as exc:
            raise ImportError(f"gtk4-layer-shell unavailable: {exc}") from exc
        from gi.repository import Gdk, Gtk

        self._gtk = Gtk
        win = Gtk.Window()
        self._win = win

        try:
            GtkLayerShell.init_for_window(win)
            GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, "top" in self.position)
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.BOTTOM, "bottom" in self.position)
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, "left" in self.position)
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.RIGHT, "right" in self.position)
            for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                         GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
                GtkLayerShell.set_margin(win, edge, 14)
            GtkLayerShell.set_exclusive_zone(win, -1)
            GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
        except Exception:
            pass  # plain floating window fallback

        css = Gtk.CssProvider()
        css.load_from_data(b"""
        window {
            background: rgba(13, 15, 20, 0.86);
            border-radius: 18px;
        }
        drawing { border-radius: 18px; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self._da = Gtk.DrawingArea()
        self._da.set_content_size(self.SIZE, self.SIZE)
        self._da.set_draw_func(self._draw)
        win.set_child(self._da)
        win.set_default_size(self.SIZE, self.SIZE)
        win.set_visible(False)

    # ------------------------------------------------------------------ state input (any thread)

    def state(self, state, text=None, level=0.0):
        with self._lock:
            self._state = state
            if level > 0:
                self._levels.append(max(0.0, min(1.0, level)))
                self._levels = self._levels[-self.LEVEL_HISTORY:]
            terminal = state in TERMINAL
        if self._da is None:
            return
        from gi.repository import GLib
        GLib.idle_add(self._present_idle, terminal)

    def result(self, state, title, body):
        self.state(state)
        notify_result(title, body)

    def _present_idle(self, terminal: bool):
        from gi.repository import GLib
        if self._win is None:
            return False
        self._win.present()
        if self._hide_timer:
            GLib.source_remove(self._hide_timer)
            self._hide_timer = None
        if terminal:
            self._hide_timer = GLib.timeout_add(2200, self._hide)
        elif not self._tick_running:
            GLib.timeout_add(33, self._tick)
        return False

    @property
    def _tick_running(self) -> bool:
        return getattr(self, "_ticking", False)

    def _tick(self):
        self._ticking = self._state in ANIMATING and self._win is not None \
            and self._win.get_visible()
        if self._da and self._ticking:
            self._da.queue_draw()
            return True
        self._ticking = False
        return False

    def _hide(self):
        if self._win is not None:
            self._win.set_visible(False)
        self._hide_timer = None
        return False

    # ------------------------------------------------------------------ drawing

    def _draw(self, da, cr, width, height):
        with self._lock:
            state = self._state
            levels = list(self._levels)
        t = time.monotonic()
        cx, cy = width / 2, height / 2

        if state == "recording":
            cr.set_source_rgb(1.0, 0.42, 0.42)
            bar_w = width / (self.WAVE_BARS * 1.6)
            history = levels[-self.WAVE_BARS:] if levels else []
            if not history:
                history = [0.02]
            history = history + [0.02] * (self.WAVE_BARS - len(history))
            x = (width - (len(history) * bar_w * 1.6 - bar_w * 0.6)) / 2
            for lvl in history:
                h = max(3.0, lvl * height * 0.78)
                cr.set_line_width(bar_w * 0.75)
                cr.set_line_cap(1)  # round
                cr.move_to(x, cy - h / 2)
                cr.line_to(x, cy + h / 2)
                cr.stroke()
                x += bar_w * 1.6

        elif state in ("transcribing", "processing"):
            # spinner
            cr.set_source_rgb(0.96, 0.77, 0.26)
            cr.set_line_width(4.5)
            cr.set_line_cap(1)
            r = height * 0.28
            a0 = t * 5.5
            cr.arc(cx, cy, r, a0, a0 + math.pi * 1.25)
            cr.stroke()

        elif state == "armed":
            # pulsing mic dot
            pulse = 0.5 + 0.5 * math.sin(t * 4.0)
            cr.set_source_rgba(0.98, 0.98, 0.98, 0.35 + 0.45 * pulse)
            cr.set_line_width(3.0)
            r = height * (0.20 + 0.06 * pulse)
            cr.arc(cx, cy, r, 0, math.tau)
            cr.stroke()
            cr.arc(cx, cy, 2.5, 0, math.tau)
            cr.fill()

        elif state in TERMINAL:
            if state == "error":
                cr.set_source_rgb(1.0, 0.36, 0.36)
                r = height * 0.26
                cr.set_line_width(5.5)
                cr.set_line_cap(1)
                cr.move_to(cx - r, cy - r)
                cr.line_to(cx + r, cy + r)
                cr.move_to(cx + r, cy - r)
                cr.line_to(cx - r, cy + r)
                cr.stroke()
            elif state in ("timeout", "cancelled"):
                pass
            else:
                # checkmark, color-coded by route
                rgb = CHECK_COLOR.get(state, CHECK_COLOR["success"])
                cr.set_source_rgb(*rgb)
                cr.set_line_width(6.5)
                cr.set_line_cap(1)
                r = height * 0.24
                cr.move_to(cx - r, cy + r * 0.1)
                cr.line_to(cx - r * 0.25, cy + r * 0.8)
                cr.line_to(cx + r * 1.05, cy - r * 0.85)
                cr.stroke()

    def run(self):
        import gi
        from gi.repository import GLib
        self._build()
        self._loop = GLib.MainLoop()
        self._loop.run()


def make_ui(cfg) -> BaseUI:
    mode = cfg.get("ui.mode", "overlay")
    if mode == "none":
        return NullUI()
    if mode == "notify":
        return NotifyUI()
    try:
        import gi  # noqa: F401
        ui = OverlayUI(position=cfg.get("ui.position", "top-right"))
        ui._build()
        return ui
    except Exception:
        return NotifyUI()
