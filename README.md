# g910-control

**Finally, real per-key RGB and macro control for the Logitech G910 Orion Spectrum on Linux — no Windows, no G HUB, no compromise.**

Logitech never shipped Linux support for this keyboard. G HUB is Windows-only, and every community tool that's tried to fill the gap has been old, abandoned, or half-working. `g910-control` talks to the keyboard directly over its real USB/HID protocol — not a workaround, not a guess — and gives you real per-key colour and G-key macros, running natively as your own user. (No animated lighting effects yet — breathing/wave/cycle-style animations aren't implemented — if that's what you're after, this isn't there yet; everything else below is.)

![G910 Control app](docs/screenshots/g910-control-v2.png)

## Why you'd want this

- **Every key, any colour.** Click a key on the on-screen keyboard to colour it directly, drag-select a whole area at once, or bulk-colour a named zone (Logo, G-Keys, F-row, Numpad, Nav Cluster, Main Board) from the sidebar in one click.
- **A colour picker that doesn't fight you.** Named presets plus a hex field — no fiddly native colour-picker dialog getting in the way.
- **G-keys that actually do something.** Record and play back macros across three switchable M1/M2/M3 profiles, with M1/M2/M3/MR rendered as real clickable parts of the keyboard, not just labels bolted on the side.
- **Save as many full lighting setups as you want**, and jump back to any of them instantly.
- **Set it up once, forget it's there.** Runs as a lightweight systemd `--user` service — starts itself at login, survives reboots, replugs, and kernel updates without you touching it again.
- **Works on your G910, not just the one it was built on.** Device paths are discovered at runtime from the actual hardware ID, never hardcoded to one physical unit.

## Status

- **App**: stable, tagged [`g910-v1.5`](https://github.com/grumpybollocks/g910-control/releases/latest).
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

## License

[MIT](LICENSE).
