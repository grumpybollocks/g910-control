#!/usr/bin/env python3
"""
G910 Backlight -- barebones skeleton, no GUI.

Purpose: prove the core color-control primitives work reliably before
building anything on top. Wraps `keyledsctl set-leds`/`get-leds`
against LED block 01 ("keys", 105 keys, confirmed true per-key RGB on
this exact hardware -- see G910_README.md). Not wired to a daemon or
GUI yet -- run directly for now, see the __main__ block at the bottom.

Groups below are a minimal hardcoded starting point (not the full
Solaar-derived layout geometry from planning) -- just enough to prove
"set a named group of keys at once" works before investing in the real
layout data.
"""
import colorsys
import ctypes
import json
import math
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

# XDG Base Directory spec: per-user runtime state (profiles/macros)
# belongs under $XDG_DATA_HOME (default ~/.local/share), not next to
# the installed source -- that only ever worked for a writable
# git-clone checkout, and breaks outright for a real /usr-installed
# package (not user-writable, by design). Created on first use.
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "g910-control"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _find_device():
    """Ask keyledsctl itself which hidraw path is the G910 (046d:c335),
    instead of a hardcoded by-id symlink -- that symlink embeds this
    exact physical unit's USB serial -- confirmed via `udevadm info`
    that this serial is per-unit, not a fixed model string, so it
    would never match a different person's G910. keyledsctl
    is already a hard runtime dependency and its own `list` command
    already resolves the correct interface (confirmed live: it reports
    exactly one line for this device, matching the same hidraw node the
    old hardcoded path pointed at -- no if00/if01 ambiguity to resolve
    ourselves). Returns None (rather than raising) if not found, so the
    app can still open with no keyboard attached -- same as today,
    whichever call actually needs the device will fail at that point.
    """
    try:
        out = subprocess.run(
            ["keyledsctl", "list"], capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        print(f"g910_backlight: keyledsctl list failed ({err})", file=sys.stderr)
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].lower() == "046d:c335":
            return parts[0]
    print("g910_backlight: no Logitech G910 (046d:c335) found via keyledsctl list", file=sys.stderr)
    return None


DEVICE = _find_device()


def _have_device():
    """True if a G910 is known, looking it up again if the app started
    before the keyboard was plugged in."""
    global DEVICE
    if DEVICE is None:
        DEVICE = _find_device()
    return DEVICE is not None


def _kctl(*args):
    """Runs keyledsctl against the G910. If the keyboard was replugged
    its hidraw path changes (seen live: hidraw2 -> hidraw1) and every
    call from an already-open app failed until it was restarted. On a
    "Cannot open" failure, look the device up again and retry once."""
    global DEVICE
    if DEVICE is None:
        DEVICE = _find_device()
        if DEVICE is None:
            return subprocess.CompletedProcess(args, 1, "", "No G910 keyboard found -- is it plugged in?")
    result = subprocess.run(["keyledsctl", args[0], "-d", DEVICE, *args[1:]], capture_output=True, text=True)
    if result.returncode != 0 and "Cannot open" in result.stderr:
        fresh = _find_device()
        if fresh is not None:
            DEVICE = fresh
            result = subprocess.run(["keyledsctl", args[0], "-d", DEVICE, *args[1:]], capture_output=True, text=True)
    return result


def _open_keyleds(lib):
    """libkeyleds handle for the G910, re-finding the device once if
    the remembered path has gone stale (replug)."""
    global DEVICE
    device = lib.keyleds_open(DEVICE.encode(), _KEYLEDSCTL_APP_ID) if DEVICE else None
    if not device:
        fresh = _find_device()
        if fresh is not None:
            DEVICE = fresh
            device = lib.keyleds_open(DEVICE.encode(), _KEYLEDSCTL_APP_ID)
    return device


