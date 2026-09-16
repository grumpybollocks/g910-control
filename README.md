# g910-control

A native Linux control app for the **Logitech G910 Orion Spectrum**
gaming keyboard — per-key RGB lighting and G-key macros, driven
straight over its real HID++ 2.0 protocol. Logitech's own software
(G HUB / Logitech Gaming Software) is Windows-only, and nothing else
on Linux drives this keyboard's hardware properly, so this exists from
scratch: real USB/HID traffic, not a guess at what "should" work.

## Status

- **App**: stable, tagged [`g910-v1.4`](https://github.com/grumpybollocks/g910-control/releases/latest).
  Runs as your normal user, starts itself at login, keeps working
  through reboots/replugs/kernel updates.
- **Download**: see [Releases](https://github.com/grumpybollocks/g910-control/releases)
  for every tagged version and its notes.
- **AUR**: packaged (`packaging/g910-control/`), builds and installs
  cleanly via `makepkg`/`pacman` against this repo's own real tag
  archive with a verified `sha256sum` — **not yet actually submitted
  to the AUR itself**. Not a readiness problem on this package's side:
  the AUR closed new account registration mid-2026 after a large
  supply-chain malware incident and hadn't reopened it as of this
  writing. Build it locally from here in the meantime — see
  [`INSTALL.md`](INSTALL.md).
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

Two fully-supported ways — a plain script installer, or the real Arch
package — both covered step by step, including the two things that
still need doing manually after a package install (enabling the
background services, and a udev-rule replug), in
**[`INSTALL.md`](INSTALL.md)**.

## How it talks to the keyboard

Via `keyledsctl`/`libkeyleds.so` over the G910's real HID++ 2.0
protocol — reverse-engineered against the actual device, not assumed
from documentation that doesn't exist for this exact model. The
macro-playback side runs as a small systemd `--user` service so
recorded macros keep firing even with the GUI closed.

## License

[MIT](LICENSE).
