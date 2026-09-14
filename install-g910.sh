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
# ydotool: macro replay mechanism for g910_macro_daemon.py (same
# mechanism the sibling G510s project's daemon already uses). Official
# extra repo, not AUR -- confirmed via `pacman -Si`/`pacman -Fl` before
# adding it here, not assumed. Ships both the `ydotool` client and the
# `ydotoold` background daemon it talks to, plus its own systemd --user
# service unit and udev rule for uinput permissions -- nothing to
# hand-write for those.
sudo pacman -S --needed base-devel git cmake libevdev libuv libx11 libxi \
    libyaml luajit systemd-libs python-pyqt5 python-evdev python-dbus ydotool

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
echo "=== ydotoold: enabling the replay daemon's own background service ==="
systemctl --user enable --now ydotool.service

echo
echo "=== systemd --user service: g910-macro-daemon (G-key/M-key playback) ==="
mkdir -p ~/.config/systemd/user
# Checked-in file has a __PROJECT_DIR__ placeholder instead of a real path
# (same reasoning as the desktop launcher above) -- substitute it here
# rather than committing any one checkout's location.
sed "s|__PROJECT_DIR__|$DIR|g" services/g910-macro-daemon.service > ~/.config/systemd/user/g910-macro-daemon.service
systemctl --user daemon-reload
systemctl --user enable --now g910-macro-daemon.service

echo
echo "=== Desktop launcher ==="
# Written here with the REAL resolved $DIR, not a hardcoded path --
# the sibling G510s project's install.sh assumes its .desktop files
# already exist with the right path baked in by hand, which turned out
# to be hardcoded to one specific machine/user and silently breaks
# anywhere else (found during a reboot-safety audit). Generating it
# here from $DIR avoids repeating that exact mistake.
DESKTOP_FILE="$HOME/Desktop/G910 Control.desktop"
mkdir -p "$HOME/Desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=G910 Control
Comment=Logitech G910 Orion Spectrum RGB + macro control
Exec=python3 "$DIR/src/g910_app.py"
Path=$DIR/src
Icon=input-keyboard
Terminal=false
Categories=Utility;
EOF
chmod +x "$DESKTOP_FILE"
# GNOME/Nautilus also needs an explicit "trusted" flag or it shows an
# "Untrusted application launcher" warning instead of running --
# harmless no-op if gio isn't installed (e.g. KDE-only systems).
command -v gio &>/dev/null && gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true

echo
echo "=== Done ==="
echo "Verify keyleds with: keyledsctl list"
echo "Should show this G910 (046d:c335) at a /dev/hidrawN path. If the"
echo "udev rule hasn't picked up yet, replug the keyboard or run:"
echo "  sudo udevadm control --reload && sudo udevadm trigger"
echo
echo "Verify ydotool with: ydotool key 28:1 28:0   (should send an Enter"
echo "keypress wherever your cursor currently has focus)"
echo
echo "Verify the macro daemon with: systemctl --user status g910-macro-daemon.service"