PROFILES_FILE = DATA_DIR / "g910_profiles.json"
# Blocks a full lighting snapshot covers. "media" deliberately excluded
# -- paused per the user's explicit instruction not to touch it, see
# G910_SKELETON.md.
PROFILE_BLOCKS = ("keys", "gkeys", "logo")

# M-key/MR indicator LEDs are NOT controlled through keyledsctl (it has
# no subcommand for this at all -- confirmed by reading
# keyledsctl_gkeys.c, it only calls keyleds_gkeys_enable). They go
# through libkeyleds.so directly via ctypes -- keyleds_mkeys_set/
# keyleds_mrkeys_set, exported functions, proven working earlier this
# project (see G910_README.md M-KEY/MR INDICATOR LED CONTROL section).
_KEYLEDSCTL_APP_ID = 0x9
_KEYLEDS_TARGET_DEFAULT = 0xff
_MKEY_MASKS = {"M1": 0x01, "M2": 0x02, "M3": 0x04}


def _keyleds_lib():
    lib = ctypes.CDLL("libkeyleds.so.1")
    lib.keyleds_open.restype = ctypes.c_void_p
    lib.keyleds_open.argtypes = [ctypes.c_char_p, ctypes.c_uint8]
    lib.keyleds_mkeys_set.restype = ctypes.c_bool
    lib.keyleds_mkeys_set.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8]
    lib.keyleds_mrkeys_set.restype = ctypes.c_bool
    lib.keyleds_mrkeys_set.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8]
    lib.keyleds_close.argtypes = [ctypes.c_void_p]
    lib.keyleds_get_error_str.restype = ctypes.c_char_p
    return lib


def set_mkey_led(profile_name):
    """Lights exactly the M-key LED matching profile_name ('M1'/'M2'/
    'M3'), turning the others off (the mask REPLACES, doesn't add --
    confirmed empirically earlier: setting M2 turned M1 off
    automatically)."""
    if not _have_device():
        return False, "No G910 keyboard found -- is it plugged in?"
    mask = _MKEY_MASKS.get(profile_name)
    if mask is None:
        return False, f"Unknown profile: {profile_name}"
    lib = _keyleds_lib()
    device = _open_keyleds(lib)
    if not device:
        return False, lib.keyleds_get_error_str().decode()
    ok = lib.keyleds_mkeys_set(device, _KEYLEDS_TARGET_DEFAULT, mask)
    err = None if ok else lib.keyleds_get_error_str().decode()
    lib.keyleds_close(device)
    return bool(ok), err


def set_mrkey_led(on):
    if not _have_device():
        return False, "No G910 keyboard found -- is it plugged in?"
    lib = _keyleds_lib()
    device = _open_keyleds(lib)
    if not device:
        return False, lib.keyleds_get_error_str().decode()
    ok = lib.keyleds_mrkeys_set(device, _KEYLEDS_TARGET_DEFAULT, 0x01 if on else 0x00)
    err = None if ok else lib.keyleds_get_error_str().decode()
    lib.keyleds_close(device)
    return bool(ok), err

# G-keys (block "gkeys") use a DIFFERENT key-naming scheme than the main
# board (block "keys") -- confirmed empirically: "G1" is rejected, the
# real names are x01..x09. This map translates our friendly "G1".."G9"
# to what keyledsctl actually accepts for that block. The logo block
# uses the same x01/x02 convention (confirmed via get-leds -b logo).
GKEY_NAMES = {f"G{i}": f"x{i:02d}" for i in range(1, 10)}
LOGO_NAMES = {"LOGO1": "x01", "LOGO2": "x02"}

