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
    if DEVICE is None:
        return False, "No G910 keyboard found -- is it plugged in?"
    mask = _MKEY_MASKS.get(profile_name)
    if mask is None:
        return False, f"Unknown profile: {profile_name}"
    lib = _keyleds_lib()
    device = lib.keyleds_open(DEVICE.encode(), _KEYLEDSCTL_APP_ID)
    if not device:
        return False, lib.keyleds_get_error_str().decode()
    ok = lib.keyleds_mkeys_set(device, _KEYLEDS_TARGET_DEFAULT, mask)
    err = None if ok else lib.keyleds_get_error_str().decode()
    lib.keyleds_close(device)
    return bool(ok), err


def set_mrkey_led(on):
    if DEVICE is None:
        return False, "No G910 keyboard found -- is it plugged in?"
    lib = _keyleds_lib()
    device = lib.keyleds_open(DEVICE.encode(), _KEYLEDSCTL_APP_ID)
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


def _run_set_leds(block, directives):
    """directives: list of 'KEY=hexcolor' strings, sent in one call."""
    if DEVICE is None:
        return False, "No G910 keyboard found -- is it plugged in?"
    cmd = ["keyledsctl", "set-leds", "-d", DEVICE, "-b", block] + directives
    result = subprocess.run(cmd, capture_output=True, text=True)
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
    """Rainbow gradient across Main Board's addressable keys, PLUS a
    real colour for the six individually-unaddressable keys (Win/Alt/
    AltGr/Menu/right-Ctrl/right-Shift) instead of leaving them
    whatever they last were -- the actual bug the user kept hitting:
    set_keys_rainbow alone just skips those six, so they sat there
    visibly grey/stale while the rest of the board got a gradient.

    Same whole-block-fill-then-restore dance set_main_board_color
    uses (fill everything via "all=", including the six unreachable-
    by-name keys, then in one more call restore F1-F12/Numpad/Nav
    Cluster to what they had and lay the real per-key gradient on top
    of the fill for Main Board's own addressable keys) -- except the
    fill colour here is the gradient's own first hue rather than a
    flat colour someone picked, since there's no single "the" colour
    for a rainbow to give a key it can't individually address."""
    if not real_key_names:
        return False, "No keys to colour."
    excluded = _excluded_from_main_board()
    current = _get_block_colors("keys")
    if not current:
        return False, "Couldn't read the current key list from the device."
    preserve = {k: v for k, v in current.items() if k in excluded}

    hexes = rainbow_hexes(len(real_key_names), brightness_pct, phase)
    ok, err = _run_set_leds("keys", [f"all={hexes[0]}"])
    if not ok:
        return False, err

    directives = [f"{k}={h}" for k, h in zip(real_key_names, hexes)]
    if preserve:
        directives += [f"{k}={v.lstrip('#')}" for k, v in preserve.items()]
    ok, err = _run_set_leds("keys", directives)
    if not ok:
        return False, f"Fill succeeded but per-key gradient/restore failed: {err}"
    return True, None


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


def _all_key_names(block="keys"):
    """Live list of every key name the device itself reports for a
    block -- queried, not hardcoded, so it can't drift out of sync with
    the real hardware. Deduped: "keys" lists BACKSLASH twice (one
    permanently-inert phantom zone, confirmed by testing -- it never
    changes color even on a whole-keyboard write -- plus the one real,
    addressable zone). Sending the same key twice in one set-leds call
    is harmless but pointless."""
    if DEVICE is None:
        return []
    result = subprocess.run(
        ["keyledsctl", "get-leds", "-d", DEVICE, "-b", block],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    names = [line.split("=", 1)[0] for line in result.stdout.splitlines() if "=" in line]
    return list(dict.fromkeys(names))


def _excluded_from_main_board():
    excluded = set()
    for group_name in ("function_row", "numpad", "nav_cluster"):
        _, keys = GROUPS[group_name]
        excluded.update(keys)
    return excluded


def set_main_board_color(hex_color):
    """'Main Board' means every colorable key in block "keys" EXCEPT
    the keys that belong to their own dedicated group buttons
    (F1-F12, Numpad, Nav Cluster) -- NOT literally every key.

    Real correction found via the user's own testing, not assumed:
    Win/Alt/AltGr/Menu/right-Ctrl/right-Shift have no INDIVIDUAL LED
    (confirmed empirically much earlier -- they never appear in
    get-leds's per-key listing, and addressing them by name is
    rejected), but they DO respond to the whole-block "all=" fill --
    confirmed live: sending all=00ff00 turned them green along with
    everything else. Different underlying HID++ function
    (keyleds_set_led_block, a uniform block fill) than per-key
    directives (keyleds_set_leds) -- keyledsctl's "all=" keyword uses
    the block-fill function, confirmed by reading
    keyledsctl_set_leds.c's real source directly.

    So Main Board now reaches those keys too: snapshot F1-F12/Numpad/
    Nav Cluster's CURRENT colors first, do the whole-block fill
    (which reaches everything including the previously-unreachable
    keys), then restore just those three groups back to what they
    were -- undoing the fill's side effect on the keys that have their
    own dedicated buttons, without losing the ability to color
    everything else."""
    excluded = _excluded_from_main_board()

    current = _get_block_colors("keys")
    if not current:
        return False, "Couldn't read the current key list from the device."
    preserve = {k: v for k, v in current.items() if k in excluded}

    ok, err = _run_set_leds("keys", [f"all={hex_color}"])
    if not ok:
        return False, err

    if preserve:
        restore_directives = [f"{k}={v.lstrip('#')}" for k, v in preserve.items()]
        ok, err = _run_set_leds("keys", restore_directives)
        if not ok:
            return False, f"Fill succeeded but restoring F1-F12/Numpad/Nav Cluster failed: {err}"
    return True, None


def set_group_color(group_name, hex_color):
    if group_name not in GROUPS:
        return False, f"Unknown group: {group_name} (known: {list(GROUPS.keys())})"
    block, keys = GROUPS[group_name]
    directives = [f"{_real_key_name(block, key)}={hex_color}" for key in keys]
    return _run_set_leds(block, directives)


def get_key_color(key_name, block="keys"):
    if DEVICE is None:
        return None
    real_name = _real_key_name(block, key_name)
    result = subprocess.run(
        ["keyledsctl", "get-leds", "-d", DEVICE, "-b", block],
        capture_output=True, text=True,
    )
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
    if DEVICE is None:
        return {}
    result = subprocess.run(
        ["keyledsctl", "get-leds", "-d", DEVICE, "-b", block],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {}
    colors = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        colors[k] = v  # last one wins for the phantom duplicate BACKSLASH entry, harmless
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

    keys_colors = snapshot.get("keys")
    if keys_colors:
        excluded = _excluded_from_main_board()
        main_board_colors = [v for k, v in keys_colors.items() if k not in excluded]
        if main_board_colors:
            dominant = Counter(main_board_colors).most_common(1)[0][0]
            ok, err = _run_set_leds("keys", [f"all={dominant.lstrip('#')}"])
            if not ok:
                return False, f"Failed pre-filling Main Board: {err}", None

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
