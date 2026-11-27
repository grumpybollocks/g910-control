#!/usr/bin/env python3
"""
Watches the G910's G1-G9/M1-M3/MR via raw HID++ reports on the
keyboard's HID++ hidraw interface (found by g910_backlight._find_device
-- no evdev keycodes exist for these -- confirmed empirically, see
G910_README.md's G-KEY/M-KEY/MR PROTOCOL section) and replays recorded
macros via ydotool. Mirrors the sibling G510s project's
g510_macro_daemon.py (same replay mechanism, same macro file format,
same M-key live-profile-switching behavior) -- adapted for the G910
needing raw hidraw decoding instead of plain evdev.

Report format, fully confirmed via direct hardware capture earlier
this project: 20-byte reports, byte0=0x11, byte1=0xff, byte2=event
type (0x08=gkeys, 0x09=mkeys, 0x0a=mrkeys), byte3=0x00, byte4(+byte5
for G9 only)=bitmask, one bit per key, set on press, all-zero on
release.

MR is quick-record, the same way Logitech's own software does it:
press MR (LED on), press the G-key to record onto (LED blinks), type,
press MR again to save. MR twice in a row cancels.
"""
import fcntl
import json
import os
import select
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import g910_backlight as bl

MACROS_FILE = bl.DATA_DIR / "g910_macros.json"

# Real bug found and fixed via a live diagnostic capture: a single real
# G5 press was followed by clean press/release pairs repeating every
# 100-400ms for 2.5+ seconds straight (confirmed via raw hidraw
# timestamps, not assumed) -- the keyboard firmware's own key-repeat
# behavior, same thing that makes a held letter key type "aaaaa". The
# daemon had zero protection against this and replayed the macro on
# every single repeat. COOLDOWN_SECONDS ignores a new press of the
# SAME key within this window of the last one it acted on.
COOLDOWN_SECONDS = 0.35
MR_COOLDOWN_SECONDS = 0.8  # MR is a toggle: a bounce would cancel what it just started


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


def read_active_profile():
    """Real bug found and fixed: clicking M1/M2/M3 in the GUI used to
    only update the on-screen highlight + LED, never told this daemon
    -- so a real G-key press right after would replay the OLD
    profile's macro while the screen showed the new one, and the GUI's
    own poll_active_profile() would silently revert the highlight back
    within ~500ms since this file never changed. Same class of bug
    found and fixed on the sibling G510s daemon. Fix: the GUI now also
    writes this file on a click (see GKeysTab.select_profile in
    g910_app.py), and main()'s loop calls this on every wake (not just
    on a physical M-key press) to pick that up."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    try:
        return Path(runtime, "g910_macro_profile").read_text().strip()
    except Exception:
        return None


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
    # Key events are notifications: function 0, software id 0. Anything
    # else on these features is the REPLY to a request (ours or the
    # app's, hidraw hands every reader every report) -- e.g. the reply
    # to "set MR LED on" carries 0x01 in byte 4 and used to be decoded
    # as a phantom MR press.
    if data[3] != 0x00:
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


# HID++ feature indices on the G910 (046d:c335), read back from the
# device's root feature: 0x8010 GKEY -> 0x08, 0x8020 MKEYS -> 0x09,
# 0x8030 MR -> 0x0a. Same features Solaar diverts for its G-key rules.
GKEY_FEATURE_INDEX = 0x08
REARM_INTERVAL = 60.0      # safety-net re-arm, see arm_gkeys()
ARMED_TIMEOUT = 20.0       # MR pressed but no G-key chosen
RECORD_TIMEOUT = 60.0      # recording left running: discarded, never saved
BLINK_INTERVAL = 0.4


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def notify(text):
    """Desktop pop-up so a recording gives feedback even when the app
    window is closed. Purely optional -- no notify-send, no pop-up."""
    try:
        subprocess.Popen(["notify-send", "-a", "G910 Control", "-i", "g910-control",
                          "-t", "3000", "G910 Control", text],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def write_record_state(state):
    """'' / 'armed' / 'recording G3' -- read by the app to show status."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    try:
        Path(runtime, "g910_macro_record").write_text(state)
    except OSError:
        pass


def _edit_macros(change):
    # The app and this daemon both edit the file: lock around the whole
    # read-modify-write so two saves at once can't drop one of them.
    MACROS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MACROS_FILE.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        macros = load_macros()
        change(macros)
        _write_macros(macros)


def save_macro(profile, gkey, value, kind="keys"):
    _edit_macros(lambda m: m.setdefault(profile, {}).__setitem__(gkey, {"type": kind, "value": value}))


def clear_macro(profile, gkey):
    _edit_macros(lambda m: m.setdefault(profile, {}).pop(gkey, None))