GROUPS = {
    "function_row": ("keys", ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"]),
    "gkeys": ("gkeys", [f"G{i}" for i in range(1, 10)]),
    "logo": ("logo", ["LOGO1", "LOGO2"]),
    "numpad": ("keys", [
        "NUMLOCK", "KPSLASH", "KPASTERISK", "KPMINUS", "KPPLUS", "KPENTER",
        "KP1", "KP2", "KP3", "KP4", "KP5", "KP6", "KP7", "KP8", "KP9", "KP0", "KPDOT",
    ]),
    "nav_cluster": ("keys", [
        "SYSRQ", "SCROLLLOCK", "PAUSE", "INSERT", "HOME", "PAGEUP",
        "DELETE", "END", "PAGEDOWN", "RIGHT", "LEFT", "DOWN", "UP",
    ]),
}


KEY_FIX_FILE = DATA_DIR / "g910_key_fix.json"
_key_fix_cache = {"mtime": None, "data": {}}


def load_key_fix():
    """{key_name: [red%, green%, blue%]} -- per-key colour correction
    for LEDs that no longer show colours true (e.g. a key whose red
    lights up too strongly gets red 40%). Re-read whenever the file
    changes so the app and a hand edit always agree."""
    try:
        mtime = KEY_FIX_FILE.stat().st_mtime
    except OSError:
        _key_fix_cache.update(mtime=None, data={})
        return {}
    if mtime != _key_fix_cache["mtime"]:
        try:
            data = json.loads(KEY_FIX_FILE.read_text())
            data = {k: [max(0, min(100, int(x))) for x in v][:3] for k, v in data.items()
                    if isinstance(v, list) and len(v) == 3}
        except (ValueError, TypeError, OSError):
            data = {}
        _key_fix_cache.update(mtime=mtime, data=data)
    return _key_fix_cache["data"]


def save_key_fix(key_name, gains):
    data = dict(load_key_fix())
    if gains is None or list(gains) == [100, 100, 100]:
        data.pop(key_name, None)
    else:
        data[key_name] = [int(g) for g in gains]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = KEY_FIX_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, KEY_FIX_FILE)


def _fix_channel(v, gain):
    return min(255, round(v * gain / 100))


def _unfix_channel(v, gain):
    # The original value nearest v*100/gain that the fix maps onto v,
    # so a chosen colour survives fix -> hardware -> read-back (ff stays
    # ff, 80 stays 80). A channel at gain 0 can't be recovered: report 0.
    if not gain:
        return v
    want = v * 100 / gain
    hits = [x for x in range(256) if _fix_channel(x, gain) == v]
    if not hits:
        return min(255, round(want))
    return min(hits, key=lambda x: (abs(x - want), -x))


def _fix_directive(directive, fixes):
    name, _, hexcolor = directive.partition("=")
    gains = fixes.get(name)
    if not gains or len(hexcolor.lstrip("#")) != 6:
        return directive
    h = hexcolor.lstrip("#")
    rgb = [_fix_channel(int(h[i:i + 2], 16), g) for i, g in zip((0, 2, 4), gains)]
    return f"{name}={rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _unfix_color(name, hexcolor, fixes):
    """Reverse of _fix_directive for read-back, so saved profiles and
    the on-screen preview hold the colour you CHOSE, not the corrected
    value actually sent (which would get corrected twice on reload)."""
    gains = fixes.get(name)
    if not gains:
        return hexcolor
    h = hexcolor.lstrip("#")
    rgb = [_unfix_channel(int(h[i:i + 2], 16), g) for i, g in zip((0, 2, 4), gains)]
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _run_set_leds(block, directives, raw=False):
    """directives: list of 'KEY=hexcolor' strings, sent in one call.
    Every colour write in the app goes through here, so this is where
    the per-key correction (load_key_fix) is applied, unless raw=True."""
    if not raw and block == "keys":
        fixes = load_key_fix()
        if fixes:
            directives = [_fix_directive(d, fixes) for d in directives]
    result = _kctl("set-leds", "-b", block, *directives)
    if result.returncode != 0:
        return False, result.stderr.strip() or f"exit code {result.returncode}"
    return True, None


