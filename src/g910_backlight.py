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
import subprocess

DEVICE = "/dev/hidraw1"

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
    the real hardware."""
    result = subprocess.run(
        ["keyledsctl", "get-leds", "-d", DEVICE, "-b", block],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return [line.split("=", 1)[0] for line in result.stdout.splitlines() if "=" in line]


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


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  g910_backlight.py all <hexcolor>")
        print("  g910_backlight.py key <KEYNAME> <hexcolor>")
        print("  g910_backlight.py group <groupname> <hexcolor>")
        print(f"  known groups: {list(GROUPS.keys())}")
        sys.exit(1)

    action = sys.argv[1]
    if action == "all":
        ok, err = set_all_color(sys.argv[2])
    elif action == "key":
        ok, err = set_key_color(sys.argv[2], sys.argv[3])
    elif action == "group":
        ok, err = set_group_color(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

    print("OK" if ok else f"FAILED: {err}")
