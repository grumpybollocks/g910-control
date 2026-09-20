#!/usr/bin/env python3
"""
G910 Control App -- canvas-based rearchitecture. Single unified view,
NOT tabbed (Backlight/G-Keys/Profiles started as separate tabs, all
three were merged into one view over several rounds of UI work -- see
G910_CANVAS_PLAN.md for that history).

MainView: real per-key geometry canvas (g910_canvas.KeyboardCanvas) +
a Color Mode sidebar for bulk zone coloring on the left, a G-Key
Macros strip under the canvas, and a Profiles panel on the right.
Selecting a zone in the sidebar highlights those keys on the canvas;
applying a color previews it there too, not just on the real hardware.

Brightness: this keyboard's LED protocol has no separate hardware
brightness call (block "keys"'s feature functions are just
get/set-per-key-color, get/set-block-color, commit -- confirmed by
reading feature_leds.c directly, see G910_README.md). So brightness
here means what it means for any RGB device without one: scale the
chosen color's R/G/B by the brightness percentage before sending.

G-Key Macros panel: a compact strip under the canvas. Macro record/
playback for G1-G9, switchable via M1/M2/M3 profiles -- ports
g510_app.py's proven RecorderThread/MacroRecordDialog pattern almost
verbatim. Recording device confirmed empirically this session (not
assumed): /dev/input/event2, stable by-id path below, is the one that
actually fires during real typing (event3 fires nothing -- tested live
by listening on both while the user typed). MR is NOT a 4th profile
here (per the user's earlier explicit decision: it's a literal
macro-record toggle, a separate feature for the future macro daemon,
not a GUI profile selector).
"""
import sys
import json
import random
import select
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QSlider, QTabWidget,
    QDialog, QLineEdit, QMessageBox, QInputDialog, QFrame, QScrollArea,
    QColorDialog, QSizePolicy,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QColor
import evdev
from evdev import ecodes

import g910_backlight as bl
from g910_canvas import KeyboardCanvas, ZONE_KEYS, ZONE_SELECTION_KEYS, PRESET_COLORS, ALL_CELLS

MACROS_FILE = bl.DATA_DIR / "g910_macros.json"  # separate from the G510s's macros.json


def _find_g910_event_device():
    """Match the G910's base HID interface by vendor/product ID
    (046d:c335) + physical interface number, not by-id's embedded
    per-unit USB serial -- confirmed via `udevadm info` that this
    serial is per-unit, not a fixed model string, so it would never
    match a different person's G910. Interface 0
    (phys ends "/input0") is confirmed empirically (this session, by
    listening on both interfaces while actually typing) to be the one
    that fires real keypress events; interface 1 fires nothing. Returns
    None (rather than raising) if no G910 is attached -- the app can
    still open without one, only macro recording actually needs it.
    Each device is opened defensively: a permission error or a device
    disappearing mid-enumeration (real races on a real desktop, not
    hypothetical) skips that one device instead of crashing the whole
    app at import time -- this function touches every input device on
    the system, unlike the old hardcoded string it replaced, which
    never opened anything until actual use.
    """
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if (dev.info.vendor, dev.info.product) == (0x046D, 0xC335) and dev.phys.endswith("input0"):
            return path
    return None


MAIN_KEYBOARD_DEVICE = _find_g910_event_device()

STYLESHEET = """
QWidget {
    background-color: #17171a;
    color: #e4e4e7;
    font-family: sans-serif;
}
QTabWidget::pane {
    border: 1px solid #2a2a30;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background: #1e1e22;
    border: 1px solid #2a2a30;
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #26262b;
    border-bottom-color: #26262b;
    color: white;
}
QPushButton {
    background-color: #26262b;
    border: 1px solid #34343a;
    border-radius: 6px;
    padding: 7px 10px;
    text-align: left;
}
QPushButton:hover {
    background-color: #302f36;
    border-color: #46454e;
}
QPushButton:checked {
    background-color: #3a6cc4;
    border-color: #5a8ce0;
    color: white;
}
QPushButton#Primary {
    background-color: #3a6cc4;
    border-color: #5a8ce0;
    color: white;
    text-align: center;
    font-weight: 600;
    padding: 9px 10px;
}
QPushButton#Primary:hover {
    background-color: #4a7cd4;
    border-color: #6a9cf0;
}
QPushButton#Danger {
    background-color: #c43a3a;
    border-color: #e05a5a;
    color: white;
    text-align: center;
    font-weight: 600;
    padding: 9px 10px;
}
QPushButton#Danger:hover {
    background-color: #d44a4a;
    border-color: #f06a6a;
}
QLabel#Title {
    font-size: 15px;
    font-weight: 600;
    padding: 4px 2px 10px 2px;
}
QPushButton#ZoneButton {
    text-align: center;
    padding: 3px 8px;
}
QWidget#Panel {
    background-color: #1c1c20;
    border: 1px solid #2a2a30;
    border-radius: 8px;
}
QWidget#Card {
    background-color: #232328;
    border: 1px solid #34343a;
    border-radius: 6px;
}
QFrame#Separator {
    background-color: #2a2a30;
    border: none;
    max-width: 1px;
    min-width: 1px;
}
QFrame#HSeparator {
    background-color: #2a2a30;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QLabel#Status {
    color: #9a9aa2;
    font-size: 11px;
    padding-top: 4px;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #34343a;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #5a8ce0;
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}
QLineEdit {
    background-color: #1e1e22;
    border: 1px solid #34343a;
    border-radius: 4px;
    padding: 5px;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    background: #1c1c20;
    width: 12px;
    margin: 0;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: #5a8ce0;
    border-radius: 5px;
    min-height: 24px;
    margin: 1px;
}
QScrollBar::handle:vertical:hover {
    background: #6a9cf0;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
"""


def scale_color(color, brightness_pct):
    factor = brightness_pct / 100.0
    r = max(0, min(255, round(color.red() * factor)))
    g = max(0, min(255, round(color.green() * factor)))
    b = max(0, min(255, round(color.blue() * factor)))
    return QColor(r, g, b)


# --- Animated effects (Breathing / Colour Cycle / Rainbow Wave) -------