def rainbow_hexes(n, brightness_pct=100, phase=0.0):
    """n evenly-spaced hues around the colour wheel (full saturation,
    value scaled by brightness_pct), in order -- one entry per key in
    a gradient. The order here is just "hue phase, phase+1/n, ..." --
    it's on the caller to supply key names in whatever order the
    gradient should sweep across the keyboard (left-to-right/top-to-
    bottom), since that ordering lives in the canvas's own cell
    geometry, not in this module. brightness_pct is applied here (not
    left to the caller to redo in QColor) so the hardware and any
    preview built from calling this again with the same arguments can
    never drift out of sync with each other. phase (any float, wraps
    via %1.0) rotates where hue 0 starts -- a one-shot call with
    phase=0 is exactly the static Rainbow preset; calling this again
    each animation tick with a slowly incrementing phase is what the
    Rainbow Wave effect actually is -- same function, not a separate
    implementation that could drift from the static version."""
    if n <= 0:
        return []
    factor = brightness_pct / 100.0
    hexes = []
    for i in range(n):
        h = (i / n + phase) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
        r = max(0, min(255, round(r * 255 * factor)))
        g = max(0, min(255, round(g * 255 * factor)))
        b = max(0, min(255, round(b * 255 * factor)))
        hexes.append("%02x%02x%02x" % (r, g, b))
    return hexes


def breathing_hex(base_rgb, phase, brightness_pct=100):
    """base_rgb breathing in and out -- phase 0..1 is one full cycle.
    A sine-based curve (not a linear ramp) so the turnaround at each
    end reads as a smooth breath rather than an abrupt reverse; never
    fully off (floors at 10% of brightness_pct) since a fully black
    keyboard mid-breath looks like the effect died, not like it's
    breathing."""
    factor = (brightness_pct / 100.0) * (0.1 + 0.9 * (0.5 - 0.5 * math.cos(phase * 2 * math.pi)))
    r, g, b = base_rgb
    r = max(0, min(255, round(r * factor)))
    g = max(0, min(255, round(g * factor)))
    b = max(0, min(255, round(b * factor)))
    return "%02x%02x%02x" % (r, g, b)


def cycle_hex(phase, brightness_pct=100):
    """One hue for the WHOLE zone at once, rotating over time -- phase
    0..1 is one full trip around the colour wheel. Same
    hsv_to_rgb/brightness math as rainbow_hexes, just n=1 conceptually
    (a single evolving colour, not a per-key gradient)."""
    factor = brightness_pct / 100.0
    r, g, b = colorsys.hsv_to_rgb(phase % 1.0, 1.0, 1.0)
    r = max(0, min(255, round(r * 255 * factor)))
    g = max(0, min(255, round(g * 255 * factor)))
    b = max(0, min(255, round(b * 255 * factor)))
    return "%02x%02x%02x" % (r, g, b)


def set_keys_rainbow(block, real_key_names, brightness_pct=100, phase=0.0):
    """Applies a rainbow gradient across real_key_names (already real
    keyledsctl names, already in the caller's intended visual order)
    in one block, one keyledsctl call. Generic building block reused
    for both the fixed GROUPS zones and Main Board -- unlike
    set_main_board_color, this never needs the whole-block "all="
    fill + restore dance: a rainbow has no single colour to give the
    six individually-unaddressable keys anyway, so this only ever
    touches keys that can actually take an individual colour, and
    leaves the rest showing whatever they already had -- same as any
    other per-key-only apply elsewhere in this module. phase forwards
    straight to rainbow_hexes() -- see there for what it does."""
    if not real_key_names:
        return False, "No keys to colour."
    hexes = rainbow_hexes(len(real_key_names), brightness_pct, phase)
    directives = [f"{k}={h}" for k, h in zip(real_key_names, hexes)]
    return _run_set_leds(block, directives)


def set_main_board_rainbow(real_key_names, brightness_pct=100, phase=0.0):
    """Kept as its own name for callers; every Main Board key is
    individually addressable (see EXTRA_KEYS), so this is just a plain
    per-key gradient with no whole-board fill and nothing to restore."""
    return set_keys_rainbow("keys", real_key_names, brightness_pct, phase)


