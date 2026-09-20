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

**v1.8** (effects preview bug fix, live Speed slider, Profiles now
remember an active effect, plus the fresh-install/landing-page docs
pass): real build against the live `g910-v1.8` URL, `namcap` clean,
extracted-package audit clean. Every source change was verified on
real hardware *before* this tag was cut, not after -- the preview
bug fix, the Speed slider's live tick-timing at three different
settings on the same running thread, and the full save-mid-effect/
load-and-resume round trip, including a byte-for-byte hash check of
this machine's real 8 saved profiles before and after every test to
confirm none of them were touched by the format-migration shim -- see
that commit's message for the exact numbers. The `git`/`sudo`
prerequisite gap in `INSTALL.md`/`install-g910.sh` was checked
against Arch's own real `base-devel` package group contents, not
guessed.

**v1.9** (canvas-click-stops-effect consistency fix): a self-audit
found a real gap -- clicking a key directly on the keyboard image
while an effect was running elsewhere on the same zone could have its
colour silently overwritten by the effect's next tick, unlike every
other static-apply path, which already stopped a running effect
first. Confirmed with the user it was worth fixing rather than left
as a self-correcting ~100ms flicker. Real build against the live
`g910-v1.9` URL, `namcap` clean, extracted-package audit clean.

**v1.10** (Main Board rainbow no longer leaves keys grey, Effects
split into its own WIP tab, randomized rainbow phase): the static
Rainbow preset previously only sent per-key gradient directives, which
genuinely cannot address Win/Alt/AltGr/Menu/right-Ctrl/right-Shift --
so on Main Board those six keys just sat there at whatever stale
colour they already had, visibly grey against the rest of the
gradient. New `set_main_board_rainbow()` does the same whole-block
"all=" fill + F1-F12/Numpad/Nav-Cluster-restore dance `set_main_board_
color()` already used for the static colour case, using the
gradient's own first hue as the fill colour, so those six keys now get
a real colour instead of being skipped. The `set_main_board_rainbow`
calls themselves were run directly against the real device
(`/dev/hidraw1`, both calls returned success) -- but `get-leds`
genuinely can't read these six keys back by design (confirmed
earlier), so that only proves the command was accepted, not that the
LEDs visibly changed; final confirmation needs the user to actually
look at the physical keyboard. Rainbow also now randomizes its
starting hue (`phase`) on every click instead of the same fixed
gradient each time, per direct request. Breathing/Colour Cycle/
Rainbow Wave/Speed slider moved out of the Color Mode panel into a
separate "Effects (WIP)" tab -- marked work-in-progress because the
on-screen preview for a few keys can still lag the real keyboard
during an animation, unlike the one-shot Rainbow/preset applies.
Switching zones or tabs now stops any running effect automatically,
and there's a dedicated Stop Effects button. Real build against the
live `g910-v1.10` URL, `namcap` clean (same two known false
positives), extracted-package personal-data audit clean, headless
launch of the actual built package with no keyboard simulated. Also
caught and fixed a real sha256 transcription error (one trailing hex
character dropped when copying the hash into this PKGBUILD) before it
shipped -- re-verified with a fresh `sha256sum` run, not by eye a
second time.

**v1.11** (Random colours rename, 6 more presets, Profiles panel
height fix, G-Keys section separator): all four items came directly
from live use immediately after installing v1.10. Rainbow renamed to
"Random colours" (button/tooltip/status text) since v1.10 already
made it randomize its starting hue per click, so the old name no
longer matched what it does. `PRESET_COLORS` gained White, Gold,
Teal, Indigo, Sky Blue, Lime (9 -> 15) -- the new Gold swatch applied
to F1-F12 and read back via `get_key_color` exactly (`#ffd700`) on
real hardware before shipping. `ProfilesTab`'s saved-profiles scroll
area previously always claimed its full 300px cap regardless of
content -- `setMaximumHeight` alone doesn't shrink a widgetResizable
QScrollArea to a short child's real size, so `refresh_list()` now
also calls `setFixedHeight(min(content_height, 300))` after rebuilding
the list, computed from the real card count each time. The G-Keys
strip under the canvas got a thin `HLine` separator above it and its
label changed from "G-Keys" to "Add New Macro" so it reads as its own
section instead of part of the keyboard image above it. Real build
against the live `g910-v1.11` URL, `namcap` clean (same two known
false positives), extracted-package personal-data audit clean,
headless launch of the actual built package with no keyboard
simulated. Hash copied via `sed` straight from a `sha256sum` variable
this time, not retyped by eye, after the v1.10 transcription slip.

