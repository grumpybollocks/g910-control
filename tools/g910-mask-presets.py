#!/usr/bin/env python3
"""Saves four lighting profiles that use no green anywhere and keep the
arrow/nav block blue. They hide LEDs whose green channel is faulty (see
docs/LED_FAULTS.md). Load them from the app's Profiles list afterwards.
Your current colours are put back when it finishes."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
here = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(here, "..", "src"), "/usr/lib/g910-control"):
    if os.path.exists(os.path.join(p, "g910_backlight.py")):
        sys.path.insert(0, p)
        break
import g910_backlight as bl  # noqa: E402
import g910_canvas as c  # noqa: E402

PRESETS = {
    "Midnight Blue": {"Main Board": "0000ff", "F1-F12": "0000c0", "Numpad": "0000ff",
                      "Nav Cluster": "0000ff", "G-Keys": "0000c0", "Logo": "0000ff"},
    "Purple Rain": {"Main Board": "7000ff", "F1-F12": "a000ff", "Numpad": "7000ff",
                    "Nav Cluster": "0000ff", "G-Keys": "ff00ff", "Logo": "7000ff"},
    "Synthwave": {"Main Board": "ff00b0", "F1-F12": "8000ff", "Numpad": "ff00b0",
                  "Nav Cluster": "3000ff", "G-Keys": "8000ff", "Logo": "ff00b0"},
    "Crimson Blue": {"Main Board": "ff0010", "F1-F12": "ff0070", "Numpad": "ff0010",
                     "Nav Cluster": "0000ff", "G-Keys": "ff0010", "Logo": "0000ff"},
}
CELLS = [x for x in c.ALL_CELLS if x.block]
BLOCK = {x.key_name: x.block for x in CELLS}


def paint(colours):
    by = {}
    for key, hexc in colours.items():
        if key in BLOCK:
            by.setdefault(BLOCK[key], []).append(f"{bl._real_key_name(BLOCK[key], key)}={hexc.lstrip('#')}")
    for block, directives in by.items():
        ok, err = bl._run_set_leds(block, directives)
        if not ok:
            sys.exit(f"FAILED: {err}")


before = bl.get_all_live_colors()
if not before:
    sys.exit("No G910 found.")
for name, zones in PRESETS.items():
    paint({k: h for z, h in zones.items() for k in c.ZONE_KEYS[z]})
    bl.save_profile(name)
    print("saved", name)
paint(before)
print("your colours are back; load a preset from the app's Profiles list")
