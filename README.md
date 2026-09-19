# g910-control

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3-blue.svg)
![Platform: Arch Linux](https://img.shields.io/badge/platform-Arch%20Linux-1793d1.svg)
![G910: v1.12 stable](https://img.shields.io/badge/G910-v1.12%20stable-brightgreen.svg)

**Finally, real per-key RGB and macro control for the Logitech G910 Orion Spectrum on Linux — no Windows, no G HUB, no compromise.**

Logitech never shipped Linux support for this keyboard. G HUB is Windows-only, and every community tool that's tried to fill the gap has been old, abandoned, or half-working. `g910-control` talks to the keyboard directly over its real USB/HID protocol — not a workaround, not a guess — and gives you real per-key colour, animated lighting effects, and G-key macros, running natively as your own user.

![G910 Control app](docs/screenshots/g910-control-v2.png)

## Why you'd want this

- **Every key, any colour.** Click a key on the on-screen keyboard to colour it directly, drag-select a whole area at once, or bulk-colour a named zone (Logo, G-Keys, F-row, Numpad, Nav Cluster, Main Board) from the sidebar in one click.
- **A colour picker that doesn't fight you.** 15 named presets plus a hex field with a live preview swatch, and an optional native Colour Picker button if you'd rather eyeball it than type a hex.
- **A Random Colours preset**, one click. Sweeps a fresh colour-wheel gradient across whichever zone you've selected, in the keys' real physical order — a different starting hue every time you click it.
- **Animated effects** — Breathing, Colour Cycle, and Rainbow Wave — running in the background without freezing the rest of the app, with a Speed slider you can drag live, mid-animation.
- **G-keys that actually do something.** Record and play back macros across three switchable M1/M2/M3 profiles, with M1/M2/M3/MR rendered as real clickable parts of the keyboard, not just labels bolted on the side.
- **Save as many full lighting setups as you want**, and jump back to any of them instantly — including whichever animated effect was running, not just a frozen colour.
- **Set it up once, forget it's there.** Runs as a lightweight systemd `--user` service — starts itself at login, survives reboots, replugs, and kernel updates without you touching it again.
- **Works on your G910, not just the one it was built on.** Device paths are discovered at runtime from the actual hardware ID, never hardcoded to one physical unit.

## Status

- **App**: stable, tagged [`g910-v1.12`](https://github.com/grumpybollocks/g910-control/releases/latest).
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

## The cheeky bits

A few things that turned up along the way, because real hardware is
always quirkier than the docs — when there are any docs at all:

- Six keys on this keyboard (Win, Alt, AltGr, Menu, right-Ctrl,
  right-Shift) have **no individual LED at all** — not a driver
  limitation, a real hardware fact, found the only way it could be:
  by asking the device directly and it simply not answering for
  those six. They only ever get coloured as a side effect of a
  whole-board fill, never individually.
- There is no official documentation for this keyboard's lighting
  protocol. None. Every "how does this actually work" answer in this
  project came from watching real HID++ 2.0 traffic, not a spec sheet.
- Building the animated effects surfaced a genuinely fun hardware
  quirk: asking the keyboard to *read* its own current colours while
  something else is *writing* new ones at the same time doesn't queue
  up politely — it just corrupts the response. Real protocol-level
  rock-paper-scissors, not a software bug to patch around.

## License

[MIT](LICENSE).
