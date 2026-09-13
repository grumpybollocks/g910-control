#!/usr/bin/env python3
"""
G910 Control App -- BAREBONES SKELETON, not the real GUI yet.

Purpose: prove a clickable visual keyboard -> color picker -> real
hardware color-set loop works end to end. Layout is structurally
shaped like the real board (G1-G5 left column, G6-G9 top row, M1-M3/MR
row, main board) but deliberately plain -- no styling, no live-color
backgrounds, no multi-select yet. That polish comes after this
skeleton is proven solid. See G910_README.txt for the full plan.
"""
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout,
    QPushButton, QColorDialog, QLabel,
)

import g910_backlight as bl

# (display_label, real_key_name_or_None, colspan) -- real_key_name is
# None for keys confirmed to have NO individually-addressable LED on
# this exact hardware (only LCTRL/LSHIFT exist among modifiers -- no
# RCTRL, RALT, LALT, RSHIFT, LMETA/RMETA, MENU, or AltGr at all,
# confirmed via a real get-leds dump, not assumed). Those render as
# inert placeholders, same as the M-keys.
MAIN_ROWS = [
    [("Esc", "ESC", 1), ("F1", "F1", 1), ("F2", "F2", 1), ("F3", "F3", 1), ("F4", "F4", 1),
     ("F5", "F5", 1), ("F6", "F6", 1), ("F7", "F7", 1), ("F8", "F8", 1), ("F9", "F9", 1),
     ("F10", "F10", 1), ("F11", "F11", 1), ("F12", "F12", 1)],
    [("`", "GRAVE", 1), ("1", "1", 1), ("2", "2", 1), ("3", "3", 1), ("4", "4", 1),
     ("5", "5", 1), ("6", "6", 1), ("7", "7", 1), ("8", "8", 1), ("9", "9", 1), ("0", "0", 1),
     ("-", "MINUS", 1), ("=", "EQUAL", 1), ("Bksp", "BACKSPACE", 2)],
    [("Tab", "TAB", 2), ("Q", "Q", 1), ("W", "W", 1), ("E", "E", 1), ("R", "R", 1),
     ("T", "T", 1), ("Y", "Y", 1), ("U", "U", 1), ("I", "I", 1), ("O", "O", 1), ("P", "P", 1),
     ("[", "LBRACE", 1), ("]", "RBRACE", 1), ("\\", "BACKSLASH", 1)],
    [("Caps", "CAPSLOCK", 2), ("A", "A", 1), ("S", "S", 1), ("D", "D", 1), ("F", "F", 1),
     ("G", "G", 1), ("H", "H", 1), ("J", "J", 1), ("K", "K", 1), ("L", "L", 1),
     (";", "SEMICOLON", 1), ("'", "APOSTROPHE", 1), ("Enter", "ENTER", 2)],
    [("Shift", "LSHIFT", 2), ("Z", "Z", 1), ("X", "X", 1), ("C", "C", 1), ("V", "V", 1),
     ("B", "B", 1), ("N", "N", 1), ("M", "M", 1), (",", "COMMA", 1), (".", "DOT", 1),
     ("/", "SLASH", 1), ("Shift", None, 2)],
    [("Ctrl", "LCTRL", 2), ("Win", None, 1), ("Alt", None, 1), ("Space", "SPACE", 6),
     ("AltGr", None, 1), ("Menu", None, 1), ("Ctrl", None, 2)],
]

# Nav cluster + numpad, row-aligned with MAIN_ROWS (same 6 rows) so they
# sit at the correct height next to the main block. (None, None, n) means
# "leave this cell empty" -- no widget added, just advances n columns.
NAV_ROWS = [
    [("PrtSc", "SYSRQ", 1), ("ScrLk", "SCROLLLOCK", 1), ("Pause", "PAUSE", 1)],
    [("Ins", "INSERT", 1), ("Home", "HOME", 1), ("PgUp", "PAGEUP", 1)],
    [("Del", "DELETE", 1), ("End", "END", 1), ("PgDn", "PAGEDOWN", 1)],
    [(None, None, 3)],
    [(None, None, 1), ("↑", "UP", 1), (None, None, 1)],
    [("←", "LEFT", 1), ("↓", "DOWN", 1), ("→", "RIGHT", 1)],
]

NUMPAD_ROWS = [
    [(None, None, 4)],
    [("Num", "NUMLOCK", 1), ("/", "KPSLASH", 1), ("*", "KPASTERISK", 1), ("-", "KPMINUS", 1)],
    [("7", "KP7", 1), ("8", "KP8", 1), ("9", "KP9", 1), ("+", "KPPLUS", 1)],
    [("4", "KP4", 1), ("5", "KP5", 1), ("6", "KP6", 1), (None, None, 1)],
    [("1", "KP1", 1), ("2", "KP2", 1), ("3", "KP3", 1), ("Enter", "KPENTER", 1)],
    [("0", "KP0", 2), (".", "KPDOT", 1), (None, None, 1)],
]

GKEYS_LEFT = ["G1", "G2", "G3", "G4", "G5"]
GKEYS_TOP = ["G6", "G7", "G8", "G9"]
MKEYS = ["M1", "M2", "M3", "MR"]