def _real_key_name(block, key_name):
    if block == "gkeys":
        return GKEY_NAMES.get(key_name, key_name)
    if block == "logo":
        return LOGO_NAMES.get(key_name, key_name)
    return key_name


def set_key_color(key_name, hex_color, block="keys"):
    real_name = _real_key_name(block, key_name)
    return _run_set_leds(block, [f"{real_name}={hex_color}"])


def set_all_color(hex_color):
    return _run_set_leds("keys", [f"all={hex_color}"])


# The six modifier keys keyledsctl's own listing never shows. The
# device has 111 LED slots in block "keys" but reports "105 keys", and
# `keyledsctl get-leds` stops after 105 -- so the last six (HID usages
# 0xe2-0xe7) are cut off the end of the list. They were long believed
# to have no individual LED; they do, and keyledsctl accepts them by
# name. Verified on hardware: each one written a different colour and
# read back correctly from slot offset 105 via libkeyleds.
EXTRA_KEYS = ("LALT", "LMETA", "RCTRL", "RSHIFT", "RALT", "RMETA")
_EXTRA_KEYS_OFFSET = 105
_KEYLEDS_BLOCK_KEYS = 0x01


class _KeyColor(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint8), ("red", ctypes.c_uint8),
                ("green", ctypes.c_uint8), ("blue", ctypes.c_uint8)]


def _get_extra_key_colors():
    """{name: '#rrggbb'} for EXTRA_KEYS, read straight from the device.
    Empty dict on any failure -- callers treat these as optional."""
    if not _have_device():
        return {}
    try:
        lib = _keyleds_lib()
        lib.keyleds_get_leds.restype = ctypes.c_bool
        lib.keyleds_get_leds.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_int,
                                         ctypes.POINTER(_KeyColor), ctypes.c_uint16, ctypes.c_uint]
        device = _open_keyleds(lib)
        if not device:
            return {}
        try:
            arr = (_KeyColor * len(EXTRA_KEYS))()
            if not lib.keyleds_get_leds(device, _KEYLEDS_TARGET_DEFAULT, _KEYLEDS_BLOCK_KEYS,
                                        arr, _EXTRA_KEYS_OFFSET, len(EXTRA_KEYS)):
                return {}
        finally:
            lib.keyleds_close(device)
    except (OSError, AttributeError):
        return {}
    by_id = {k.id: f"#{k.red:02x}{k.green:02x}{k.blue:02x}" for k in arr}
    return {name: by_id[0xe2 + i] for i, name in enumerate(EXTRA_KEYS) if 0xe2 + i in by_id}


def _all_key_names(block="keys"):
    """Every key name in a block: the device's own live list (deduped,
    it lists BACKSLASH twice) plus, for "keys", the six modifiers its
    listing cuts off (see EXTRA_KEYS)."""
    if not _have_device():
        return []
    result = _kctl("get-leds", "-b", block)
    if result.returncode != 0:
        return []
    names = [line.split("=", 1)[0] for line in result.stdout.splitlines() if "=" in line]
    if block == "keys":
        names += EXTRA_KEYS
    return list(dict.fromkeys(names))


def _excluded_from_main_board():
    excluded = set()
    for group_name in ("function_row", "numpad", "nav_cluster"):
        _, keys = GROUPS[group_name]
        excluded.update(keys)
    return excluded


def set_main_board_color(hex_color):
    """'Main Board' = every key in block "keys" except the ones with
    their own zone button (F1-F12, Numpad, Nav Cluster). Sent as one
    plain per-key write. This used to be a whole-board "all=" fill
    followed by restoring the other three zones from a read-back,
    because the modifiers were thought to be reachable no other way --
    that flashed the other zones and could put stale colours back."""
    excluded = _excluded_from_main_board()
    names = [k for k in _all_key_names("keys") if k not in excluded]
    if not names:
        return False, "Couldn't read the current key list from the device."
    return _run_set_leds("keys", [f"{k}={hex_color}" for k in names])


