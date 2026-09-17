# g910-control packaging

A real Arch/pacman PKGBUILD for the G910 app, alongside the existing
`install-g910.sh` git-clone install method (both are valid; this one
follows the standard "package installs everything to fixed `/usr/...`
locations, no per-user path discovery needed at all" pattern, verified
directly against `solaar`'s own real installed layout via
`pacman -Ql solaar` on a machine that has it installed).

## Status

Built and verified against a real, public source:
[grumpybollocks/g910-control](https://github.com/grumpybollocks/g910-control)
(G910-only history, originally `git-filter-repo`'d out of a combined,
private repo -- personal identifiers scrubbed from authorship and
commit messages, verified against a fresh clone of the real pushed
remote, not just the local working copy). As of 2026-09-17 that
original combined repo has removed the G910 app from its `main`
branch entirely -- this standalone repo is now the sole home for
G910's source, not a mirror of it. **Not yet submitted to the AUR
itself** -- that's still a separate, explicit step (see below).

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
downloading the `g910-v1.5` tag archive from the now-public
`grumpybollocks/g910-control` repo and hashing it directly
(`sha256sum`), not copied or guessed.

## Local build + verification (what's actually been done)

**For the current v1.5 tag, specifically** (real, done this pass --
not carried over from an older version's testing):

1. `makepkg` against the real public URL
   (`https://github.com/grumpybollocks/g910-control/archive/refs/tags/g910-v1.5.tar.gz`)
   -- downloads, hash-validates, and builds clean.
2. `namcap` against both the PKGBUILD and the built package -- clean
   except the two known false positives (`keyleds`/`ydotool` "may not
   be needed" -- namcap can't see the `subprocess.run()` calls to
   those binaries this app genuinely makes).
3. Extracted the actual built `.pkg.tar.zst` and grepped every file
   for personal identifiers -- clean (the one hit,
   `.BUILDINFO`'s `builddir`/`startdir`, is normal `makepkg` metadata
   about *this test build's own* local path, never part of what's
   submitted to the AUR).
4. A real headless PyQt5 launch (`QT_QPA_PLATFORM=offscreen`) of the
   **actual extracted built package's files** -- not just the source
   checkout -- with no keyboard simulated. Confirmed it constructs
   without crashing (this is exactly the bug v1.5 fixes).

**Now also done for v1.5 itself** (2026-09-17, after the user installed
it): a real `pacman -U` upgrade on real hardware, confirmed the
`post_upgrade()` hook printed correctly, `g910-control.service`
restarted and reported `active`, and a live hardware round-trip
through the actual installed package
(`bl.set_group_color("function_row", "a020f0")` then
`bl.get_key_color("F1")` -- returned `#a020f0` exactly) -- run against
`/usr/lib/g910-control/`'s real installed files, not the source
checkout.

**v1.6** (the Rainbow preset, same day): real build against the live
`g910-v1.6` URL, `namcap` clean (same two known false positives),
extracted-package personal-identifier audit clean, and a headless
launch of the actual built package with no keyboard simulated --
confirmed clicking Rainbow with no G910 attached fails gracefully
instead of crashing. The gradient logic itself was verified on real
hardware *before* packaging (backend directly: genuinely different
colours per key, brightness scaling reaching the device exactly;
full GUI path: preview colour matched hardware readback exactly;
Main Board case: function-row keys correctly left untouched while
real main-board keys got real distinct colours) -- see that commit's
message for the exact values. Not yet re-confirmed via a real
`pacman -U` of v1.6 itself.

**v1.7** (three animated effects, plus a real sidebar-width fix): real
build against the live `g910-v1.7` URL, `namcap` clean, extracted-
package audit clean, and a headless launch of the actual built
package confirming an effect started with no keyboard fails through
the same graceful `tick_failed` path a real mid-effect disconnect
would use, not just at start time. The effects' own colour-changes-
over-time behaviour, the effect-switching/thread-cleanup logic, and a
real device-level read-vs-write conflict this surfaced (fixed by
stopping any running effect before a profile save/load) were all
verified on real hardware *before* this tag was cut -- see that
commit's message for the exact reproduction and fix.

## Before real AUR submission (not done yet, needs the user's go-ahead)

- Generate `.SRCINFO` (`makepkg --printsrcinfo > .SRCINFO`).
- Push to a dedicated `aur.archlinux.org` git remote for this package.
- Everything else (public source, real sha256sum, clean built-package
  audit) is done.
