#!/usr/bin/env python3
"""
G910 keyboard canvas -- real per-key geometry, QPainter rendering,
rect-based hit-testing, click + drag/multi-select (Ctrl+drag XORs the
selection, adapted from OpenRGB's DeviceView.cpp mouse handlers).

Position/gap data for the main board ported from Solaar's
ui/perkey/layouts/_keyboard_base.py (itself ported from OpenRGB's
KeyboardLayoutManager.cpp, GPL-2.0-or-later) -- real column positions
and inter-group gaps, cross-checked against our own confirmed
keyledsctl key names. Widths for keys that data doesn't cover (only
Space and the numpad 0 key have real width overrides there) are
standard ANSI keycap proportions, supplied here. G-keys/M-keys/Logo
positions are ours -- no external source covers this keyboard's
specific layout for those.
"""
import sys
from collections import Counter
from dataclasses import dataclass
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QFont
from PyQt5.QtWidgets import QWidget, QColorDialog, QApplication

import g910_backlight as bl

CELL_PX = 34
GUTTER_PX = 4
PADDING_PX = 10


@dataclass
class Cell:
    key_name: str       # real keyledsctl name, or None for inert placeholders
    label: str           # what's drawn on the key
    row: float
    col: float
    width: float = 1.0
    height: float = 1.0
    block: str = "keys"  # "keys" / "gkeys" / "logo" / None (M-keys only, no
                          # bulk mechanism reaches them at all)
    # False for Win/Alt/AltGr/Menu/right-Ctrl/right-Shift specifically:
    # confirmed via direct live testing they have NO individual per-key
    # LED (rejected by name, never appear in get-leds's per-key listing)
    # but DO respond to the whole-block "all=" fill (keyleds_set_led_block,
    # a different HID++ function than per-key set_leds -- confirmed via
    # keyledsctl_set_leds.c's real source). So they're colorable via
    # Main Board's bulk apply but can't be clicked individually on the
    # canvas -- see set_main_board_color()'s docstring for the full fix.
    individually_colorable: bool = True


# --- M-keys + MR (row -2, ABOVE G6-G9's row -- was colliding with
# them at row -1 before, M3/G6 landed on the exact same cell) ---
MKEY_CELLS = [
    Cell(None, "M1", -2, 0, block=None),
    Cell(None, "M2", -2, 1, block=None),
    Cell(None, "M3", -2, 2, block=None),
    Cell(None, "MR", -2, 3, block=None),
]

# --- Logo, between the M-keys and the G1 column (matches reference).
# height=1.0, not 2.2 -- that was overlapping G1's cell below it.
LOGO_CELLS = [
    Cell("LOGO1", "G", -1, -1.3, width=0.9, height=1.0, block="logo"),
]

# --- G-keys: G1-G5 left column, G6-G9 top row above F1-F4 ---
GKEY_LEFT_CELLS = [Cell(f"G{i}", f"G{i}", i, -1.3, width=0.9) for i in range(1, 6)]
GKEY_TOP_CELLS = [Cell(f"G{i}", f"G{i}", -1, i - 4, block="gkeys") for i in range(6, 10)]
for c in GKEY_LEFT_CELLS:
    c.block = "gkeys"