class EffectThread(QThread):
    """Runs one animated lighting effect in a loop until stopped, in
    its own thread -- same reasoning as RecorderThread/the macro
    daemon's replay(): real per-tick timing measured live on actual
    hardware before this was written (a single-group set-leds call
    ~20ms, a full per-key Main Board sweep ~32ms, Main Board's uniform
    "all=" fill -- the only path that reaches the six individually-
    unaddressable keys, so it's what Breathing/Colour Cycle use there
    -- ~114ms). All comfortably fast enough for these effects' actual
    tick intervals, but 114ms would visibly stall the rest of the GUI
    every tick if run directly on a QTimer on the main thread instead.

    apply_fn(hexcolor) -> (ok, err): how Breathing/Colour Cycle send a
    single colour to the real target (reuses ColorModeSidebar's own
    _apply_zone, so this never duplicates that per-target dispatch a
    second way). Rainbow Wave doesn't use apply_fn at all -- it always
    has its own per-key gradient, sent directly."""
    tick_applied = pyqtSignal(dict)   # {key_name: "#rrggbb"} for the canvas preview
    tick_failed = pyqtSignal(str)

    # Base pacing at speed_pct=100, and a floor per kind so the Speed
    # slider can never ask this thread to out-run what was actually
    # measured on real hardware this session (Main Board's whole-block
    # "all=" fill -- what Breathing/Cycle use there -- ~114ms; a full
    # per-key sweep, what Wave uses -- ~32ms on Main Board's 62 keys).
    # One conservative floor per kind, not a precise per-target one:
    # smaller zones could safely go faster, but erring toward "never
    # spams the device" is a better default than being precise about it.
    _BASE_INTERVAL_MS = {"wave": 60, "breathing": 100, "cycle": 100}
    _BASE_STEP = {"wave": 0.015, "breathing": 0.012, "cycle": 0.004}
    _MIN_INTERVAL_MS = {"wave": 40, "breathing": 110, "cycle": 110}

    def __init__(self, kind, apply_fn, ordered_keys, real_names, block, brightness_pct, base_rgb, speed_pct=100):
        super().__init__()
        self.kind = kind
        self.apply_fn = apply_fn
        self.ordered_keys = ordered_keys
        self.real_names = real_names
        self.block = block
        self.brightness_pct = brightness_pct
        self.base_rgb = base_rgb
        self.speed_pct = speed_pct
        self._stop = False

    def stop(self):
        self._stop = True

    def set_speed(self, pct):
        # Plain attribute write, read fresh at the top of every loop
        # iteration below -- no lock needed for a single int/float
        # under the GIL, same as how stop() already works. Takes
        # effect on the very next tick, which is what makes this
        # "live" rather than needing a restart.
        self.speed_pct = pct

    def run(self):
        phase = 0.0
        while not self._stop:
            # Recomputed every tick from the current speed_pct, not
            # cached -- a slider drag mid-effect changes pacing on the
            # very next iteration.
            scale = 100.0 / max(1, self.speed_pct)
            interval_ms = max(self._MIN_INTERVAL_MS[self.kind], int(self._BASE_INTERVAL_MS[self.kind] * scale))
            step = self._BASE_STEP[self.kind] / scale

            if self.kind == "wave":
                hexes = bl.rainbow_hexes(len(self.real_names), self.brightness_pct, phase)
                ok, err = bl._run_set_leds(self.block, [f"{k}={h}" for k, h in zip(self.real_names, hexes)])
                preview = {name: f"#{h}" for name, h in zip(self.ordered_keys, hexes)}
            elif self.kind == "breathing":
                hexcolor = bl.breathing_hex(self.base_rgb, phase, self.brightness_pct)
                ok, err = self.apply_fn(hexcolor)
                preview = {name: f"#{hexcolor}" for name in self.ordered_keys}
            else:  # "cycle"
                hexcolor = bl.cycle_hex(phase, self.brightness_pct)
                ok, err = self.apply_fn(hexcolor)
                preview = {name: f"#{hexcolor}" for name in self.ordered_keys}

            if not ok:
                self.tick_failed.emit(err or "unknown error")
                break
            self.tick_applied.emit(preview)
            if self._stop:
                break
            self.msleep(interval_ms)
            phase += step


# --- Color Mode sidebar (left side of MainView) -----------------------

