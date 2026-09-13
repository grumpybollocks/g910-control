#!/usr/bin/env python3
"""
Watches the G910's G1-G9/M1-M3/MR via raw HID++ reports on hidraw1 (no
evdev keycodes exist for these -- confirmed empirically, see
G910_README.txt's G-KEY/M-KEY/MR PROTOCOL section) and replays recorded
macros via ydotool. Mirrors the sibling G510s project's
g510_macro_daemon.py (same replay mechanism, same macro file format,
same M-key live-profile-switching behavior) -- adapted for the G910
needing raw hidraw decoding instead of plain evdev.

Report format, fully confirmed via direct hardware capture earlier
this project: 20-byte reports, byte0=0x11, byte1=0xff, byte2=event
type (0x08=gkeys, 0x09=mkeys, 0x0a=mrkeys), byte3=0x00, byte4(+byte5
for G9 only)=bitmask, one bit per key, set on press, all-zero on
release.

MR is a literal macro-record toggle (the user's explicit decision),
NOT a 4th profile -- currently only toggles its own LED as a visible
placeholder. Wiring it to actually arm/disarm quick-recording is not
yet designed (real open question, not guessed at here).
"""
import json
import os
import select
import subprocess
import sys
import threading
import time
from pathlib import Path

import g910_backlight as bl

PROJECT_DIR = Path(__file__).resolve().parent.parent
MACROS_FILE = PROJECT_DIR / "g910_macros.json"
DEVICE_PATH = bl.DEVICE  # stable by-id symlink, not a hardcoded hidrawN -- see g910_backlight.py's DEVICE comment

# Real bug found and fixed via a live diagnostic capture: a single real
# G5 press was followed by clean press/release pairs repeating every
# 100-400ms for 2.5+ seconds straight (confirmed via raw hidraw
# timestamps, not assumed) -- the keyboard firmware's own key-repeat
# behavior, same thing that makes a held letter key type "aaaaa". The
# daemon had zero protection against this and replayed the macro on
# every single repeat. COOLDOWN_SECONDS ignores a new press of the
# SAME key within this window of the last one it acted on.
COOLDOWN_SECONDS = 0.35


def load_macros():
    if MACROS_FILE.exists():
        try:
            return json.loads(MACROS_FILE.read_text())
        except Exception:
            pass
    return {"M1": {}, "M2": {}, "M3": {}}


def write_active_profile(name):
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    Path(runtime, "g910_macro_profile").write_text(name)


def replay(entry):
    """Runs in its own thread (see main()) so a slow macro/command can
    never block the read loop and delay/miss the next real HID++
    report -- confirmed this matters: subprocess.run() here used to
    run inline on the same thread that reads M-key presses too."""
    try:
        if isinstance(entry, str):  # legacy/bare-string format, pre-command-support
            result = subprocess.run(["ydotool", "key"] + entry.split(), capture_output=True, text=True)
        elif entry.get("type") == "command":
            result = subprocess.run(entry["value"], shell=True, capture_output=True, text=True)
        else:  # type == "keys"
            result = subprocess.run(["ydotool", "key"] + entry["value"].split(), capture_output=True, text=True)
        if result.returncode != 0:
            print(f"replay FAILED (exit {result.returncode}): {result.stderr.strip()}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"replay FAILED with exception: {e!r}", file=sys.stderr, flush=True)


def decode_report(data):
    """Returns ('gkey', 'G3', is_press) / ('mkey', 'M2', is_press) /
    ('mrkey', 'MR', is_press) / None for an unrelated/malformed report."""
    if len(data) < 6 or data[0] != 0x11 or data[1] != 0xff:
        return None
    event_type = data[2]
    byte4, byte5 = data[4], data[5]

    if event_type == 0x08:  # gkeys
        for i in range(8):
            if byte4 & (1 << i):
                return ("gkey", f"G{i + 1}", True)
        if byte5 & 0x01:
            return ("gkey", "G9", True)
        if byte4 == 0 and byte5 == 0:
            return ("gkey", None, False)  # release, no specific key needed
        return None
    if event_type == 0x09:  # mkeys
        for i, name in enumerate(("M1", "M2", "M3")):
            if byte4 & (1 << i):
                return ("mkey", name, True)
        if byte4 == 0:
            return ("mkey", None, False)
        return None
    if event_type == 0x0a:  # mrkeys
        if byte4 & 0x01:
            return ("mrkey", "MR", True)
        if byte4 == 0:
            return ("mrkey", None, False)
        return None
    return None


def main():
    # G-keys default to F13-F21 passthrough and emit nothing on the
    # HID++ channel until explicitly enabled -- confirmed empirically
    # earlier this project (a capture attempt with zero setup produced
    # zero bytes). Must be re-run every daemon start, it's a live
    # device-mode toggle, not a persisted setting.
    gkeys_on = subprocess.run(["keyledsctl", "gkeys", "-d", DEVICE_PATH, "on"], capture_output=True, text=True)
    if gkeys_on.returncode != 0:
        print(f"WARNING: 'keyledsctl gkeys on' failed (exit {gkeys_on.returncode}): "
              f"{gkeys_on.stderr.strip()} -- G-key presses will NOT be detected until this succeeds.",
              file=sys.stderr, flush=True)

    active_profile = "M1"
    recording_armed = False
    write_active_profile(active_profile)
    ok, err = bl.set_mkey_led(active_profile)
    if not ok:
        print(f"WARNING: startup set_mkey_led({active_profile}) failed: {err}", file=sys.stderr, flush=True)

    last_trigger = {}  # key_name -> time.monotonic() of last accepted press

    fd = os.open(DEVICE_PATH, os.O_RDONLY)
    try:
        while True:
            r, _, _ = select.select([fd], [], [])
            data = os.read(fd, 64)
            decoded = decode_report(data)
            if decoded is None:
                continue
            kind, name, is_press = decoded
            if not is_press:
                continue  # only act on press, matching the G510s daemon's key-down-only filter

            # Firmware key-repeat cooldown -- confirmed necessary via a
            # live capture (see COOLDOWN_SECONDS comment above), applies
            # to every key kind, not just G-keys, since M-keys/MR could
            # repeat-fire the same way if held.
            now = time.monotonic()
            if now - last_trigger.get(name, 0) < COOLDOWN_SECONDS:
                continue
            last_trigger[name] = now

            if kind == "mkey":
                active_profile = name
                write_active_profile(active_profile)
                ok, err = bl.set_mkey_led(active_profile)
                if not ok:
                    print(f"WARNING: set_mkey_led({active_profile}) failed: {err}", file=sys.stderr, flush=True)
            elif kind == "mrkey":
                recording_armed = not recording_armed
                ok, err = bl.set_mrkey_led(recording_armed)
                if not ok:
                    print(f"WARNING: set_mrkey_led({recording_armed}) failed: {err}", file=sys.stderr, flush=True)
            elif kind == "gkey":
                macros = load_macros()  # reload each time -- app may have just saved a new one
                entry = macros.get(active_profile, {}).get(name)
                if entry:
                    # Own thread: a slow command/ydotool call must
                    # never block the read loop, or the next M-key
                    # press (or another G-key) could be delayed/missed.
                    threading.Thread(target=replay, args=(entry,), daemon=True).start()
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
