# g910-control packaging

A real Arch/pacman PKGBUILD for the G910 app, alongside the existing
`install-g910.sh` git-clone install method (both are valid; this one
follows the standard "package installs everything to fixed `/usr/...`
locations, no per-user path discovery needed at all" pattern, verified
directly against `solaar`'s own real installed layout via
`pacman -Ql solaar` on a machine that has it installed).

## Status

Built and verified against a real, public source: the source repo has
been split out to a standalone public repo,
[grumpybollocks/g910-control](https://github.com/grumpybollocks/g910-control)
(G910-only history, `git-filter-repo`'d out of this combined, private
repo -- personal identifiers scrubbed from authorship and commit
messages, verified against a fresh clone of the real pushed remote,
not just the local working copy). This combined repo stays private and
untouched; `g910-control` is where the PKGBUILD's `source=` now
actually points. **Not yet submitted to the AUR itself** -- that's
still a separate, explicit step (see below).

## Dependencies

`depends=('python' 'keyleds' 'ydotool' 'python-pyqt5' 'python-evdev')`
-- `keyleds`/`ydotool` are used via `subprocess.run()`, not python
imports, so `namcap` flags them as "may not be needed"; that's a false
positive (it can't see subprocess calls to external binaries), both
are genuinely required at runtime.

## Layout

Same shape as `solaar`'s real installed package (`pacman -Ql solaar`),
confirmed directly rather than assumed:

- `/usr/bin/g910-control` -- thin wrapper, `exec`s the real script
- `/usr/lib/g910-control/*.py` -- the actual source, flat (no `src/`
  subdirectory -- the checked-in systemd service *template* has a
  `src/` segment baked in for the git-clone layout, so this
  PKGBUILD's `sed` strips `__PROJECT_DIR__/src` as one unit, not just
  `__PROJECT_DIR__` -- confirmed necessary via a real failed build
  before this was caught)
- `/usr/lib/systemd/user/g910-control.service`
- `/usr/share/applications/g910-control.desktop`
- `/usr/share/licenses/g910-control/LICENSE`

## sha256sums: resolved

`sha256sums` is a real hash now, not `SKIP` -- computed by actually
downloading the `g910-v1.4` tag archive from the now-public
`grumpybollocks/g910-control` repo and hashing it directly
(`sha256sum`), not copied or guessed.

## Local build + verification (what's actually been done)

1. `makepkg` against the real public URL
   (`https://github.com/grumpybollocks/g910-control/archive/refs/tags/g910-v1.4.tar.gz`)
   -- downloads, hash-validates, and builds clean, no local-tarball
   workaround needed anymore now that the source is genuinely public.
2. `pacman -U` installed for real on this machine. Confirmed:
   - `g910-control` launches from `/usr/bin/` and opens correctly.
   - `bl.DATA_DIR`/`bl.DEVICE` resolve correctly from the packaged
     copy (`~/.local/share/g910-control/`, the real discovered
     hidraw path) -- not hardcoded, not stale.
   - Live hardware round-trip (set a color, read it back) matches
     through the packaged files.
   - `systemd-analyze verify` passes on the packaged service unit
     after the `src/`-path bug above was found and fixed.
3. `namcap` run against both the PKGBUILD and the built package --
   one real, actionable finding fixed (`python` needed as an explicit
   dependency, not just relying on it coming in transitively via
   `python-pyqt5`); the `keyleds`/`ydotool` warnings are the false
   positive explained above, left as-is.
4. Extracted the actual built `.pkg.tar.zst` and grepped every file
   for personal identifiers (username, hostname, USB serial) --
   clean. The one hit found (`.BUILDINFO`'s `builddir`/`startdir`
   fields) is normal `makepkg` build metadata recording *this test
   build's own* local path -- it's never part of what's submitted to
   the AUR (only the PKGBUILD source is), and anyone else building
   this PKGBUILD gets their own `.BUILDINFO` with their own path, not
   this one.

## Before real AUR submission (not done yet, needs the user's go-ahead)

- Generate `.SRCINFO` (`makepkg --printsrcinfo > .SRCINFO`).
- Push to a dedicated `aur.archlinux.org` git remote for this package.
- Everything else (public source, real sha256sum, clean built-package
  audit) is done.