# --- Main board, positions from Solaar's MAIN_ANSI/FN_ROW/EXTRAS data,
# widths supplied where that data defaults to 1.0 but the real key is
# wider (standard ANSI keycap proportions).
MAIN_CELLS = [
    # F-row
    Cell("ESC", "Esc", 0, 0), Cell("F1", "F1", 0, 2), Cell("F2", "F2", 0, 3),
    Cell("F3", "F3", 0, 4), Cell("F4", "F4", 0, 5), Cell("F5", "F5", 0, 6),
    Cell("F6", "F6", 0, 7), Cell("F7", "F7", 0, 8), Cell("F8", "F8", 0, 9),
    Cell("F9", "F9", 0, 10), Cell("F10", "F10", 0, 11), Cell("F11", "F11", 0, 12),
    Cell("F12", "F12", 0, 13),
    # number row
    Cell("GRAVE", "`", 1, 0), Cell("1", "1", 1, 1), Cell("2", "2", 1, 2),
    Cell("3", "3", 1, 3), Cell("4", "4", 1, 4), Cell("5", "5", 1, 5),
    Cell("6", "6", 1, 6), Cell("7", "7", 1, 7), Cell("8", "8", 1, 8),
    Cell("9", "9", 1, 9), Cell("0", "0", 1, 10), Cell("MINUS", "-", 1, 11),
    Cell("EQUAL", "=", 1, 12), Cell("BACKSPACE", "Bksp", 1, 13, width=2.0),
    # qwerty row
    Cell("TAB", "Tab", 2, 0, width=1.5), Cell("Q", "Q", 2, 1.5), Cell("W", "W", 2, 2.5),
    Cell("E", "E", 2, 3.5), Cell("R", "R", 2, 4.5), Cell("T", "T", 2, 5.5),
    Cell("Y", "Y", 2, 6.5), Cell("U", "U", 2, 7.5), Cell("I", "I", 2, 8.5),
    Cell("O", "O", 2, 9.5), Cell("P", "P", 2, 10.5), Cell("LBRACE", "[", 2, 11.5),
    Cell("RBRACE", "]", 2, 12.5), Cell("BACKSLASH", "\\", 2, 13.5, width=1.5),
    # asdf row
    Cell("CAPSLOCK", "Caps", 3, 0, width=1.75), Cell("A", "A", 3, 1.75),
    Cell("S", "S", 3, 2.75), Cell("D", "D", 3, 3.75), Cell("F", "F", 3, 4.75),
    Cell("G", "G", 3, 5.75), Cell("H", "H", 3, 6.75), Cell("J", "J", 3, 7.75),
    Cell("K", "K", 3, 8.75), Cell("L", "L", 3, 9.75), Cell("SEMICOLON", ";", 3, 10.75),
    Cell("APOSTROPHE", "'", 3, 11.75), Cell("ENTER", "Enter", 3, 12.75, width=2.25),
    # zxcv row
    Cell("LSHIFT", "Shift", 4, 0, width=2.25), Cell("Z", "Z", 4, 2.25),
    Cell("X", "X", 4, 3.25), Cell("C", "C", 4, 4.25), Cell("V", "V", 4, 5.25),
    Cell("B", "B", 4, 6.25), Cell("N", "N", 4, 7.25), Cell("M", "M", 4, 8.25),
    Cell("COMMA", ",", 4, 9.25), Cell("DOT", ".", 4, 10.25), Cell("SLASH", "/", 4, 11.25),
    Cell("_RSHIFT", "Shift", 4, 12.25, width=2.75, block="keys", individually_colorable=False),
    # bottom row
    Cell("LCTRL", "Ctrl", 5, 0, width=1.25),
    Cell("_LWIN", "Win", 5, 1.25, width=1.25, block="keys", individually_colorable=False),
    Cell("_LALT", "Alt", 5, 2.5, width=1.25, block="keys", individually_colorable=False),
    Cell("SPACE", "Space", 5, 3.75, width=6.25),
    Cell("_ALTGR", "AltGr", 5, 10.0, width=1.25, block="keys", individually_colorable=False),
    Cell("_RWIN", "Win", 5, 11.25, width=1.25, block="keys", individually_colorable=False),
    Cell("_MENU", "Menu", 5, 12.5, width=1.25, block="keys", individually_colorable=False),
    Cell("_RCTRL", "Ctrl", 5, 13.75, width=1.25, block="keys", individually_colorable=False),
]

NAV_COL0 = 15.5  # one gap column right of the main board (main board ends ~col15)
NAV_CELLS = [
    Cell("SYSRQ", "PrtSc", 0, NAV_COL0), Cell("SCROLLLOCK", "ScrLk", 0, NAV_COL0 + 1),
    Cell("PAUSE", "Pause", 0, NAV_COL0 + 2),
    Cell("INSERT", "Ins", 1, NAV_COL0), Cell("HOME", "Home", 1, NAV_COL0 + 1),
    Cell("PAGEUP", "PgUp", 1, NAV_COL0 + 2),
    Cell("DELETE", "Del", 2, NAV_COL0), Cell("END", "End", 2, NAV_COL0 + 1),
    Cell("PAGEDOWN", "PgDn", 2, NAV_COL0 + 2),
    Cell("UP", "↑", 4, NAV_COL0 + 1),
    Cell("LEFT", "←", 5, NAV_COL0), Cell("DOWN", "↓", 5, NAV_COL0 + 1),
    Cell("RIGHT", "→", 5, NAV_COL0 + 2),
]