class KeyButton(QPushButton):
    def __init__(self, label, key_name, block):
        super().__init__(label)
        self.key_name = key_name
        self.block = block
        self.setFixedHeight(32)
        if block is None:
            self.setEnabled(False)  # no individually-addressable LED, or not wired yet
        self.clicked.connect(self.on_click)

    def on_click(self):
        if self.block is None:
            return
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        hexcolor = color.name().lstrip("#")
        ok, err = bl.set_key_color(self.key_name, hexcolor, block=self.block)
        if ok:
            self.setStyleSheet(f"background-color: #{hexcolor};")
        else:
            self.setStyleSheet("background-color: #400000;")
            print(f"FAILED to set {self.key_name}: {err}")


# target_name -> apply function taking a hex color string.
COLOR_MODE_TARGETS = {
    "Logo": lambda hexcolor: bl.set_group_color("logo", hexcolor),
    "G-Keys": lambda hexcolor: bl.set_group_color("gkeys", hexcolor),
    "Main Board": lambda hexcolor: bl.set_all_color(hexcolor),
}


class ColorModeSidebar(QWidget):
    """Select a target (Logo / G-Keys / Main Board), pick a color, Apply
    it to that whole group at once -- separate from clicking individual
    keys on the keyboard grid."""
    def __init__(self):
        super().__init__()
        self.current_target = "Logo"
        self.setFixedWidth(160)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>Color Mode</b>"))

        self.target_buttons = {}
        for name in COLOR_MODE_TARGETS:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, n=name: self.select_target(n))
            layout.addWidget(btn)
            self.target_buttons[name] = btn
        self.target_buttons[self.current_target].setChecked(True)

        layout.addSpacing(16)
        apply_btn = QPushButton("Pick Color && Apply")
        apply_btn.clicked.connect(self.on_apply)
        layout.addWidget(apply_btn)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setLayout(layout)

    def select_target(self, name):
        self.current_target = name
        for n, btn in self.target_buttons.items():
            btn.setChecked(n == name)

    def on_apply(self):
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        hexcolor = color.name().lstrip("#")
        ok, err = COLOR_MODE_TARGETS[self.current_target](hexcolor)
        if ok:
            self.status_label.setText(f"{self.current_target} set to #{hexcolor}")
        else:
            self.status_label.setText(f"FAILED: {err}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G910 Control -- SKELETON (not final)")
        self.resize(2050, 500)

        central = QWidget()
        outer = QHBoxLayout()
        central.setLayout(outer)
        self.setCentralWidget(central)

        outer.addWidget(ColorModeSidebar())

        keyboard_widget = QWidget()
        grid = QGridLayout()
        grid.setSpacing(4)
        keyboard_widget.setLayout(grid)
        outer.addWidget(keyboard_widget)

        # M1/M2/M3/MR -- top-left, not color-wired yet (block=None)
        for col, name in enumerate(MKEYS):
            btn = KeyButton(name, name, block=None)
            btn.setMaximumWidth(50)
            grid.addWidget(btn, 0, col)

        # Main board -- offset right/down to leave room for G-keys.
        # col_offset=4 (not 2): M1-M3/MR occupy columns 0-3, so the main
        # board (and G6-G9, computed relative to it below) must start at
        # column 4 or later to avoid overlapping the M-keys' own cells.
        col_offset = 4
        row_offset = 1
        # Width varies per row (e.g. Backspace/Tab/Enter/Shift span 2) --
        # take the max across ALL rows, not just the F-row, or later
        # blocks (nav cluster) start too early and collide with whatever
        # row is actually widest.
        main_width = max(sum(span for label, real_name, span in row) for row in MAIN_ROWS)

        # G6-G9 -- top row, aligned above F1-F4 (matches the reference
        # picture: G-keys sit directly above the first 4 F-keys, not
        # past the M-keys' own width).
        for col, name in enumerate(GKEYS_TOP):
            btn = KeyButton(name, name, block="gkeys")
            grid.addWidget(btn, 0, col_offset + 1 + col)

        # G1-G5 -- left column, below the M-keys. Capped to the same
        # width as the M-keys so column 0 doesn't stretch wide and leave
        # M1 looking stranded in oversized empty space.
        for row, name in enumerate(GKEYS_LEFT):
            btn = KeyButton(name, name, block="gkeys")
            btn.setMaximumWidth(50)
            grid.addWidget(btn, row + 1, 0)
        for r, row_keys in enumerate(MAIN_ROWS):
            c = col_offset
            for label, real_name, span in row_keys:
                if label is not None:
                    block = "keys" if real_name is not None else None
                    btn = KeyButton(label, real_name, block=block)
                    grid.addWidget(btn, r + row_offset, c, 1, span)
                c += span

        # Nav cluster -- right of the main board, one column gap
        nav_offset = col_offset + main_width + 1
        for r, row_keys in enumerate(NAV_ROWS):
            c = nav_offset
            for label, real_name, span in row_keys:
                if label is not None:
                    btn = KeyButton(label, real_name, block="keys")
                    grid.addWidget(btn, r + row_offset, c, 1, span)
                c += span

        # Numpad -- right of the nav cluster, one column gap
        numpad_offset = nav_offset + 3 + 1
        for r, row_keys in enumerate(NUMPAD_ROWS):
            c = numpad_offset
            for label, real_name, span in row_keys:
                if label is not None:
                    btn = KeyButton(label, real_name, block="keys")
                    grid.addWidget(btn, r + row_offset, c, 1, span)
                c += span


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
