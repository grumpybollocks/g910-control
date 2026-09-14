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
# Check-then-report before installing anything, rather than a silent
# `pacman -S --needed` black box -- prints what's already present vs.
# what's about to actually change, per explicit request.
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
REPO_PKGS="base-devel git cmake libevdev libuv libx11 libxi libyaml luajit systemd-libs python-pyqt5 python-evdev python-dbus ydotool"
MISSING=""
for pkg in $REPO_PKGS; do
    if pacman -Qi "$pkg" &>/dev/null; then
        echo "  [ok]      $pkg"
    else
        echo "  [missing] $pkg"
        MISSING="$MISSING $pkg"
    fi
done
if [ -n "$MISSING" ]; then
    echo "Installing:$MISSING"
    sudo pacman -S --needed $MISSING
else
    echo "All official-repo dependencies already present."
fi

echo "=== 2/2: AUR package (keyleds -- needs yay) ==="
if pacman -Qi keyleds &>/dev/null; then
    echo "  [ok] keyleds"
else
    echo "  [missing] keyleds"
    if ! command -v yay &>/dev/null; then
        echo "yay not found -- can't auto-install keyleds. Install an AUR helper"
        echo "first (https://github.com/Jguer/yay -- or paru/whatever you prefer),"
        echo "then re-run this script. Make sure the 'keyleds' package ends up"
        echo "installed -- NOT 'keyleds-git', that's the abandoned original"
        echo "upstream. See G910_README.txt DECISIONS section for why."
        exit 1
    fi
    yay -S --needed keyleds
fi

echo
echo "=== ydotoold: enabling the replay daemon's own background service ==="
systemctl --user enable --now ydotool.service

echo
echo "=== systemd --user service: g910-macro-daemon (G-key/M-key playback) ==="
mkdir -p ~/.config/systemd/user
# Checked-in file has a __PROJECT_DIR__ placeholder instead of a real
# path (same reasoning as the desktop launcher below) -- substitute it
# here rather than committing any one checkout's location.
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
#
# Written to BOTH ~/Desktop (a literal desktop icon) AND
# ~/.local/share/applications (the standard XDG location every
# desktop environment's app menu/launcher actually reads) -- several
# DEs, GNOME notably, don't show desktop icons at all by default, so
# ~/Desktop alone would make the app undiscoverable there regardless
# of the path being correct.
DESKTOP_ENTRY="[Desktop Entry]
Type=Application
Name=G910 Control
Comment=Logitech G910 Orion Spectrum RGB + macro control
Exec=python3 \"$DIR/src/g910_app.py\"
Path=$DIR/src
Icon=input-keyboard
Terminal=false
Categories=Utility;"

mkdir -p "$HOME/Desktop"
echo "$DESKTOP_ENTRY" > "$HOME/Desktop/G910 Control.desktop"
chmod +x "$HOME/Desktop/G910 Control.desktop"
# GNOME/Nautilus also needs an explicit "trusted" flag or it shows an
# "Untrusted application launcher" warning instead of running --
# harmless no-op if gio isn't installed (e.g. KDE-only systems).
command -v gio &>/dev/null && gio set "$HOME/Desktop/G910 Control.desktop" metadata::trusted true 2>/dev/null || true

mkdir -p "$HOME/.local/share/applications"
echo "$DESKTOP_ENTRY" > "$HOME/.local/share/applications/g910-control.desktop"
chmod +x "$HOME/.local/share/applications/g910-control.desktop"

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