NUMPAD_COL0 = NAV_COL0 + 4  # one gap column right of the nav cluster
NUMPAD_CELLS = [
    Cell("NUMLOCK", "Num", 1, NUMPAD_COL0), Cell("KPSLASH", "/", 1, NUMPAD_COL0 + 1),
    Cell("KPASTERISK", "*", 1, NUMPAD_COL0 + 2), Cell("KPMINUS", "-", 1, NUMPAD_COL0 + 3),
    Cell("KP7", "7", 2, NUMPAD_COL0), Cell("KP8", "8", 2, NUMPAD_COL0 + 1),
    Cell("KP9", "9", 2, NUMPAD_COL0 + 2), Cell("KPPLUS", "+", 2, NUMPAD_COL0 + 3, height=2.0),
    Cell("KP4", "4", 3, NUMPAD_COL0), Cell("KP5", "5", 3, NUMPAD_COL0 + 1),
    Cell("KP6", "6", 3, NUMPAD_COL0 + 2),
    Cell("KP1", "1", 4, NUMPAD_COL0), Cell("KP2", "2", 4, NUMPAD_COL0 + 1),
    Cell("KP3", "3", 4, NUMPAD_COL0 + 2), Cell("KPENTER", "Enter", 4, NUMPAD_COL0 + 3, height=2.0),
    Cell("KP0", "0", 5, NUMPAD_COL0, width=2.0), Cell("KPDOT", ".", 5, NUMPAD_COL0 + 2),
]

ALL_CELLS = MKEY_CELLS + LOGO_CELLS + GKEY_LEFT_CELLS + GKEY_TOP_CELLS + MAIN_CELLS + NAV_CELLS + NUMPAD_CELLS

# Zone name -> set of real key_names, for the Color Mode sidebar to
# highlight on the canvas and preview colors against. Mirrors
# g910_backlight.GROUPS but sourced from our own local cell data
# (no live device query needed just to compute a selection preview).
_FUNCTION_ROW_KEYS = {c.key_name for c in MAIN_CELLS if c.key_name and c.key_name.startswith("F") and c.key_name[1:].isdigit()}
_NUMPAD_KEYS = {c.key_name for c in NUMPAD_CELLS if c.key_name}
_NAV_CLUSTER_KEYS = {c.key_name for c in NAV_CELLS if c.key_name}
_GKEY_KEYS = {c.key_name for c in (GKEY_LEFT_CELLS + GKEY_TOP_CELLS) if c.key_name}
_LOGO_KEYS = {c.key_name for c in LOGO_CELLS if c.key_name}
# MAIN_CELLS never contains numpad/nav-cluster keys (those come from
# separate lists), so this only needs to exclude F1-F12 -- and the "_"
# prefixed placeholder names (inert cells with no real addressable LED
# on this hardware, e.g. _LWIN/_RCTRL -- confirmed empirically much
# earlier: only LCTRL/LSHIFT exist among modifiers). Those placeholders
# exist purely so each inert cell can be individually selected for
# visual highlighting -- they must NEVER be sent to keyledsctl, since
# they aren't real key names it would accept.
_MAIN_BOARD_KEYS = {
    c.key_name for c in MAIN_CELLS
    if c.key_name and c.key_name not in _FUNCTION_ROW_KEYS and not c.key_name.startswith("_")
}
# Visual-only: same as above but INCLUDING the inert placeholder cells,
# so selecting "Main Board" highlights the whole physical area (Win/
# Alt/AltGr/Menu/right-Ctrl/right-Shift included) even though those
# specific keys can't actually receive a color.
_MAIN_BOARD_VISUAL_KEYS = {
    c.key_name for c in MAIN_CELLS
    if c.key_name and c.key_name not in _FUNCTION_ROW_KEYS
}

