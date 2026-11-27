#!/usr/bin/env python3
# Passes every G910 key through EXCEPT the numpad, for when numpad switches
# misfire (e.g. still wet after cleaning). Runs until stopped with Ctrl+C.
import evdev
from evdev import ecodes as e
BLOCK = {c for n, c in e.ecodes.items() if n.startswith("KEY_KP")} | {e.KEY_NUMLOCK}
devs = [evdev.InputDevice(p) for p in evdev.list_devices()]
devs = [d for d in devs if (d.info.vendor, d.info.product) == (0x046D, 0xC335) and d.phys.endswith("input0")]
src = devs[0]
ui = evdev.UInput.from_device(src, name="G910 (numpad blocked)")
src.grab()
print("blocking numpad on", src.path, flush=True)
try:
    for ev in src.read_loop():
        if ev.type == e.EV_KEY and ev.code in BLOCK:
            continue
        ui.write_event(ev)
finally:
    src.ungrab(); ui.close()