**v1.12** (preset palette fix, compact colour picker row, shorter
profile cards): three more items from live use right after v1.11.
Gold and Sky Blue sat too close in hue to Yellow and Cyan to
distinguish in a small swatch -- replaced with Brown and Silver
(genuinely different value/saturation, not just another mid-brightness
hue), and the grid is 5 columns instead of 3. The old layout had a
separate full-width preview box above a separate "Hex code" row --
now there's one compact row: a small swatch (updates live as you type
or use the picker, no hardware call until Apply), the hex field, and
Apply. A new "Colour Picker" button opens Qt's native `QColorDialog`
and fills the hex field only -- confirmed it doesn't call `_apply_color`
itself, Apply/Enter still does. Saved profile cards went from 61px to
30px (measured via `sizeHint()` before/after, not eyeballed) by
tightening margins/spacing to zero, fixing Load/Delete at 16px tall,
and dropping the name label to a 10px font -- wordWrap left on so an
unusually long profile name still wraps instead of getting clipped.
Real build against the live `g910-v1.12` URL, `namcap` clean (same two
known false positives), extracted-package personal-data audit clean,
headless launch of the actual built package, hex-apply path
(`on_apply_hex` -> `_apply_color`) tested live against real hardware.

**v1.13** (fix oversized profile card + clipped button text, rename
Random Colours to WIP): two real bugs found from a live screenshot
right after v1.12 shipped. `ProfilesTab.refresh_list()` had no trailing
`addStretch()` in `list_layout` -- with a Preferred size policy and
nothing else claiming leftover vertical space, Qt let the single/last
card grow to fill whatever height the scroll viewport ended up with
(confirmed via a full `MainWindow` + `processEvents()` repro, not just
an isolated widget: card measured 86px actual vs. its own 30px
sizeHint before the fix, 42px actual == 42px sizeHint after). Separately,
the Load/Delete buttons' `setFixedHeight(16)` from v1.12 was smaller
than this font's own 24px line height (`fontMetrics().height()`,
checked directly rather than guessed again after the v1.10/v1.11 hash
mistakes) -- clipped text, confirmed by the same screenshot. Replaced
with reduced padding so Qt computes a safe height from real font
metrics instead of another guessed constant. Random Colours renamed to
"Random Colours (WIP)" per direct feedback: it's a hue-sweep gradient
with a randomized starting phase, not independent per-key randomness,
so keys in the same row on Main Board still read as an ordered band --
the name shouldn't promise more than the algorithm delivers. Real
build against the live `g910-v1.13` URL, `namcap` clean (same two
known false positives), extracted-package personal-data audit clean,
headless launch of the actual built package.

**v1.14** (fix the REAL root cause of profile card breakage, after two
failed attempts): v1.12 and v1.13 both tried to shrink/stabilize
`ProfilesTab`'s card height by recomputing `profiles_scroll`'s fixed
height from `list_container.sizeHint()` on every `refresh_list()` call
-- self-referential, since that computation ran on top of whatever the
PREVIOUS refresh had already set. Confirmed via a real screenshot that
adding a SECOND profile compounded this into garbled, overlapping,
near-unreadable cards -- worse than the original "too tall" complaint
this was meant to fix. Fully reverted: cards are back to plain default
sizing (normal font, normal `ZoneButton` padding, no custom shrinking),
`profiles_scroll` uses one static `setMaximumHeight(160)`, no
per-refresh recomputation at all. The actual root cause of BOTH the
original inflation bug (v1.12) and this new corruption (v1.13): Card
widgets had no explicit vertical size policy, so Qt's default
`Preferred` let them grow OR shrink away from their own `sizeHint()`
whenever the layout had slack either direction. Every card now gets
`QSizePolicy.Fixed` vertically -- confirmed via a 0/1/2/3/5/back-to-2
profile stress test (not just a single-profile check like the previous
two releases) against both the source and the actual built package,
plus the 3 real profiles on this machine, all rendering at their
correct natural height (64px) with zero compression or inflation.
Real build against the live `g910-v1.14` URL, `namcap` clean (same two
known false positives), extracted-package personal-data audit clean.

**v1.15** (safely re-apply the profile card height reduction): v1.14
fixed real card corruption by fully reverting a height reduction back
to the original ~64px size -- but that corruption's actual root cause
was the missing `QSizePolicy.Fixed` (shipped in v1.14 itself), not the
smaller padding/font choices from the reverted attempt. With that
policy now correctly pinning every card, the same compact sizing is
safe to reapply: tighter margins/spacing, a 10px name label font, and
`ZoneButton` padding reduced to "1px 8px" (checked against this font's
real `fontMetrics().height()` of 24px before use -- sizeHint comes out
to 28px, so text can't clip the way the earlier guessed
`setFixedHeight(16)` did in v1.12). Cards now measure 42px, down from
61-64px. Re-verified with the same 0/1/2/3-profile stress test as
v1.14, plus a real multi-word name ("profile i like") to confirm
wordWrap still has room if it's ever needed -- every card's rendered
height matched its own sizeHint exactly at every count, on both the
source and the actual built package. Real build against the live
`g910-v1.15` URL, `namcap` clean (same two known false positives),
extracted-package personal-data audit clean.

## Before real AUR submission (not done yet, needs the user's go-ahead)

- Generate `.SRCINFO` (`makepkg --printsrcinfo > .SRCINFO`).
- Push to a dedicated `aur.archlinux.org` git remote for this package.
- Everything else (public source, real sha256sum, clean built-package
  audit) is done.