ZONE_KEYS = {
    "Logo": _LOGO_KEYS,
    "G-Keys": _GKEY_KEYS,
    "F1-F12": _FUNCTION_ROW_KEYS,
    "Numpad": _NUMPAD_KEYS,
    "Nav Cluster": _NAV_CLUSTER_KEYS,
    "Main Board": _MAIN_BOARD_KEYS,
}

# What gets HIGHLIGHTED when a zone is selected -- identical to
# ZONE_KEYS except Main Board additionally highlights the inert
# placeholder keys. Use this for canvas.select_keys(), and ZONE_KEYS
# (only) for anything that actually applies/previews a color.
ZONE_SELECTION_KEYS = dict(ZONE_KEYS)
ZONE_SELECTION_KEYS["Main Board"] = _MAIN_BOARD_VISUAL_KEYS

# Colors -- dark, clean, simple. No logos, no glossy 3D key art.
BG_COLOR = QColor(0x17, 0x17, 0x1a)  # matches g910_app.py's sidebar background
KEY_UNSET_COLOR = QColor(42, 42, 46)
KEY_INERT_COLOR = QColor(30, 30, 33)
KEY_BORDER_COLOR = QColor(10, 10, 12)
SELECTION_BORDER_COLOR = QColor(70, 140, 230)
LABEL_INERT_COLOR = QColor(90, 90, 95)


class KeyboardCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self._colors = {}  # key_name -> QColor, unset keys use KEY_UNSET_COLOR
        self._selection = set()  # set of key_name currently selected
        self._press_pos = None
        self._drag_rect = None
        self._ctrl_down = False
        self._previous_selection = set()
        self.setMouseTracking(True)
        self._compute_size()
        self.sync_from_device()

    def sync_from_device(self):
        """Query the device's ACTUAL current colors and populate the
        preview from them, so the app reflects real state on open
        instead of starting blank.

        The six individually-unaddressable keys (Win/Alt/AltGr/Menu/
        right-Ctrl/right-Shift) never appear in the device's per-key
        report -- confirmed empirically, see the Cell dataclass comment
        -- so we can't read their real color directly. But we know how
        they're actually colored in practice: Main Board's "all=" bulk
        fill (keyleds_set_led_block) reaches them too, and nothing else
        does. So on sync we approximate their color as the most common
        color among the rest of the (individually-addressable) Main
        Board keys -- exactly right after a solid fill, which is the
        only way these keys get colored at all today."""
        live = bl.get_all_live_colors()
        for name, hexcolor in live.items():
            self._colors[name] = QColor(hexcolor)

        main_board_colors = [
            self._colors[c.key_name] for c in ALL_CELLS
            if c.block == "keys" and c.individually_colorable
            and c.key_name in self._colors
        ]
        if main_board_colors:
            counts = Counter(c.name() for c in main_board_colors)
            dominant = QColor(counts.most_common(1)[0][0])
            for c in ALL_CELLS:
                if c.block == "keys" and not c.individually_colorable:
                    self._colors[c.key_name] = dominant

        self.update()

    def select_keys(self, key_names):
        """Replace the current selection with an explicit set of real
        key names -- used by the Color Mode sidebar's zone buttons."""
        self._selection = set(key_names)
        self.update()

    def set_colors(self, key_names, qcolor):
        """Update the local color preview for a set of keys, without
        touching selection -- used after the sidebar successfully
        applies a color, so the canvas shows what was actually sent."""
        for name in key_names:
            self._colors[name] = qcolor
        self.update()

    def _compute_size(self):
        min_row = min(c.row for c in ALL_CELLS)
        min_col = min(c.col for c in ALL_CELLS)
        max_row_bottom = max(c.row + c.height for c in ALL_CELLS)
        max_col_right = max(c.col + c.width for c in ALL_CELLS)
        rows = max_row_bottom - min_row
        cols = max_col_right - min_col
        w = int(PADDING_PX * 2 + cols * (CELL_PX + GUTTER_PX))
        h = int(PADDING_PX * 2 + rows * (CELL_PX + GUTTER_PX))
        self._row_offset = -min_row
        self._col_offset = -min_col
        self.setMinimumSize(w, h)

    def _cell_rect(self, cell):
        x = PADDING_PX + (cell.col + self._col_offset) * (CELL_PX + GUTTER_PX)
        y = PADDING_PX + (cell.row + self._row_offset) * (CELL_PX + GUTTER_PX)
        w = cell.width * CELL_PX + max(0.0, cell.width - 1.0) * GUTTER_PX
        h = cell.height * CELL_PX + max(0.0, cell.height - 1.0) * GUTTER_PX
        return QRectF(x, y, w, h)

    def _cell_at(self, point):
        for cell in ALL_CELLS:
            if self._cell_rect(cell).contains(point):
                return cell
        return None

    def _label_color(self, fill):
        if fill is None:
            return LABEL_INERT_COLOR
        lum = 0.299 * fill.redF() + 0.587 * fill.greenF() + 0.114 * fill.blueF()
        return QColor(0, 0, 0) if lum > 0.55 else QColor(255, 255, 255)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), BG_COLOR)
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)

        for cell in ALL_CELLS:
            rect = self._cell_rect(cell)
            path = QPainterPath()
            path.addRoundedRect(rect, 4, 4)

            if cell.block is None:
                fill = KEY_INERT_COLOR
            else:
                fill = self._colors.get(cell.key_name, KEY_UNSET_COLOR)

            painter.fillPath(path, fill)
            border = SELECTION_BORDER_COLOR if cell.key_name in self._selection else KEY_BORDER_COLOR
            pen_width = 2 if cell.key_name in self._selection else 1
            painter.setPen(Qt.NoPen)
            painter.strokePath(path, painter.pen())
            from PyQt5.QtGui import QPen
            painter.setPen(QPen(border, pen_width))
            painter.drawPath(path)

            painter.setPen(self._label_color(fill if cell.block is not None else None))
            painter.drawText(rect, Qt.AlignCenter, cell.label)

        if self._drag_rect is not None:
            painter.setPen(QPen(SELECTION_BORDER_COLOR, 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._drag_rect.normalized())

    def _update_selection_from_drag(self):
        sel = self._drag_rect.normalized()
        new_sel = set()
        for cell in ALL_CELLS:
            if cell.block is None or not cell.individually_colorable:
                continue
            if sel.intersects(self._cell_rect(cell)):
                new_sel.add(cell.key_name)
        if self._ctrl_down:
            self._selection = self._previous_selection ^ new_sel
        else:
            self._selection = new_sel

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self._ctrl_down = bool(event.modifiers() & Qt.ControlModifier)
        if self._ctrl_down:
            self._previous_selection = set(self._selection)
        else:
            self._previous_selection = set()
        pos = event.pos()
        self._press_pos = QPointF(pos)
        self._drag_rect = QRectF(pos, pos)
        self._update_selection_from_drag()
        self.update()

    def mouseMoveEvent(self, event):
        if self._press_pos is None:
            return
        self._drag_rect.setBottomRight(QPointF(event.pos()))
        self._ctrl_down = bool(event.modifiers() & Qt.ControlModifier)
        self._update_selection_from_drag()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._press_pos is None:
            return
        was_click = (event.pos() - self._press_pos.toPoint()).manhattanLength() < 4
        self._press_pos = None
        self._drag_rect = None
        self.update()

        if not self._selection:
            return
        color = QColorDialog.getColor()
        if not color.isValid():
            self._selection = set() if was_click else self._selection
            self.update()
            return
        hexcolor = color.name().lstrip("#")

        by_block = {}
        for cell in ALL_CELLS:
            if cell.key_name in self._selection:
                by_block.setdefault(cell.block, []).append(cell.key_name)

        for block, keys in by_block.items():
            directives = [f"{bl._real_key_name(block, k)}={hexcolor}" for k in keys]
            ok, err = bl._run_set_leds(block, directives)
            if ok:
                for k in keys:
                    self._colors[k] = color
            else:
                print(f"FAILED to set {keys} on block {block}: {err}")

        if was_click:
            self._selection = set()
        self.update()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = KeyboardCanvas()
    win.setWindowTitle("G910 Canvas -- standalone test")
    win.show()
    sys.exit(app.exec_())