def set_group_color(group_name, hex_color):
    if group_name not in GROUPS:
        return False, f"Unknown group: {group_name} (known: {list(GROUPS.keys())})"
    block, keys = GROUPS[group_name]
    directives = [f"{_real_key_name(block, key)}={hex_color}" for key in keys]
    return _run_set_leds(block, directives)


def get_key_color(key_name, block="keys"):
    if not _have_device():
        return None
    real_name = _real_key_name(block, key_name)
    result = _kctl("get-leds", "-b", block)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k == real_name:
            return v
    return None


def _get_block_colors(block):
    """{real_key_name: hexcolor} for every key currently reported by
    the device in this block -- read-only, live query, same source as
    _all_key_names/get_key_color."""
    if not _have_device():
        return {}
    result = _kctl("get-leds", "-b", block)
    if result.returncode != 0:
        return {}
    colors = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        colors[k] = v  # last one wins for the phantom duplicate BACKSLASH entry, harmless
    if block == "keys" and colors:
        colors.update(_get_extra_key_colors())
        fixes = load_key_fix()
        if fixes:
            colors = {k: _unfix_color(k, v, fixes) for k, v in colors.items()}
    return colors


def get_all_live_colors():
    """{our_friendly_key_name: hexcolor} across keys/gkeys/logo, for
    the GUI to sync its preview to the device's ACTUAL current state
    on startup. Translates device names back to our friendly ones for
    gkeys/logo (device reports x01..x09, our canvas uses G1../LOGO1/2)
    -- reverse of GKEY_NAMES/LOGO_NAMES. The six individually-
    unaddressable keys (Win/Alt/AltGr/Menu/right-Ctrl/right-Shift)
    can't be included here at all -- the device genuinely doesn't
    report an individual color for them (confirmed empirically), so
    the GUI has no way to know their current state short of guessing,
    which we don't do."""
    combined = {}
    for block in PROFILE_BLOCKS:
        colors = _get_block_colors(block)
        if block == "gkeys":
            reverse = {v: k for k, v in GKEY_NAMES.items()}
        elif block == "logo":
            reverse = {v: k for k, v in LOGO_NAMES.items()}
        else:
            reverse = {}
        for real_name, color in colors.items():
            friendly = reverse.get(real_name, real_name)
            combined[friendly] = color
    return combined


def load_profiles():
    if PROFILES_FILE.exists():
        try:
            return json.loads(PROFILES_FILE.read_text())
        except Exception:
            pass
    return {}


def list_profiles():
    return list(load_profiles().keys())


def _normalize_profile_entry(value):
    """Handles both profile-file shapes: the original plain
    {block: {key: color}} (pre-effects -- what every profile saved
    before this feature existed still uses on disk, real user data
    that must keep loading correctly) and the current
    {"snapshot": {...same as above...}, "effect": {...} or None}.
    Told apart by whether the value's own top-level keys are
    "snapshot"/"effect" -- real PROFILE_BLOCKS names ("keys"/"gkeys"/
    "logo") never collide with those two, so this is a real
    distinction, not a guess. Returns (snapshot_dict,
    effect_dict_or_None)."""
    if "snapshot" in value or "effect" in value:
        return value.get("snapshot", {}), value.get("effect")
    return value, None


def save_profile(name, effect=None):
    """Snapshots the CURRENT live color of every key across
    PROFILE_BLOCKS (keys/gkeys/logo -- media excluded, see
    PROFILE_BLOCKS comment) and stores it under `name`, overwriting any
    existing profile with that name. `effect`, if given (a dict like
    {"kind": "cycle", "target": "Main Board", "speed_pct": 100}), is
    saved alongside the snapshot so loading this profile back can also
    resume whatever animated effect was running when it was saved --
    without this, only the one frozen colour that happened to be
    showing at save time would ever come back. Always written in the
    current {"snapshot": ..., "effect": ...} shape; an older profile
    re-saved under the same name gets silently upgraded to this shape
    too, same one-touch migration pattern already used elsewhere in
    this codebase (e.g. the sensor-name alias migration) -- never a
    batch rewrite of the whole file."""
    snapshot = {block: _get_block_colors(block) for block in PROFILE_BLOCKS}
    if not any(snapshot.values()):
        return False, "Couldn't read any key colors from the device."
    profiles = load_profiles()
    profiles[name] = {"snapshot": snapshot, "effect": effect}
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2))
    return True, None