def _write_macros(macros):
    # Atomic: the app and this daemon both write this file, and the
    # daemon re-reads it on every G-key press.
    MACROS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = MACROS_FILE.with_suffix(f".json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(macros, indent=2))
    os.replace(tmp, MACROS_FILE)


def clean_sequence(events):
    """Turns raw (code, value) key events into a replayable ydotool
    string. Drops auto-repeat events, drops key-ups whose key-down was
    never seen (a key already held when recording started), and
    releases anything still held at the end so a macro can never leave
    a key stuck down."""
    out, down = [], []
    for code, value in events:
        if value == 1:
            if code not in down:
                down.append(code)
                out.append(f"{code}:1")
        elif value == 0 and code in down:
            down.remove(code)
            out.append(f"{code}:0")
    out.extend(f"{code}:0" for code in reversed(down))
    return " ".join(out)


def find_keyboard_event_device():
    """The G910's typing interface (046d:c335, phys .../input0)."""
    try:
        import evdev
    except ImportError:
        return None
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if (dev.info.vendor, dev.info.product) == (0x046D, 0xC335) and dev.phys.endswith("input0"):
            return dev
        dev.close()
    return None


def arm_gkeys(fd=None):
    """Puts G1-G9 into software mode so presses arrive as HID++ reports.
    This is a live device mode, NOT a stored setting: the keyboard
    forgets it on every power loss (suspend, replug, KVM switch) and
    the G-keys then silently go back to typing F1-F9. The daemon used
    to send it once at start-up only, so macros died after the first
    suspend. Now sent at start, after resume, after a reconnect, and
    every REARM_INTERVAL as a cheap safety net (one 20-byte write)."""
    if fd is not None:
        try:
            os.write(fd, bytes([0x11, 0xff, GKEY_FEATURE_INDEX, 0x2d, 0x01]).ljust(20, b"\0"))
            return True
        except OSError as e:
            log(f"re-arming G-keys failed: {e!r}")
            return False
    res = subprocess.run(["keyledsctl", "gkeys", "-d", bl.DEVICE, "on"], capture_output=True, text=True)
    if res.returncode != 0:
        log(f"WARNING: 'keyledsctl gkeys on' failed (exit {res.returncode}): {res.stderr.strip()}")
    return res.returncode == 0


def _suspend_offset():
    # CLOCK_BOOTTIME keeps counting during suspend, CLOCK_MONOTONIC
    # does not -- a jump in the difference means the machine slept.
    return time.clock_gettime(time.CLOCK_BOOTTIME) - time.monotonic()


class Daemon:
    def __init__(self):
        self.fd = None
        self.active_profile = "M1"
        self.state = "idle"          # idle / armed / recording
        self.state_since = 0.0
        self.target = None           # (profile, gkey) being recorded
        self.kbd = None              # evdev device, open only while recording
        self.events = []
        self.led_on = False
        self.last_blink = 0.0
        self.last_trigger = {}
        self.last_arm = 0.0
        self.suspend_offset = _suspend_offset()

    # -- device -----------------------------------------------------
    def open_device(self):
        """Blocks until the keyboard is present and opened."""
        warned = False
        while True:
            bl.DEVICE = bl._find_device()
            if bl.DEVICE is not None:
                try:
                    self.fd = os.open(bl.DEVICE, os.O_RDWR | os.O_NONBLOCK)
                    break
                except OSError as e:
                    log(f"cannot open {bl.DEVICE}: {e!r}")
            if not warned:
                log("G910 not found -- waiting for it to be plugged in.")
                warned = True
            time.sleep(3)
        arm_gkeys()
        self.last_arm = time.monotonic()
        self.set_idle(quiet=True)
        ok, err = bl.set_mkey_led(self.active_profile)
        if not ok:
            log(f"WARNING: set_mkey_led({self.active_profile}) failed: {err}")
        log(f"watching {bl.DEVICE}, profile {self.active_profile}")

    def close_device(self):
        self.stop_capture()
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    # -- MR quick-record --------------------------------------------
    def set_led(self, on):
        self.led_on = on
        ok, err = bl.set_mrkey_led(on)
        if not ok:
            log(f"WARNING: set_mrkey_led({on}) failed: {err}")

    def set_idle(self, quiet=False):
        self.stop_capture()
        self.state, self.target, self.events = "idle", None, []
        write_record_state("")
        if not quiet or self.led_on:
            self.set_led(False)

    def stop_capture(self):
        if self.kbd is not None:
            try:
                self.kbd.close()
            except OSError:
                pass
            self.kbd = None

    def on_mr(self):
        now = time.monotonic()
        if self.state == "idle":
            self.state, self.state_since = "armed", now
            self.set_led(True)
            write_record_state("armed")
            log("MR: armed -- press the G-key to record onto")
            notify("Recording armed: press a G-key, type, then press MR again.")
        elif self.state == "armed":
            log("MR: cancelled")
            self.set_idle()
        else:
            profile, gkey = self.target
            sequence = clean_sequence(self.events)
            self.set_idle()
            if sequence:
                save_macro(profile, gkey, sequence)
                log(f"MR: saved {len(sequence.split())} events to {profile}/{gkey}")
                notify(f"Macro saved to {profile} / {gkey}.")
            else:
                log(f"MR: nothing typed, {profile}/{gkey} left unchanged")
                notify(f"Nothing typed, {gkey} left unchanged.")

    def start_recording(self, gkey):
        self.kbd = find_keyboard_event_device()
        if self.kbd is None:
            log("MR: cannot record -- keyboard input device not readable (python-evdev / 'input' group?)")
            notify("Cannot record: keyboard input device is not readable.")
            self.set_idle()
            return
        self.state, self.state_since = "recording", time.monotonic()
        self.target, self.events = (self.active_profile, gkey), []
        write_record_state(f"recording {gkey}")
        log(f"MR: recording onto {self.active_profile}/{gkey}")

    def read_capture(self):
        try:
            for event in self.kbd.read():
                if event.type == 1:  # EV_KEY
                    self.events.append((event.code, event.value))
        except BlockingIOError:
            pass
        except OSError as e:
            log(f"MR: keyboard input lost while recording ({e!r}), discarded")
            self.set_idle()

    def tick(self, now):
        if self.state == "armed" and now - self.state_since > ARMED_TIMEOUT:
            log("MR: no G-key chosen, disarmed")
            self.set_idle()
        elif self.state == "recording":
            if now - self.state_since > RECORD_TIMEOUT:
                log("MR: recording timed out, discarded")
                notify("Recording timed out, nothing saved.")
                self.set_idle()
            elif now - self.last_blink >= BLINK_INTERVAL:
                self.last_blink = now
                self.set_led(not self.led_on)

    # -- key handling -----------------------------------------------
    def on_report(self, data):
        decoded = decode_report(data)
        if decoded is None:
            return
        kind, name, is_press = decoded
        if not is_press:
            return
        now = time.monotonic()
        cooldown = MR_COOLDOWN_SECONDS if kind == "mrkey" else COOLDOWN_SECONDS
        if now - self.last_trigger.get(name, 0) < cooldown:
            return
        self.last_trigger[name] = now

        if kind == "mrkey":
            self.on_mr()
        elif kind == "mkey":
            if self.state == "recording":
                return  # target profile is fixed once recording started
            self.active_profile = name
            write_active_profile(name)
            ok, err = bl.set_mkey_led(name)
            if not ok:
                log(f"WARNING: set_mkey_led({name}) failed: {err}")
        elif kind == "gkey":
            if self.state == "armed":
                self.start_recording(name)
            elif self.state == "recording":
                return
            else:
                entry = load_macros().get(self.active_profile, {}).get(name)
                if entry:
                    log(f"{self.active_profile}/{name}: replay")
                    threading.Thread(target=replay, args=(entry,), daemon=True).start()
                else:
                    log(f"{self.active_profile}/{name}: no macro assigned")

    def run(self):
        write_active_profile(self.active_profile)
        self.open_device()
        while True:
            fds = [self.fd] + ([self.kbd.fd] if self.kbd is not None else [])
            timeout = 0.1 if self.state == "recording" else 0.5
            try:
                r, _, _ = select.select(fds, [], [], timeout)
            except OSError:
                r = [self.fd]  # fall through to the read, which reports the real error
            now = time.monotonic()

            live = read_active_profile()
            if live in ("M1", "M2", "M3") and live != self.active_profile and self.state != "recording":
                self.active_profile = live

            offset = _suspend_offset()
            resumed = offset - self.suspend_offset > 1.0
            self.suspend_offset = offset
            if resumed:
                log("resume detected -- re-arming G-keys")
                self.set_idle(quiet=True)
                time.sleep(1.0)  # let the keyboard finish coming back
                if not arm_gkeys(self.fd):
                    r = [self.fd]
                else:
                    bl.set_mkey_led(self.active_profile)
                self.last_arm = now
            elif now - self.last_arm > REARM_INTERVAL and self.state == "idle":
                arm_gkeys(self.fd)
                self.last_arm = now

            if self.kbd is not None and self.kbd.fd in r:
                self.read_capture()
            if self.fd in r:
                try:
                    data = os.read(self.fd, 64)
                    if not data:
                        raise OSError("device closed")
                except BlockingIOError:
                    data = None  # forced read with nothing waiting: device is fine
                except OSError as e:
                    log(f"keyboard disconnected ({e!r}) -- waiting for it to come back")
                    self.close_device()
                    self.state, self.target, self.events = "idle", None, []
                    write_record_state("")
                    time.sleep(2)
                    self.open_device()
                    continue
                if data:
                    self.on_report(data)
            self.tick(now)


def main():
    # systemd stops us with SIGTERM; turn it into a normal exit so the
    # finally block clears the record state file and the MR LED.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    daemon = Daemon()
    try:
        daemon.run()
    except KeyboardInterrupt:
        pass
    finally:
        write_record_state("")
        if daemon.fd is not None and daemon.led_on:
            bl.set_mrkey_led(False)


if __name__ == "__main__":
    main()
