# Installing g910-control

Two supported ways to install. Both end up in the same place — your
saved Profiles and macros always live under
`~/.local/share/g910-control/`, independent of which one you used.

## Before you start

Both options below assume `git` and a working `sudo` are already on
your system. If you installed Arch the normal way (`archinstall`),
you already have both. If you did a from-scratch manual install and
haven't set either up yet:

- **`git` missing?** `pacman -S git` (as root, or with `sudo` if you
  already have that part sorted).
- **No `sudo` yet?** That's a real security-relevant step this
  project isn't going to try to script for you — see the ArchWiki's
  [Sudo](https://wiki.archlinux.org/title/Sudo) page.
- **Don't want to install `git` at all?** See "No git? No problem"
  under Option 1 below — every release is also a plain downloadable
  archive.

## Option 1 — the script installer

```
git clone https://github.com/grumpybollocks/g910-control.git
cd g910-control
./install-g910.sh
```

**No git? No problem** — every tagged release is also a plain
archive, no git required:

```
curl -LO https://github.com/grumpybollocks/g910-control/archive/refs/tags/g910-v1.8.tar.gz
tar xzf g910-v1.8.tar.gz
cd g910-control-g910-v1.8
./install-g910.sh
```

(Swap `g910-v1.8` for whatever the [latest release](https://github.com/grumpybollocks/g910-control/releases/latest) tag actually is.)

This installs every dependency (checking what's already present
first, rather than a silent black-box `pacman -S`), sets up the
`g910-control` systemd `--user` service, and writes a desktop
launcher to both `~/Desktop` and `~/.local/share/applications`.

Dependencies it installs, and why each is there:

| Package | What it's for |
| --- | --- |
| `python-pyqt5`, `python-evdev` | the GUI and keyboard-event reading |
| `ydotool` | macro keystroke replay — ships its own `uinput` udev rule and its own `ydotool.service`, both needed for macros to actually fire |
| `keyleds` (AUR, via `yay`) | drives the keyboard's real HID++ 2.0 protocol; ships its own `hidraw` udev rule |
| `base-devel git cmake libevdev libuv libx11 libxi libyaml luajit systemd-libs` | build dependencies for `keyleds` itself |

## Option 2 — the Arch package

```
git clone https://github.com/grumpybollocks/g910-control.git
cd g910-control/packaging/g910-control
makepkg -si
```

`makepkg -si` builds and installs in one step, resolving official-repo
dependencies itself. **`keyleds` is an AUR package**, and plain
`makepkg`/`pacman` have no AUR awareness at all — that's specifically
what tools like `yay`/`paru` add. Install `keyleds` first with one of
those (`yay -S keyleds`), *then* run `makepkg -si` here. Not yet on
the AUR itself — see the note below.

Installing this way still leaves two things for you to do (pacman
never starts services or replugs hardware during a transaction — you'll
see these same instructions printed automatically right after
install):

```
systemctl --user daemon-reload
systemctl --user enable --now ydotool.service
systemctl --user enable --now g910-control.service
```

If `keyleds` was *just* installed fresh, its udev rule may not have
applied to an already-plugged-in keyboard yet — replug the G910, or:

```
sudo udevadm control --reload && sudo udevadm trigger
```

## Verifying it worked

```
keyledsctl list                              # should show the G910 (046d:c335)
ydotool key 28:1 28:0                        # sends an Enter keypress wherever focus is
systemctl --user status g910-control.service # should say "active"
```

## About the AUR

This package isn't on the AUR yet. Not because it isn't ready —
`packaging/g910-control/PKGBUILD` builds cleanly against this repo's
own real, tagged source with a verified `sha256sum` — but because the
AUR closed new account registration in mid-2026 after a large
supply-chain malware incident, and hasn't reopened it as of this
writing. See the [Releases](https://github.com/grumpybollocks/g910-control/releases)
page for the latest downloadable tag in the meantime.