class ColorModeSidebar(QWidget):
    """Select a zone, set brightness, pick a color, Apply it to that
    whole zone at once. Selecting a zone highlights it on the canvas
    (including inert non-colorable keys, for visual completeness); a
    successful apply previews the (brightness-scaled) color there too."""
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.current_target = "Logo"
        self.brightness_pct = 100
        self.effect_thread = None
        self.effect_speed_pct = 100
        # 180 used to clip real content -- confirmed directly (not
        # guessed): the hex-code row (QLineEdit + Apply button) and the
        # zone grid's "Nav Cluster"/"Main Board" row each need ~225-245px
        # on their own, and the scroll area's own vertical scrollbar eats
        # another 12px off whatever's left. 280 is the measured minimum
        # content sizeHint (263) plus that scrollbar allowance, so
        # nothing actually gets cut off regardless of which zone/button
        # labels happen to be showing.
        self.setFixedWidth(280)

        # Real layout bug found via live use: this panel's own content
        # (zone buttons + brightness + color controls) is naturally
        # taller than the keyboard canvas -- since MainWindow sizes
        # itself to fit the tallest column, that made the WHOLE window
        # grow to fit this sidebar, leaving a big empty gap below the
        # shorter canvas/G-keys column. Same fix as the Profiles panel
        # already got: put the content in a QScrollArea instead of
        # adding it to this widget directly, so the canvas (not
        # whichever side panel happens to be tallest) drives the
        # window's height, and anything taller than that just scrolls.
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer)

        content = QWidget()
        wrapper_layout = QVBoxLayout(content)
        wrapper_layout.setContentsMargins(10, 10, 10, 10)
        wrapper_layout.setSpacing(4)

        self.tabs = QTabWidget()
        wrapper_layout.addWidget(self.tabs)

        color_tab = QWidget()
        layout = QVBoxLayout(color_tab)
        layout.setContentsMargins(6, 10, 6, 6)
        layout.setSpacing(4)

        # 2-column grid, not a vertical list -- real complaint from live
        # use: 6 full-width stacked buttons ate a lot of vertical space
        # for what's fundamentally a small set of short-label choices.
        self.target_buttons = {}
        zone_grid = QGridLayout()
        zone_grid.setSpacing(4)
        for i, name in enumerate(ZONE_KEYS):
            btn = QPushButton(name)
            btn.setObjectName("ZoneButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, n=name: self.select_target(n))
            zone_grid.addWidget(btn, i // 2, i % 2)
            self.target_buttons[name] = btn
        layout.addLayout(zone_grid)
        self.target_buttons[self.current_target].setChecked(True)
        self.canvas.select_keys(ZONE_SELECTION_KEYS[self.current_target])

        layout.addSpacing(8)
        bright_row = QHBoxLayout()
        bright_label = QLabel("Brightness")
        bright_row.addWidget(bright_label)
        self.bright_value_label = QLabel("100%")
        bright_row.addStretch()
        bright_row.addWidget(self.bright_value_label)
        layout.addLayout(bright_row)

        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(1, 100)
        self.brightness_slider.setValue(100)
        self.brightness_slider.valueChanged.connect(self.on_brightness_changed)
        layout.addWidget(self.brightness_slider)

        # Hex field moved above the presets and given a bolder label --
        # it was easy to miss entirely sitting below the swatch grid,
        # confirmed by the user not noticing it was there at all. The
        # preview swatch used to be its own full-width row above this
        # one (a "big colour tab" complaint from live use) -- now it's
        # a small square living directly on the hex row itself, and it
        # updates live as you type/pick a colour (on_hex_text_changed),
        # not just after a successful hardware Apply.
        layout.addSpacing(8)
        layout.addWidget(QLabel("<b>Hex code</b>"))
        hex_row = QHBoxLayout()
        hex_row.setSpacing(6)
        self.preview_swatch = QLabel()
        self.preview_swatch.setFixedSize(26, 26)
        self._set_preview_style(QColor(38, 38, 43))  # matches the app's own default button gray, not a "real" color yet
        hex_row.addWidget(self.preview_swatch)
        self.hex_edit = QLineEdit()
        self.hex_edit.setPlaceholderText("8000ff")
        self.hex_edit.returnPressed.connect(self.on_apply_hex)
        self.hex_edit.textChanged.connect(self.on_hex_text_changed)
        hex_row.addWidget(self.hex_edit)
        hex_apply_btn = QPushButton("Apply")
        hex_apply_btn.setObjectName("Primary")
        hex_apply_btn.clicked.connect(self.on_apply_hex)
        hex_row.addWidget(hex_apply_btn)
        layout.addLayout(hex_row)

        layout.addSpacing(4)
        picker_btn = QPushButton("Colour Picker")
        picker_btn.setToolTip("Opens a full colour picker -- fills the hex code above, doesn't apply it by itself")
        picker_btn.clicked.connect(self.on_pick_color)
        layout.addWidget(picker_btn)

        layout.addSpacing(8)
        layout.addWidget(QLabel("Presets"))
        swatch_grid = QGridLayout()
        swatch_grid.setSpacing(4)
        for i, (name, rgb) in enumerate(PRESET_COLORS.items()):
            btn = QPushButton()
            btn.setToolTip(name)
            btn.setFixedSize(28, 28)
            hexval = "#%02x%02x%02x" % rgb
            btn.setStyleSheet(f"background-color: {hexval}; border: 1px solid #34343a; border-radius: 4px;")
            btn.clicked.connect(lambda _, c=QColor(*rgb): self._apply_color(c))
            swatch_grid.addWidget(btn, i // 5, i % 5)
        swatch_row = QHBoxLayout()
        swatch_row.addStretch()
        swatch_row.addLayout(swatch_grid)
        swatch_row.addStretch()
        layout.addLayout(swatch_row)

        layout.addSpacing(6)
        # Renamed with a (WIP) flag per direct feedback: this is a hue
        # SWEEP with a randomized starting point, not truly independent
        # per-key randomness -- on Main Board especially, keys in the
        # same row sit next to each other in the gradient, so it reads
        # as an ordered rainbow band, not a scattered random look. The
        # name shouldn't promise more than the algorithm delivers.
        rainbow_btn = QPushButton("Random Colours (WIP)")
        rainbow_btn.setToolTip("A gradient sweep with a random starting hue, not fully independent per-key colours yet")
        rainbow_btn.clicked.connect(self.on_apply_rainbow)
        layout.addWidget(rainbow_btn)
        layout.addStretch()

        self.tabs.addTab(color_tab, "Color Mode")

        # Effects (animated) split into its own tab, away from the
        # Color Mode/Rainbow controls that just work -- real complaint
        # from live use: Breathing/Colour Cycle/Rainbow Wave stacked
        # directly under Rainbow made the whole sidebar look like one
        # undifferentiated pile of buttons, and an effect left running
        # was easy to lose track of. Marked WIP because the on-screen
        # preview for Main Board's six individually-unaddressable keys
        # can still drift from the real keyboard during an animation --
        # unlike the one-shot Rainbow/preset applies, which are solid.
        effects_tab = QWidget()
        elayout = QVBoxLayout(effects_tab)
        elayout.setContentsMargins(6, 10, 6, 6)
        elayout.setSpacing(4)
        wip_note = QLabel(
            "Work in progress: animations run on the real keyboard, but "
            "the on-screen preview for a few keys can lag behind it. "
            "Switch zones or tabs to stop whatever's running."
        )
        wip_note.setObjectName("Status")
        wip_note.setWordWrap(True)
        elayout.addWidget(wip_note)
        elayout.addSpacing(6)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Speed"))
        self.speed_value_label = QLabel("100%")
        speed_row.addStretch()
        speed_row.addWidget(self.speed_value_label)
        elayout.addLayout(speed_row)
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(20, 300)
        self.speed_slider.setValue(100)
        self.speed_slider.setToolTip("Changes pace live if an effect is already running -- no need to restart it")
        self.speed_slider.valueChanged.connect(self.on_speed_changed)
        elayout.addWidget(self.speed_slider)
        breathing_btn = QPushButton("Breathing")
        breathing_btn.setToolTip("Pulses the hex code above, in and out, until Stopped")
        breathing_btn.clicked.connect(lambda: self._start_effect("breathing"))
        elayout.addWidget(breathing_btn)
        cycle_btn = QPushButton("Colour Cycle")
        cycle_btn.setToolTip("The whole zone slowly rotates through every hue")
        cycle_btn.clicked.connect(lambda: self._start_effect("cycle"))
        elayout.addWidget(cycle_btn)
        wave_btn = QPushButton("Rainbow Wave")
        wave_btn.setToolTip("Like Rainbow, but the gradient scrolls across the keys")
        wave_btn.clicked.connect(lambda: self._start_effect("wave"))
        elayout.addWidget(wave_btn)
        elayout.addSpacing(6)
        stop_effect_btn = QPushButton("Stop Effects")
        stop_effect_btn.setObjectName("Danger")
        stop_effect_btn.clicked.connect(self._stop_effect)
        elayout.addWidget(stop_effect_btn)
        elayout.addStretch()

        self.tabs.addTab(effects_tab, "Effects (WIP)")
        self.tabs.currentChanged.connect(lambda _: self._stop_effect())

        self.status_label = QLabel("")
        self.status_label.setObjectName("Status")
        self.status_label.setWordWrap(True)
        wrapper_layout.addWidget(self.status_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Capped explicitly -- a QScrollArea's own sizeHint still
        # reports its content's full natural height unless bounded, so
        # just wrapping in one doesn't stop it from stretching the
        # window on its own. ~340px matches the canvas+G-Keys strip
        # column's own real height (canvas.minimumHeight() is 286,
        # +the G-Keys strip+spacing below it), so this panel can never
        # be the one driving the window taller than the keyboard.
        scroll.setMaximumHeight(460)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def on_brightness_changed(self, value):
        self.brightness_pct = value
        self.bright_value_label.setText(f"{value}%")

    def select_target(self, name):
        self._stop_effect()  # switching zones while a different zone is animating would just be confusing
        self.current_target = name
        for n, btn in self.target_buttons.items():
            btn.setChecked(n == name)
        self.canvas.select_keys(ZONE_SELECTION_KEYS[name])

    def sync_target(self, name):
        """Called when the CANVAS itself is clicked (a key/cluster),
        to keep this list in sync with it -- unlike select_target, this
        must NOT touch the canvas's own selection state. The canvas
        already owns that from the very click that triggered this (its
        own click-to-color-picker flow), so calling select_keys() here
        would stomp the single-key selection with the whole zone and
        make a plain click on one key recolor the entire zone instead."""
        if name not in self.target_buttons:
            return
        self.current_target = name
        for n, btn in self.target_buttons.items():
            btn.setChecked(n == name)

    def on_apply_hex(self):
        """Exact-value path -- kept alongside the swatches/gradient
        picker for anyone who already knows the hex they want, or
        wants to match a color exactly rather than eyeball it."""
        text = self.hex_edit.text().strip().lstrip("#")
        if len(text) != 6 or any(c not in "0123456789abcdefABCDEF" for c in text):
            self.status_label.setText("Invalid hex color -- use 6 hex digits, e.g. 8000ff")
            return
        self._apply_color(QColor(f"#{text}"))

    def on_hex_text_changed(self, text):
        """Live preview only -- no hardware call. Updates the small
        swatch next to the hex field as you type or as the Colour
        Picker fills it in, so you see what you're about to Apply
        before actually sending it. An invalid/partial hex just leaves
        the swatch showing whatever it last showed, rather than
        flashing to a default colour on every keystroke."""
        text = text.strip().lstrip("#")
        if len(text) == 6 and all(c in "0123456789abcdefABCDEF" for c in text):
            self._set_preview_style(QColor(f"#{text}"))

    def on_pick_color(self):
        """Qt's native colour picker -- fills the hex field, same as
        typing a value in by hand, but doesn't Apply it on its own.
        Starts from whatever's currently in the hex field (if valid)
        so re-opening the picker doesn't reset your starting point."""
        current = self.hex_edit.text().strip().lstrip("#")
        if len(current) == 6 and all(c in "0123456789abcdefABCDEF" for c in current):
            initial = QColor(f"#{current}")
        else:
            initial = QColor(255, 255, 255)
        color = QColorDialog.getColor(initial, self, "Pick a colour")
        if color.isValid():
            self.hex_edit.setText(color.name().lstrip("#"))

    def _set_preview_style(self, color):
        self.preview_swatch.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid #34343a; border-radius: 4px;"
        )

    def _apply_color(self, color):
        self._stop_effect()  # a static apply should win over a leftover animation, not fight it
        scaled = scale_color(color, self.brightness_pct)
        self._set_preview_style(scaled)
        hexcolor = scaled.name().lstrip("#")
        # ZONE_SELECTION_KEYS, not ZONE_KEYS: for Main Board this also
        # includes Win/Alt/AltGr/Menu/right-Ctrl/right-Shift, which
        # DO get reached by the real apply (set_main_board_color's
        # whole-block fill, confirmed via live testing) even though
        # they can't be addressed individually -- using ZONE_KEYS here
        # would leave the canvas preview wrong (still grey) for keys
        # that actually did change color on the real hardware.
        preview_keys = ZONE_SELECTION_KEYS[self.current_target]

        ok, err = self._apply_zone(self.current_target, hexcolor)
        if ok:
            self.status_label.setText(f"{self.current_target} set to #{hexcolor} ({self.brightness_pct}%)")
            self.canvas.set_colors(preview_keys, scaled)
        else:
            self.status_label.setText(f"FAILED: {err}")

    def _apply_zone(self, target, hexcolor):
        if target == "Logo":
            return bl.set_group_color("logo", hexcolor)
        if target == "G-Keys":
            return bl.set_group_color("gkeys", hexcolor)
        if target == "F1-F12":
            return bl.set_group_color("function_row", hexcolor)
        if target == "Numpad":
            return bl.set_group_color("numpad", hexcolor)
        if target == "Nav Cluster":
            return bl.set_group_color("nav_cluster", hexcolor)
        if target == "Main Board":
            return bl.set_main_board_color(hexcolor)
        return False, f"Unknown target: {target}"

    # Same block each target actually lives on, per _apply_zone above --
    # reused here so the rainbow apply calls the right keyledsctl block
    # without re-deriving it from the target name a second way.
    _TARGET_BLOCK = {
        "Logo": "logo", "G-Keys": "gkeys", "F1-F12": "keys",
        "Numpad": "keys", "Nav Cluster": "keys", "Main Board": "keys",
    }

    def on_apply_rainbow(self):
        """Sweeps a rainbow gradient across the selected zone's own
        keys, in the same left-to-right/top-to-bottom order they're
        declared in g910_canvas.ALL_CELLS. For Main Board specifically,
        also gives the six individually-unaddressable keys (Win/Alt/
        AltGr/Menu/right-Ctrl/right-Shift) the gradient's first hue via
        set_main_board_rainbow's whole-block fill, instead of leaving
        them at a stale colour -- previously this just skipped them
        entirely, which is the "grey keys" bug reported repeatedly.

        phase is randomised on every click (requested explicitly) so
        repeat clicks give a genuinely different-looking sweep instead
        of the identical fixed gradient each time -- same rainbow_hexes
        math, just a different starting hue."""
        self._stop_effect()
        target = self.current_target
        block = self._TARGET_BLOCK[target]
        wanted = ZONE_KEYS[target]
        ordered_keys = [c.key_name for c in ALL_CELLS if c.key_name in wanted]
        real_names = [bl._real_key_name(block, k) for k in ordered_keys]
        phase = random.random()

        if target == "Main Board":
            ok, err = bl.set_main_board_rainbow(real_names, brightness_pct=self.brightness_pct, phase=phase)
        else:
            ok, err = bl.set_keys_rainbow(block, real_names, brightness_pct=self.brightness_pct, phase=phase)

        if ok:
            # Calling rainbow_hexes() again with the identical
            # arguments (including phase) -- not re-deriving the
            # scaling in QColor here -- guarantees the preview can
            # never drift from what was actually just sent to the
            # hardware.
            hexes = bl.rainbow_hexes(len(ordered_keys), brightness_pct=self.brightness_pct, phase=phase)
            preview = {name: QColor(f"#{h}") for name, h in zip(ordered_keys, hexes)}
            fill_count = 0
            if target == "Main Board" and hexes:
                fill_color = QColor(f"#{hexes[0]}")
                extra_keys = ZONE_SELECTION_KEYS[target] - wanted
                for name in extra_keys:
                    preview[name] = fill_color
                fill_count = len(extra_keys)
            self.canvas.set_colors_map(preview)
            if fill_count:
                self.status_label.setText(
                    f"{target} set to random colours ({len(ordered_keys)} keys + "
                    f"{fill_count} whole-board-fill keys, {self.brightness_pct}%)"
                )
            else:
                self.status_label.setText(f"{target} set to random colours ({len(ordered_keys)} keys, {self.brightness_pct}%)")
        else:
            self.status_label.setText(f"FAILED: {err}")

    def _stop_effect(self):
        """Stops whatever EffectThread is currently running, if any --
        called both by the explicit Stop button and automatically
        whenever a static apply (preset/hex/Rainbow) or a zone switch
        happens, so a leftover animation can never keep overwriting
        something the user just tried to set statically."""
        if self.effect_thread is not None:
            self.effect_thread.stop()
            self.effect_thread.wait(2000)
            self.effect_thread = None

    def _start_effect(self, kind):
        """Starts kind ("breathing"/"cycle"/"wave") on the currently
        selected zone. Only one effect ever runs at a time -- starting
        a new one (even the same kind again, e.g. after changing the
        brightness slider) stops whatever was already running first."""
        self._stop_effect()
        target = self.current_target
        block = self._TARGET_BLOCK[target]
        # Breathing/Cycle go through _apply_zone -> set_main_board_color,
        # which DOES reach Main Board's six individually-unaddressable
        # keys via its whole-block "all=" fill (same reasoning
        # _apply_color's own comment already documents for the static
        # case) -- so their preview should use ZONE_SELECTION_KEYS, same
        # as the static apply. Wave sends real per-key directives
        # directly and genuinely never reaches those six keys, so it
        # keeps ZONE_KEYS. Using ZONE_KEYS for all three (the bug found
        # from a real screenshot: those six keys visibly stuck at a
        # stale colour during Colour Cycle while the rest of the board
        # updated) was the preview silently under-covering what
        # Breathing/Cycle's own real apply actually reaches.
        wanted = ZONE_SELECTION_KEYS[target] if kind in ("breathing", "cycle") else ZONE_KEYS[target]
        ordered_keys = [c.key_name for c in ALL_CELLS if c.key_name in wanted]
        real_names = [bl._real_key_name(block, k) for k in ordered_keys]

        # Breathing's base colour comes from whatever's in the hex
        # field right now -- lets you breathe a colour you actually
        # picked, not a hardcoded default. Invalid/empty hex falls
        # back to white rather than refusing to start the effect.
        text = self.hex_edit.text().strip().lstrip("#")
        if len(text) == 6 and all(c in "0123456789abcdefABCDEF" for c in text):
            base_rgb = tuple(int(text[i:i+2], 16) for i in (0, 2, 4))
        else:
            base_rgb = (255, 255, 255)

        thread = EffectThread(
            kind, lambda hexcolor: self._apply_zone(target, hexcolor),
            ordered_keys, real_names, block, self.brightness_pct, base_rgb,
            speed_pct=self.effect_speed_pct,
        )
        thread.tick_applied.connect(self._on_effect_tick)
        thread.tick_failed.connect(self._on_effect_failed)
        self.effect_thread = thread
        thread.start()
        names = {"breathing": "Breathing", "cycle": "Colour Cycle", "wave": "Rainbow Wave"}
        self.status_label.setText(f"{target}: {names[kind]} running -- click Stop Effect to end it")

    def on_speed_changed(self, value):
        self.effect_speed_pct = value
        self.speed_value_label.setText(f"{value}%")
        if self.effect_thread is not None:
            # Live: no restart needed, EffectThread reads this fresh
            # every tick.
            self.effect_thread.set_speed(value)

    def _on_effect_tick(self, preview):
        for name, hexstr in preview.items():
            self.canvas._colors[name] = QColor(hexstr)
        self.canvas.update()

    def _on_effect_failed(self, err):
        self.status_label.setText(f"Effect stopped: {err}")
        self.effect_thread = None


def _vseparator():
    line = QFrame()
    line.setObjectName("Separator")
    line.setFrameShape(QFrame.VLine)
    return line


def _hseparator():
    line = QFrame()
    line.setObjectName("HSeparator")
    line.setFrameShape(QFrame.HLine)
    return line


class MainView(QWidget):
    """Everything: Color Mode sidebar (left), keyboard canvas + G-Key
    Macros strip (middle), Profiles panel (right). Started as a
    "Backlight tab" before G-Keys and Profiles were merged in from
    their own tabs -- name kept in sync with what it actually is now,
    not what it used to be."""
    def __init__(self):
        super().__init__()
        outer = QHBoxLayout()
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(14)
        self.setLayout(outer)

        self.canvas = KeyboardCanvas()
        sidebar = ColorModeSidebar(self.canvas)
        sidebar.setObjectName("Panel")
        self.gkeys_panel = GKeysTab(self.canvas)
        self.gkeys_panel.setObjectName("Panel")

        # Canvas + G-Keys strip stacked in one column (the strip sits
        # in what used to be empty space below the keyboard). Centered
        # under the "keyboard proper" (M-keys/Logo/G-keys/main board),
        # NOT the whole canvas widget -- the canvas is wider than that
        # because Nav Cluster/Numpad extend further right, so plain
        # AlignHCenter across the full widget looked off-center
        # relative to the keyboard block itself.
        canvas_column = QVBoxLayout()
        canvas_column.setSpacing(10)
        canvas_column.addWidget(self.canvas)

        board_left, board_right = self.canvas.main_board_pixel_span()
        board_center = (board_left + board_right) / 2
        gkeys_width = self.gkeys_panel.sizeHint().width()
        left_margin = max(0, round(board_center - gkeys_width / 2))
        gkeys_row = QHBoxLayout()
        gkeys_row.addSpacing(left_margin)
        gkeys_row.addWidget(self.gkeys_panel)
        gkeys_row.addStretch()
        canvas_column.addLayout(gkeys_row)
        canvas_column.addStretch()

        self.profiles_panel = ProfilesTab(self.canvas, sidebar)
        self.profiles_panel.setObjectName("Panel")
        self.profiles_panel.setFixedWidth(220)

        outer.addWidget(sidebar)
        outer.addWidget(_vseparator())
        outer.addLayout(canvas_column)
        outer.addWidget(_vseparator())
        outer.addWidget(self.profiles_panel)

        self._mr_active = False
        self.canvas.zone_clicked.connect(sidebar.sync_target)
        self.canvas.mkey_clicked.connect(self.on_mkey_clicked)
        self.canvas.color_applied.connect(sidebar._stop_effect)

    def on_mkey_clicked(self, name):
        if name == "MR":
            self._mr_active = not self._mr_active
            ok, err = bl.set_mrkey_led(self._mr_active)
            if not ok:
                print(f"FAILED to toggle MR LED: {err}")
                self._mr_active = not self._mr_active  # revert, the LED didn't actually change
                return
            self.canvas.set_mr_active(self._mr_active)
        else:
            self.gkeys_panel.select_profile(name)


# --- G-Key Macros panel (embedded in MainView; ported from
# g510_app.py's proven pattern) --------------------------------------

def load_macros():
    if MACROS_FILE.exists():
        try:
            return json.loads(MACROS_FILE.read_text())
        except Exception:
            pass
    return {"M1": {}, "M2": {}, "M3": {}}


def save_macro(profile, gkey, value, kind="keys"):
    macros = load_macros()
    macros.setdefault(profile, {})[gkey] = {"type": kind, "value": value}
    MACROS_FILE.write_text(json.dumps(macros, indent=2))


def clear_macro(profile, gkey):
    macros = load_macros()
    macros.setdefault(profile, {}).pop(gkey, None)
    MACROS_FILE.write_text(json.dumps(macros, indent=2))


class RecorderThread(QThread):
    """Captures real keystrokes from the main keyboard while recording,
    grabbing the device so they don't also leak into whatever window has
    focus. Emits the final ydotool-ready 'code:value code:value ...'
    string when stopped. Same pattern as g510_app.py's RecorderThread,
    just pointed at the G910's confirmed typing device."""
    finished_recording = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._stop = False
        self._events = []

    def stop(self):
        self._stop = True

    def run(self):
        dev = evdev.InputDevice(MAIN_KEYBOARD_DEVICE)
        dev.grab()
        try:
            while not self._stop:
                r, _, _ = select.select([dev.fd], [], [], 0.1)
                if not r:
                    continue
                for event in dev.read():
                    if event.type == ecodes.EV_KEY:
                        self._events.append(f"{event.code}:{event.value}")
        finally:
            dev.ungrab()
            dev.close()
        self.finished_recording.emit(" ".join(self._events))


class MacroRecordDialog(QDialog):
    def __init__(self, profile, gkey, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.gkey = gkey
        self.recorder = None
        self.recorded_sequence = None

        self.setWindowTitle(f"{profile} / {gkey}")
        layout = QVBoxLayout()

        macros = load_macros()
        existing = macros.get(profile, {}).get(gkey)
        if isinstance(existing, dict) and existing.get("type") == "command":
            status_text = f"Currently runs: {existing.get('value', '')}"
        elif existing:
            status_text = "Currently assigned (recorded keystrokes)."
        else:
            status_text = "Nothing assigned yet."
        self.status_label = QLabel(status_text)
        layout.addWidget(self.status_label)

        self.record_btn = QPushButton("Record")
        self.record_btn.clicked.connect(self.toggle_recording)
        layout.addWidget(self.record_btn)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.on_save)
        # Deliberately NOT disabled when nothing's recorded -- a
        # disabled button that silently does nothing when clicked is
        # indistinguishable from a broken Save, confirmed as a real
        # confusing UX gap while testing this. on_save() below shows a
        # clear message instead when there's nothing to save.
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.on_clear)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("<b>Or run a command instead:</b>"))
        cmd_row = QHBoxLayout()
        self.command_edit = QLineEdit()
        self.command_edit.setPlaceholderText("e.g. notify-send hello")
        if isinstance(existing, dict) and existing.get("type") == "command":
            self.command_edit.setText(existing.get("value", ""))
        save_cmd_btn = QPushButton("Save Command")
        save_cmd_btn.clicked.connect(self.on_save_command)
        cmd_row.addWidget(self.command_edit)
        cmd_row.addWidget(save_cmd_btn)
        layout.addLayout(cmd_row)

        self.setLayout(layout)

    def toggle_recording(self):
        if self.recorder is None:
            if MAIN_KEYBOARD_DEVICE is None:
                self.status_label.setText("No G910 keyboard found -- is it plugged in?")
                return
            self.status_label.setText("Recording... press your key combo, then click Stop.")
            self.record_btn.setText("Stop")
            self.recorder = RecorderThread()
            self.recorder.finished_recording.connect(self.on_recorded)
            self.recorder.start()
        else:
            self.record_btn.setEnabled(False)
            self.status_label.setText("Stopping...")
            self.recorder.stop()

    def reject(self):
        if self.recorder is not None:
            self.recorder.stop()
            self.recorder.wait(2000)
        super().reject()

    def on_recorded(self, sequence):
        self.recorded_sequence = sequence
        if self.recorder is not None:
            self.recorder.wait()
        self.recorder = None
        self.record_btn.setText("Record")
        self.record_btn.setEnabled(True)
        if sequence:
            self.status_label.setText(f"Captured {len(sequence.split())} events. Click Save to keep it.")
        else:
            self.status_label.setText("Nothing was captured -- press a key while it says \"Recording...\", then Stop.")

    def on_save(self):
        if not self.recorded_sequence:
            QMessageBox.warning(
                self, "Nothing recorded",
                "No keys were captured. Click Record, press the key combo, then Stop before Save.",
            )
            return
        save_macro(self.profile, self.gkey, self.recorded_sequence, kind="keys")
        self.accept()

    def on_save_command(self):
        cmd = self.command_edit.text().strip()
        if cmd:
            save_macro(self.profile, self.gkey, cmd, kind="command")
        self.accept()

    def on_clear(self):
        clear_macro(self.profile, self.gkey)
        self.accept()


class GKeysTab(QWidget):
    """M1/M2/M3 profile toggle + G1-G9 macro buttons, as a single
    compact horizontal strip -- lives directly under the canvas (see
    MainView), not in its own tab/panel, so it has to be short.
    MR is intentionally NOT a profile here -- it's a literal
    macro-record toggle for the future physical-key-driven daemon, not
    a 4th GUI profile (the user's explicit decision earlier in this
    project)."""
    def __init__(self, canvas=None):
        super().__init__()
        self.canvas = canvas
        self.current_profile = "M1"

        # Wrapped in its own QVBoxLayout with a thin rule on top -- real
        # complaint from live use: sitting directly under the canvas
        # with no visual break, this strip read as part of the keyboard
        # image rather than its own distinct macro-editing section.
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        outer.addWidget(_hseparator())

        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        label = QLabel("Add New Macro")
        layout.addWidget(label)
        layout.addSpacing(12)

        self.profile_buttons = {}
        for name in ("M1", "M2", "M3"):
            btn = QPushButton(name)
            btn.setObjectName("ZoneButton")
            btn.setCheckable(True)
            btn.setFixedWidth(42)
            btn.clicked.connect(lambda _, n=name: self.select_profile(n))
            layout.addWidget(btn)
            self.profile_buttons[name] = btn

        layout.addSpacing(12)
        layout.addWidget(_vseparator())
        layout.addSpacing(12)

        self.key_buttons = {}
        for i in range(1, 10):
            name = f"G{i}"
            btn = QPushButton(name)
            btn.setObjectName("ZoneButton")
            btn.setFixedWidth(46)
            btn.clicked.connect(lambda _, n=name: self.open_key_dialog(n))
            layout.addWidget(btn)
            self.key_buttons[name] = btn

        outer.addLayout(layout)
        self.setLayout(outer)
        self.select_profile("M1")  # also lights the LED + syncs the canvas highlight

        # Physical M1/M2/M3 presses go through g910_macro_daemon.py
        # (not this app -- confirmed there's no listener here at all,
        # that daemon is what closes the gap), which writes the active
        # profile to a status file. Poll it so the GUI follows physical
        # presses too, not just its own buttons -- same pattern as the
        # G510s app's poll_active_profile.
        self.profile_poll_timer = QTimer(self)
        self.profile_poll_timer.timeout.connect(self.poll_active_profile)
        self.profile_poll_timer.start(500)

    def select_profile(self, name):
        self.current_profile = name
        for n, btn in self.profile_buttons.items():
            btn.setChecked(n == name)
        ok, err = bl.set_mkey_led(name)
        if not ok:
            print(f"FAILED to light {name} LED: {err}")
        if self.canvas is not None:
            self.canvas.set_active_mkey(name)
        self._write_active_profile(name)
        self.refresh_assigned_keys()

    def _write_active_profile(self, name):
        """Real bug found and fixed: clicking M1/M2/M3 here used to
        only update the LED/canvas -- never told g910_macro_daemon.py,
        so a real G-key press right after would replay the OLD
        profile's macro while the screen showed the new one, and
        poll_active_profile() below would silently revert the GUI back
        within ~500ms since this file never changed. Same class of bug
        found and fixed on the sibling G510s app/daemon. The daemon now
        reads this file back on every wake (see its read_active_profile
        docstring), not just when it writes it itself on a physical
        M-key press."""
        import os
        runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        Path(runtime, "g910_macro_profile").write_text(name)

    def refresh_assigned_keys(self):
        """Gold border on G-keys with a macro saved in the CURRENT
        profile, so it's visible at a glance which keys are already
        programmed without opening every dialog -- requested by the
        user, matching what the sibling G510s app's canvas just got."""
        assigned = load_macros().get(self.current_profile, {})
        for name, btn in self.key_buttons.items():
            btn.setStyleSheet("border: 2px solid #d4af37;" if name in assigned else "")

    def poll_active_profile(self):
        import os
        runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        profile_file = Path(runtime, "g910_macro_profile")
        try:
            live = profile_file.read_text().strip()
        except Exception:
            return
        if live in self.profile_buttons and live != self.current_profile:
            self.select_profile(live)

    def open_key_dialog(self, gkey):
        dlg = MacroRecordDialog(self.current_profile, gkey, self)
        dlg.exec_()
        self.refresh_assigned_keys()  # macro may have just been saved/cleared


# --- Profiles tab: save/load full lighting snapshots -------------------

class ProfilesTab(QWidget):
    """Save the CURRENT live color of every key (across keys/gkeys/logo
    -- media excluded, see g910_backlight.PROFILE_BLOCKS) as a named
    profile; load a saved one back to instantly reapply that whole
    combination. Backend already verified directly against the real
    device before this UI was wired to it -- save/load/delete/list all
    confirmed working (real snapshot captured, real color match
    confirmed after replay). Takes MainView's canvas so a
    successful Load can refresh the preview to match -- otherwise the
    canvas would keep showing whatever was there before the load."""
    def __init__(self, canvas, sidebar):
        super().__init__()
        self.canvas = canvas
        # Needed to stop any running EffectThread before a save/load --
        # confirmed via a real concurrent test that keyledsctl get-leds
        # genuinely fails ("invalid response from device") when it
        # races against a concurrent set-leds write from an effect
        # still running. Not an application bug to work around with
        # retries -- a real HID++ protocol-level conflict from two
        # processes hitting the same device at once.
        self.sidebar = sidebar
        layout = QVBoxLayout()
        layout.setContentsMargins(14, 14, 14, 14)

        title = QLabel("Profiles")
        title.setObjectName("Title")
        layout.addWidget(title)

        layout.addSpacing(6)
        save_btn = QPushButton("Save Current as Profile...")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self.on_save)
        layout.addWidget(save_btn)

        layout.addSpacing(8)
        layout.addWidget(QLabel("<b>Saved profiles</b>"))

        # Real bug found via live use: with no scroll area, saving
        # enough profiles to exceed the window's height just laid the
        # extra rows out past the bottom edge -- invisible, unreachable,
        # no scrollbar, nothing telling you they were even still there
        # (they were: this is purely a rendering bug, the data was
        # always intact in g910_profiles.json). Wrapping the list in a
        # QScrollArea instead of adding it to the panel directly means
        # any number of saved profiles stay reachable by scrolling.
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(4)
        self.list_container = QWidget()
        self.list_container.setLayout(self.list_layout)
        self.profiles_scroll = QScrollArea()
        self.profiles_scroll.setWidgetResizable(True)
        self.profiles_scroll.setFrameShape(QFrame.NoFrame)
        self.profiles_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # A SIMPLE static cap, deliberately -- a previous attempt tried
        # to compute this height dynamically from list_container's own
        # sizeHint() every refresh (to shrink for a short list, cap for
        # a long one), but that self-referential adjustSize()/sizeHint()
        # call, re-run on top of whatever the PREVIOUS refresh had
        # already set, compounded into worse and worse states as more
        # profiles were added -- confirmed via a real screenshot after
        # a second save: overlapping, garbled, near-unreadable cards.
        # 160px (roughly 2-3 cards at their normal, unshrunk size) plus
        # addStretch() below is simple, deterministic Qt with no
        # feedback loop: few profiles sit compact with blank space
        # below them (not stretched into), more than that scrolls.
        self.profiles_scroll.setMaximumHeight(160)
        self.profiles_scroll.setWidget(self.list_container)
        layout.addWidget(self.profiles_scroll)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Status")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()  # leftover space collects here, below everything, not inside the capped scroll box
        self.setLayout(layout)

        self.refresh_list()

    def refresh_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        names = bl.list_profiles()
        if not names:
            self.list_layout.addWidget(QLabel("No profiles saved yet."))
            self.list_layout.addStretch()
            return
        for name in names:
            # Stacked (name above Load/Delete), not side-by-side -- a
            # single row ran out of horizontal space for long names
            # once the scroll area's own scrollbar (added for the
            # overflow fix above) ate into this already-narrow 220px
            # panel, and a fixed width can never truly be "wide enough"
            # for an arbitrary user-typed name anyway. Stacking is
            # robust to any name length instead of guessing a width.
            # Deliberately plain/default sizing here (normal font,
            # normal ZoneButton padding, no custom shrinking tricks) --
            # two separate attempts at a smaller custom card (a forced
            # setFixedHeight that clipped the button text, then a
            # smaller font + padding combo that still produced garbled
            # overlapping cards once a second profile existed) both
            # made things worse -- but the root cause of THAT was the
            # missing Fixed size policy below, not the smaller padding
            # itself. Now that every card is pinned to Fixed, this same
            # compact padding (verified via fontMetrics().height()==24
            # against this stylesheet's font, so "padding: 1px 8px"
            # -> a real sizeHint of 28px, never clipping the text the
            # way the earlier guessed setFixedHeight(16) did) is safe
            # to reapply -- re-tested with 0/1/2/3 profiles below
            # before shipping, not just assumed safe from the theory.
            entry = QVBoxLayout()
            entry.setContentsMargins(6, 0, 6, 0)
            entry.setSpacing(0)
            name_label = QLabel(name)
            name_label.setWordWrap(True)
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setStyleSheet("font-size: 10px;")
            entry.addWidget(name_label)
            btn_row = QHBoxLayout()
            btn_row.setSpacing(3)
            load_btn = QPushButton("Load")
            load_btn.setObjectName("ZoneButton")
            load_btn.setStyleSheet("padding: 1px 8px;")
            load_btn.clicked.connect(lambda _, n=name: self.on_load(n))
            delete_btn = QPushButton("Delete")
            delete_btn.setObjectName("ZoneButton")
            delete_btn.setStyleSheet("padding: 1px 8px;")
            delete_btn.clicked.connect(lambda _, n=name: self.on_delete(n))
            btn_row.addWidget(load_btn)
            btn_row.addWidget(delete_btn)
            entry.addLayout(btn_row)
            # Distinct "Card" background (not "Panel", the same shade as
            # this whole panel's own background) -- real contrast bug
            # found via live use: cards were invisible as distinct
            # elements since they shared the exact same fill as their
            # own parent, giving zero visual separation between them.
            container = QWidget()
            container.setObjectName("Card")
            container.setLayout(entry)
            # Fixed vertical size policy -- the real root cause behind
            # BOTH previous bugs (cards inflating to ~90px with few
            # profiles, then cards compressing to ~36px/garbled with
            # more than fit in the scroll cap): a default Preferred
            # policy lets Qt grow OR shrink a widget away from its own
            # sizeHint whenever the layout has slack either direction.
            # Fixed means only the scroll AREA's viewport size changes;
            # each card always renders at exactly its own sizeHint, and
            # a real vertical scrollbar (default policy, never disabled
            # above) takes over once more cards exist than the capped
            # height can show -- confirmed via a 0/1/2/5/1-profile
            # stress test before shipping this, not just a 1-profile
            # check like the last two attempts.
            container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.list_layout.addWidget(container)

        # Real bug found via live use: with no trailing stretch, Qt's
        # box layout let the LAST card grow to fill whatever height the
        # scroll viewport happened to have (Preferred size policy
        # allows growth when nothing else claims the leftover space) --
        # a single profile ended up a ~90px-tall box with Load/Delete
        # squeezed into the very bottom edge, despite the card's own
        # sizeHint being ~60px. addStretch() gives that leftover space
        # somewhere else to go, so every card always renders at its own
        # natural size regardless of how much room the viewport has.
        self.list_layout.addStretch()

    def on_save(self):
        name, ok = QInputDialog.getText(self, "Save Profile", "Profile name:")
        name = name.strip()
        if not ok or not name:
            return
        if name in bl.list_profiles():
            confirm = QMessageBox.question(
                self, "Overwrite?", f'A profile named "{name}" already exists. Overwrite it?',
            )
            if confirm != QMessageBox.Yes:
                return
        # Capture what's running BEFORE stopping it -- stopping first
        # would lose exactly the information being saved. speed_pct
        # and (for breathing) the real base colour come straight off
        # the live thread's own attributes, not re-derived from
        # whatever the hex field/slider happen to show right now.
        effect = None
        thread = self.sidebar.effect_thread
        if thread is not None:
            effect = {"kind": thread.kind, "target": self.sidebar.current_target, "speed_pct": thread.speed_pct}
            if thread.kind == "breathing":
                effect["base_rgb"] = list(thread.base_rgb)
        # A running effect keeps writing to the device -- confirmed
        # live that a concurrent get-leds read genuinely fails
        # ("invalid response from device") against that, not just a
        # theoretical risk. Stop it AFTER capturing the above, so the
        # snapshot itself is real.
        self.sidebar._stop_effect()
        success, err = bl.save_profile(name, effect=effect)
        if success:
            self.status_label.setText(f'Saved current lighting as "{name}".')
            self.refresh_list()
        else:
            self.status_label.setText(f"FAILED: {err}")

    def on_load(self, name):
        self.sidebar._stop_effect()  # same device-contention reason as on_save
        success, err, effect = bl.load_profile(name)
        if not success:
            self.status_label.setText(f"FAILED: {err}")
            return
        self.canvas.sync_from_device()
        if effect:
            # Resume whatever was actually animating when this was
            # saved, not just show the one frozen frame the static
            # snapshot above already applied. select_target sets
            # current_target (which _start_effect reads); for
            # breathing, the real saved base colour goes into the hex
            # field first since that's what _start_effect reads its
            # base_rgb from -- same field, just populated from the
            # profile instead of whatever a user happened to type.
            self.sidebar.select_target(effect["target"])
            if effect["kind"] == "breathing" and "base_rgb" in effect:
                r, g, b = effect["base_rgb"]
                self.sidebar.hex_edit.setText("%02x%02x%02x" % (r, g, b))
            self.sidebar.speed_slider.setValue(effect.get("speed_pct", 100))
            self.sidebar._start_effect(effect["kind"])
            names = {"breathing": "Breathing", "cycle": "Colour Cycle", "wave": "Rainbow Wave"}
            self.status_label.setText(f'Loaded "{name}" -- resuming {names[effect["kind"]]}.')
        else:
            self.status_label.setText(f'Loaded "{name}".')

    def on_delete(self, name):
        confirm = QMessageBox.question(self, "Delete profile?", f'Delete "{name}"?')
        if confirm != QMessageBox.Yes:
            return
        success, err = bl.delete_profile(name)
        if success:
            self.status_label.setText(f'Deleted "{name}".')
            self.refresh_list()
        else:
            self.status_label.setText(f"FAILED: {err}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G910 Control")
        self.setStyleSheet(STYLESHEET)

        # No tabs anymore -- Backlight/G-Keys/Profiles are all one
        # single view now (G-Keys and Profiles used to be separate
        # tabs, moved in one at a time into what used to be empty
        # space around the canvas, by request).
        self.setCentralWidget(MainView())

        # Size to the actual content instead of a hardcoded guess --
        # was 1500x460, but the real layout needs less width than that
        # (left a real, visible empty gap on the right of the window).
        # adjustSize() sizes to the layout's real sizeHint, so this
        # keeps tracking reality as panels change instead of rotting
        # into another stale hardcoded number.
        self.adjustSize()

        # Real bug found via live use: the sidebar/profiles panels'
        # scroll areas each have a setMaximumHeight() cap so THEIR
        # natural full-content size doesn't drag adjustSize() above --
        # but that same cap also blocked them from ever growing again,
        # even if the user manually dragged the window taller
        # afterward. The cap only needs to apply for this one
        # calculation above; relax it immediately after so the panels
        # are free to actually use any extra space a manual resize
        # provides, instead of leaving it as dead space below them.
        for scroll_area in self.findChildren(QScrollArea):
            scroll_area.setMaximumHeight(16777215)  # Qt's own QWIDGETSIZE_MAX

    def closeEvent(self, event):
        # A running EffectThread would otherwise be destroyed while
        # still alive when this window closes -- Qt warns loudly about
        # that at best, and it's a real dangling-thread/background-
        # subprocess risk at worst. Stop it cleanly first.
        sidebar = self.findChildren(ColorModeSidebar)
        if sidebar:
            sidebar[0]._stop_effect()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
