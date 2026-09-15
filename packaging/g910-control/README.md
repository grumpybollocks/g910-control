# g910-control packaging

A real Arch/pacman PKGBUILD for the G910 app, alongside the existing
`install-g910.sh` git-clone install method (both are valid; this one
follows the standard "package installs everything to fixed `/usr/...`
locations, no per-user path discovery needed at all" pattern, verified
against `solaar`'s own real installed layout -- see `PORTABILITY.md`).

## Status

Built and verified locally. **Not yet submitted to the AUR** -- that's
a separate, explicit step, and the source repo needs to be public
first (see below).

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

## Known gap: sha256sums

`sha256sums=('SKIP')` right now. The source repo is currently private
while the app is being finished, so the release tarball can't be
fetched to hash it for real -- `SKIP` is the honest, standard PKGBUILD
value for "not yet verifiable," not a guessed/fake hash. **Must** be
replaced with a real sum (`updpkgsums`, or `sha256sum` the tarball by
hand) once the repo is public, before any real AUR submission.

## Local build + verification (what's actually been done)

1. `makepkg` against a local source tarball built from a real `git
   archive` of the `g910` branch at the `g910-v1.2` tag (not the
   private GitHub URL directly, for the reason above) -- builds
   clean.
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
   for personal identifiers (username, hostname, USB serial) -- found
   and removed two comments in `g910_app.py`/`g910_backlight.py` that
   named this machine's specific keyboard's USB serial number as an
   example; re-verified clean after the fix.

## Before real AUR submission (not done yet, needs the user's go-ahead)

- Make the source repo public (or point `source=` at whatever new
  repo replaces it) and compute a real `sha256sum`.
- Generate `.SRCINFO` (`makepkg --printsrcinfo > .SRCINFO`).
- Push to a dedicated `aur.archlinux.org` git remote for this package.
