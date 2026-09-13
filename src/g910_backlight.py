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
# to what keyledsctl actually accepts for that block.
GKEY_NAMES = {f"G{i}": f"x{i:02d}" for i in range(1, 10)}

GROUPS = {
    "function_row": ("keys", ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"]),
    "gkeys": ("gkeys", [f"G{i}" for i in range(1, 10)]),
}


def _run_set_leds(block, directives):
    """directives: list of 'KEY=hexcolor' strings, sent in one call."""
    cmd = ["keyledsctl", "set-leds", "-d", DEVICE, "-b", block] + directives
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, result.stderr.strip() or f"exit code {result.returncode}"
    return True, None


def _real_key_name(block, key_name):
    return GKEY_NAMES.get(key_name, key_name) if block == "gkeys" else key_name


def set_key_color(key_name, hex_color, block="keys"):
    real_name = _real_key_name(block, key_name)
    return _run_set_leds(block, [f"{real_name}={hex_color}"])


def set_all_color(hex_color):
    return _run_set_leds("keys", [f"all={hex_color}"])


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
