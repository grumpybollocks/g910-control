#!/usr/bin/env python3
"""
G910 Backlight -- barebones skeleton, no GUI.

Purpose: prove the core color-control primitives work reliably before
building anything on top. Wraps `keyledsctl set-leds`/`get-leds`
against LED block 01 ("keys", 105 keys, confirmed true per-key RGB on
this exact hardware -- see G910_README.txt). Not wired to a daemon or
GUI yet -- run directly for now, see the __main__ block at the bottom.

Groups below are a minimal hardcoded starting point (not the full
Solaar-derived layout geometry from planning) -- just enough to prove
"set a named group of keys at once" works before investing in the real
layout data.
"""
import ctypes
import json
import subprocess
from pathlib import Path

DEVICE = "/dev/hidraw1"
PROFILES_FILE = Path(__file__).resolve().parent.parent / "g910_profiles.json"
# Blocks a full lighting snapshot covers. "media" deliberately excluded
# -- paused per the user's explicit instruction not to touch it, see
# G910_SKELETON.md.
PROFILE_BLOCKS = ("keys", "gkeys", "logo")

# M-key/MR indicator LEDs are NOT controlled through keyledsctl (it has
# no subcommand for this at all -- confirmed by reading
# keyledsctl_gkeys.c, it only calls keyleds_gkeys_enable). They go
# through libkeyleds.so directly via ctypes -- keyleds_mkeys_set/
# keyleds_mrkeys_set, exported functions, proven working earlier this
# project (see G910_README.txt M-KEY/MR INDICATOR LED CONTROL section).
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
    cmd = ["keyledsctl", "set-leds", "-d", DEVICE, "-b", block] + directives
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, result.stderr.strip() or f"exit code {result.returncode}"
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
    result = subprocess.run(
        ["keyledsctl", "get-leds", "-d", DEVICE, "-b", block],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    names = [line.split("=", 1)[0] for line in result.stdout.splitlines() if "=" in line]
    return list(dict.fromkeys(names))


def set_main_board_color(hex_color):
    """'Main Board' means everything in block "keys" EXCEPT the keys
    that belong to their own dedicated group buttons (F1-F12, Numpad,
    Nav Cluster) -- NOT literally every key in the block. Using the
    "all" keyword here was a real bug: it silently recolored F1-F12/
    Numpad/Nav Cluster too, since they physically live in the same
    block, confirmed by the user seeing F-keys change color when they
    only asked for Main Board."""
    excluded = set()
    for group_name in ("function_row", "numpad", "nav_cluster"):
        _, keys = GROUPS[group_name]
        excluded.update(keys)
    remaining = [k for k in _all_key_names("keys") if k not in excluded]
    if not remaining:
        return False, "Couldn't read the current key list from the device."
    directives = [f"{k}={hex_color}" for k in remaining]
    return _run_set_leds("keys", directives)


def set_group_color(group_name, hex_color):
    if group_name not in GROUPS:
        return False, f"Unknown group: {group_name} (known: {list(GROUPS.keys())})"
    block, keys = GROUPS[group_name]
    directives = [f"{_real_key_name(block, key)}={hex_color}" for key in keys]
    return _run_set_leds(block, directives)


def get_key_color(key_name, block="keys"):
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


def load_profiles():
    if PROFILES_FILE.exists():
        try:
            return json.loads(PROFILES_FILE.read_text())
        except Exception:
            pass
    return {}


def list_profiles():
    return list(load_profiles().keys())


def save_profile(name):
    """Snapshots the CURRENT live color of every key across
    PROFILE_BLOCKS (keys/gkeys/logo -- media excluded, see
    PROFILE_BLOCKS comment) and stores it under `name`, overwriting any
    existing profile with that name."""
    snapshot = {block: _get_block_colors(block) for block in PROFILE_BLOCKS}
    if not any(snapshot.values()):
        return False, "Couldn't read any key colors from the device."
    profiles = load_profiles()
    profiles[name] = snapshot
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2))
    return True, None


def load_profile(name):
    """Replays a saved profile block by block. Real key names stored
    in the snapshot (block "gkeys"/"logo" already use their real x01..
    names from the live query, not our friendly G1../LOGO1 aliases) --
    no _real_key_name() translation needed on the way back out."""
    profiles = load_profiles()
    snapshot = profiles.get(name)
    if snapshot is None:
        return False, f"No such profile: {name}"
    for block, colors in snapshot.items():
        if not colors:
            continue
        directives = [f"{key}={color}" for key, color in colors.items()]
        ok, err = _run_set_leds(block, directives)
        if not ok:
            return False, f"Failed applying block '{block}': {err}"
    return True, None


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
