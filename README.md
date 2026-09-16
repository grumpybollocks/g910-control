# g910-control

A native Linux control app for the **Logitech G910 Orion Spectrum**
gaming keyboard — per-key RGB lighting and G-key macros, driven
straight over its real HID++ 2.0 protocol. Logitech's own software
(G HUB / Logitech Gaming Software) is Windows-only, and nothing else
on Linux drives this keyboard's hardware properly, so this exists from
scratch: real USB/HID traffic, not a guess at what "should" work.

## Status

- **App**: stable, tagged `g910-v1.3`. Runs as your normal user, starts
  itself at login, keeps working through reboots/replugs/kernel
  updates.
- **AUR**: packaged (`packaging/g910-control/`), builds and installs
  cleanly via `makepkg`/`pacman` against this repo's own real tag
  archive — **not yet actually submitted to the AUR itself** (that's a
  separate, explicit step).
- This repo is G910-only, on purpose. If you're looking for the
  companion Logitech **G510s** app (LCD screen, backlight, macros) —
  different keyboard, different codebase, developed and released
  separately.

## What it does

One window built around a real on-screen render of the keyboard:
click any key to colour it, drag-select a whole area, or use the
Colour Mode sidebar to bulk-colour a named zone (Logo, G-Keys, F-row,
Numpad, Nav Cluster, Main Board). A compact colour picker (named
presets + a hex field) replaces the fiddly native colour-picker
dialog. G-key macros record/playback across M1/M2/M3 profiles, with
M1/M2/M3/MR shown as real clickable parts of the keyboard picture, not
just labels. Any number of full lighting setups can be saved and
reloaded as Profiles.

Device paths (both the RGB control interface and the keyboard's input
event device) are discovered at runtime by matching the actual
hardware's vendor/product ID (`046d:c335`) — not hardcoded to one
specific physical unit, so this works on any G910, not just the one it
was built on.

![G910 Control app](docs/screenshots/g910-control-v2.png)

## Installing

Two ways, both fully supported:

1. **`./install-g910.sh`** — clones this repo, installs every
   dependency, drops the systemd `--user` service and desktop launcher
   in place. Good for following along with development, or if you'd
   rather not go through pacman.
2. **The real Arch package** (`packaging/g910-control/PKGBUILD`) —
   `makepkg` against this repo's own tagged source, then `pacman -U`.
   Installs to the standard fixed `/usr/...` locations (see that
   folder's own `README.md` for the exact layout and what's been
   verified).

Either way, your saved Profiles/macros live under
`~/.local/share/g910-control/`, independent of which install method
you used or whether you later switch between them.

## How it talks to the keyboard

Via `keyledsctl`/`libkeyleds.so` over the G910's real HID++ 2.0
protocol — reverse-engineered against the actual device, not assumed
from documentation that doesn't exist for this exact model. The
macro-playback side runs as a small systemd `--user` service so
recorded macros keep firing even with the GUI closed.

## License

[MIT](LICENSE).