def load_profile(name):
    """Replays a saved profile block by block. Real key names stored
    in the snapshot (block "gkeys"/"logo" already use their real x01..
    names from the live query, not our friendly G1../LOGO1 aliases) --
    no _real_key_name() translation needed on the way back out.

    The six individually-unaddressable keys (Win/Alt/AltGr/Menu/
    right-Ctrl/right-Shift) were never captured in the snapshot in the
    first place -- get-leds never reports them, see
    _excluded_from_main_board's callers -- so without help they'd just
    keep whatever color was on the device before the load, silently
    diverging from the saved profile. Same fix as set_main_board_color:
    before writing the snapshot's exact per-key colors, fill block
    "keys" with the dominant color among the snapshot's own Main Board
    keys (the most common color there is, by definition, what the
    whole board was last bulk-filled to when the profile was saved).
    That reaches the six unaddressable keys the only way they CAN be
    reached. The per-key directives applied right after override the
    fill for every individually addressable key back to its exact
    saved color, so nothing else is approximated -- only the keys that
    have no other option. Returns (ok, err, effect) -- effect is
    whatever was saved alongside this profile (or None, including for
    every profile saved before this feature existed), so the caller
    can decide whether to resume an animation on top of the static
    snapshot this function already applies."""
    profiles = load_profiles()
    entry = profiles.get(name)
    if entry is None:
        return False, f"No such profile: {name}", None
    snapshot, effect = _normalize_profile_entry(entry)

    # Profiles saved before the six modifiers became readable (see
    # EXTRA_KEYS) don't contain them: give those the profile's most
    # common Main Board colour instead of leaving whatever was there.
    keys_colors = snapshot.get("keys")
    if keys_colors:
        missing = [k for k in EXTRA_KEYS if k not in keys_colors]
        excluded = _excluded_from_main_board()
        main_board_colors = [v for k, v in keys_colors.items() if k not in excluded]
        if missing and main_board_colors:
            dominant = Counter(main_board_colors).most_common(1)[0][0]
            snapshot = dict(snapshot, keys=dict(keys_colors, **{k: dominant for k in missing}))

    for block, colors in snapshot.items():
        if not colors:
            continue
        directives = [f"{key}={color}" for key, color in colors.items()]
        ok, err = _run_set_leds(block, directives)
        if not ok:
            return False, f"Failed applying block '{block}': {err}", None
    return True, None, effect


def delete_profile(name):
    profiles = load_profiles()
    if name not in profiles:
        return False, f"No such profile: {name}"
    del profiles[name]
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2))
    return True, None


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  g910_backlight.py all <hexcolor>          (literally every key in block 'keys')")
        print("  g910_backlight.py main_board <hexcolor>   (block 'keys' MINUS F1-F12/Numpad/Nav Cluster)")
        print("  g910_backlight.py key <KEYNAME> <hexcolor>")
        print("  g910_backlight.py group <groupname> <hexcolor>")
        print(f"  known groups: {list(GROUPS.keys())}")
        sys.exit(1)

    action = sys.argv[1]
    if action == "all":
        ok, err = set_all_color(sys.argv[2])
    elif action == "main_board":
        ok, err = set_main_board_color(sys.argv[2])
    elif action == "key":
        ok, err = set_key_color(sys.argv[2], sys.argv[3])
    elif action == "group":
        ok, err = set_group_color(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

    print("OK" if ok else f"FAILED: {err}")
