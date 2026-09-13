#!/bin/bash
# Dependency install for the G910 Orion Spectrum project on a fresh
# Manjaro/Arch install. Run this from inside the project folder:
#   ./install-g910.sh
#
# This ONLY installs dependencies -- it does not touch the keyboard or
# write any udev rules itself (the keyleds AUR package ships its own
# uaccess-based udev rule, confirmed working, see G910_README.txt).
# Safe to re-run any time -- pacman/yay --needed just skips what's
# already installed.
#
# This is a separate script from install.sh (that one is the sibling
# G510s LCD project's setup, different hardware, different deps -- see
# README.txt vs G910_README.txt).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== 1/2: Official repo packages ==="
# base-devel/git/cmake = AUR build tooling for the keyleds package below.
# libevdev/libuv/libx11/libxi/libyaml/luajit/systemd-libs = keyleds's own
# Depends (pre-installed here so yay won't prompt mid-build).
# python-pyqt5/python-evdev already proven via the sibling G510s app.
# python-dbus: NOT actually needed by the final architecture (this
# project ended up bypassing keyledsd entirely -- reads hidraw directly
# and uses keyledsctl/libkeyleds.so via ctypes instead, see
# G910_SKELETON.md) -- kept here anyway since it was part of the
# original confirmed-working install and costs nothing to have.
sudo pacman -S --needed base-devel git cmake libevdev libuv libx11 libxi \
    libyaml luajit systemd-libs python-pyqt5 python-evdev python-dbus

echo "=== 2/2: AUR package (keyleds -- needs yay) ==="
if ! command -v yay &>/dev/null; then
    echo "yay not found. Install an AUR helper first, then re-run this script."
    echo "(https://github.com/Jguer/yay -- or use paru/whatever you prefer, just"
    echo " make sure the 'keyleds' package ends up installed -- NOT 'keyleds-git',"
    echo " that's the abandoned original upstream. See G910_README.txt DECISIONS"
    echo " section for why.)"
    exit 1
fi
yay -S --needed keyleds

echo
echo "=== Done ==="
echo "Verify with: keyledsctl list"
echo "Should show this G910 (046d:c335) at a /dev/hidrawN path. If the"
echo "udev rule hasn't picked up yet, replug the keyboard or run:"
echo "  sudo udevadm control --reload && sudo udevadm trigger"
