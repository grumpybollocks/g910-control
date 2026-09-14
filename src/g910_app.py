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
reading feature_leds.c directly, see G910_README.txt). So brightness
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
import select
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QColorDialog, QLabel, QSlider, QTabWidget,
    QDialog, QLineEdit, QMessageBox, QInputDialog, QFrame,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QColor
import evdev
from evdev import ecodes

import g910_backlight as bl
from g910_canvas import KeyboardCanvas, ZONE_KEYS, ZONE_SELECTION_KEYS

PROJECT_DIR = Path(__file__).resolve().parent.parent
MACROS_FILE = PROJECT_DIR / "g910_macros.json"  # separate from the G510s's macros.json
MAIN_KEYBOARD_DEVICE = "/dev/input/by-id/usb-Logitech_Gaming_Keyboard_G910_096239583837-event-kbd"

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
QLabel#Title {
    font-size: 15px;
    font-weight: 600;
    padding: 4px 2px 10px 2px;
}
QPushButton#ZoneButton {
    text-align: center;
    padding: 5px 10px;
}
QWidget#Panel {
    background-color: #1c1c20;
    border: 1px solid #2a2a30;
    border-radius: 8px;
}
QFrame#Separator {
    background-color: #2a2a30;
    border: none;
    max-width: 1px;
    min-width: 1px;
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
"""


def scale_color(color, brightness_pct):
    factor = brightness_pct / 100.0
    r = max(0, min(255, round(color.red() * factor)))
    g = max(0, min(255, round(color.green() * factor)))
    b = max(0, min(255, round(color.blue() * factor)))
    return QColor(r, g, b)


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
        self.setFixedWidth(180)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        title = QLabel("Color Mode")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.target_buttons = {}
        for name in ZONE_KEYS:
            btn = QPushButton(name)
            btn.setObjectName("ZoneButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, n=name: self.select_target(n))
            layout.addWidget(btn)
            self.target_buttons[name] = btn
        self.target_buttons[self.current_target].setChecked(True)
        self.canvas.select_keys(ZONE_SELECTION_KEYS[self.current_target])

        layout.addSpacing(14)
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

        layout.addSpacing(14)
        apply_btn = QPushButton("Pick Color && Apply")
        apply_btn.setObjectName("Primary")
        apply_btn.clicked.connect(self.on_apply)
        layout.addWidget(apply_btn)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Status")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setLayout(layout)

    def on_brightness_changed(self, value):
        self.brightness_pct = value
        self.bright_value_label.setText(f"{value}%")

    def select_target(self, name):
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

    def on_apply(self):
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        scaled = scale_color(color, self.brightness_pct)
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


def _vseparator():
    line = QFrame()
    line.setObjectName("Separator")
    line.setFrameShape(QFrame.VLine)
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

        self.profiles_panel = ProfilesTab(self.canvas)
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
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        label = QLabel("G-Keys")
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

        self.setLayout(layout)
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
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        layout = QVBoxLayout()
        layout.setContentsMargins(14, 14, 14, 14)

        title = QLabel("Profiles")
        title.setObjectName("Title")
        layout.addWidget(title)

        layout.addSpacing(10)
        save_btn = QPushButton("Save Current as Profile...")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self.on_save)
        layout.addWidget(save_btn)

        layout.addSpacing(16)
        layout.addWidget(QLabel("<b>Saved profiles</b>"))
        self.list_layout = QVBoxLayout()
        layout.addLayout(self.list_layout)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Status")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
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
            return
        for name in names:
            row = QHBoxLayout()
            row.addWidget(QLabel(name))
            row.addStretch()
            load_btn = QPushButton("Load")
            load_btn.clicked.connect(lambda _, n=name: self.on_load(n))
            delete_btn = QPushButton("Delete")
            delete_btn.clicked.connect(lambda _, n=name: self.on_delete(n))
            row.addWidget(load_btn)
            row.addWidget(delete_btn)
            container = QWidget()
            container.setLayout(row)
            self.list_layout.addWidget(container)

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
        success, err = bl.save_profile(name)
        if success:
            self.status_label.setText(f'Saved current lighting as "{name}".')
            self.refresh_list()
        else:
            self.status_label.setText(f"FAILED: {err}")

    def on_load(self, name):
        success, err = bl.load_profile(name)
        if success:
            self.status_label.setText(f'Loaded "{name}".')
            self.canvas.sync_from_device()
        else:
            self.status_label.setText(f"FAILED: {err}")

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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
