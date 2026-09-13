#!/usr/bin/env python3
"""
G910 Control App -- canvas-based rearchitecture.

Real per-key geometry canvas (g910_canvas.KeyboardCanvas) + a Color
Mode sidebar for bulk zone coloring. Selecting a zone highlights those
keys on the canvas; applying a color previews it there too, not just
on the real hardware. See G910_CANVAS_PLAN.md for the full design.
"""
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QColorDialog, QLabel,
)
from PyQt5.QtGui import QColor

import g910_backlight as bl
from g910_canvas import KeyboardCanvas, ZONE_KEYS


class ColorModeSidebar(QWidget):
    """Select a zone, pick a color, Apply it to that whole zone at
    once. Selecting a zone highlights it on the canvas; a successful
    apply previews the color there too."""
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.current_target = "Logo"
        self.setFixedWidth(160)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>Color Mode</b>"))

        self.target_buttons = {}
        for name in ZONE_KEYS:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, n=name: self.select_target(n))
            layout.addWidget(btn)
            self.target_buttons[name] = btn
        self.target_buttons[self.current_target].setChecked(True)
        self.canvas.select_keys(ZONE_KEYS[self.current_target])

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
        self.canvas.select_keys(ZONE_KEYS[name])

    def on_apply(self):
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        hexcolor = color.name().lstrip("#")
        keys = ZONE_KEYS[self.current_target]

        ok, err = self._apply_zone(self.current_target, hexcolor)
        if ok:
            self.status_label.setText(f"{self.current_target} set to #{hexcolor}")
            self.canvas.set_colors(keys, QColor(f"#{hexcolor}"))
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G910 Control")
        self.resize(1500, 420)

        central = QWidget()
        outer = QHBoxLayout()
        central.setLayout(outer)
        self.setCentralWidget(central)

        canvas = KeyboardCanvas()
        sidebar = ColorModeSidebar(canvas)

        outer.addWidget(sidebar)
        outer.addWidget(canvas)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
