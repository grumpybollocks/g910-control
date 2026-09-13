# G910 Canvas Rearchitecture — Plan (no code written yet)

Branch: `g910-canvas-rearchitect`, forked from `g910-macros` at the
point tagged `g910-skeleton-v1-buttongrid` — that tag is the permanent,
untouched record of the working button-grid skeleton (clickable
keyboard + Color Mode sidebar, all 6 targets confirmed working). This
branch is where the keyboard-rendering rearchitecture happens; nothing
here should be assumed "done" until re-confirmed on real hardware,
same as everything else in this project.

## Why this rearchitecture, not just more patches

Researched two independent, real, established per-key RGB keyboard
apps before deciding anything:

- **Solaar** (GTK/Cairo) — `ui/perkey/canvas.py`. Renders the keyboard
  on a `Gtk.DrawingArea` via Cairo, using real per-key geometry
  (`Cell(row, col, width, height)`), does pixel rect hit-testing
  (`_cell_at`), and handles click/drag/multi-select through a
  pluggable "tool" system (single/rect/line/gradient/brush).
- **OpenRGB** (Qt/C++, directly comparable since it's the same GUI
  framework family as our PyQt5 app) — `qt/DeviceView.cpp`. Renders
  via `QPainter` in a custom `paintEvent`, stores normalized grid
  positions scaled to pixels, and handles drag-select with a
  `selection_rect` intersected against every LED's real rect (Ctrl+drag
  XORs the selection).

Both independently converge on the same architecture: **a
custom-painted canvas with real per-key geometry and rect-based
hit-testing**, not a layout manager full of buttons. That's the
opposite of what our current skeleton does (`QGridLayout` +
`QPushButton` + hand-approximated integer colspans) — and it's
directly why we kept hitting real layout-collision bugs (M1/M2
spacing, MR/G6 overlap, nav cluster vs Backspace): colspan grids don't
carry real geometry, so overlaps have to be caught by hand instead of
being structurally impossible.

## What's actually solid to reuse vs. what still needs our own work

**Reusable, verified**: Solaar's ported `MAIN_ANSI`/`FN_ROW`/`EXTRAS`/
`NUMPAD` cell data (`ui/perkey/layouts/_keyboard_base.py`, itself
ported from OpenRGB's `KeyboardLayoutManager.cpp`, GPL-2.0-or-later)
gives correct **relative row/col placement and the real gaps** between
key groups (e.g. the actual gap between Esc and F1, between F4/F5,
F8/F9, before the nav cluster) — this is a real reference, not a
guess, and better than what we hand-approximated.

**NOT solved by that data, checked directly rather than assumed**:
precise widths for most "wide" keys. Grepped the actual source for
`width=` overrides — only `Space` (7.0 units) and the numpad `0` key
(2.0 units) have one. Backspace, Tab, Caps Lock, Enter, both Shifts,
Ctrl/Alt/Win all default to `width=1.0` in that data, same as every
normal key. So for those, we still need to supply real-world standard
ANSI proportions ourselves (well-known physical measurements — not
something requiring hardware-specific testing, since it's about
standard keycap sizes, not this specific device): Backspace ≈2u,
Tab ≈1.5u, Caps ≈1.75u, Enter ≈2.25u, LShift ≈2.25u, RShift ≈2.75u,
Ctrl/Alt/Win ≈1.25u each.

**Not covered by Solaar's data at all**: G-keys, M-keys, and the Logo
key(s). Solaar's G-key zone data is for a *different* Logitech
keyboard model's HID++ protocol (PER_KEY_LIGHTING_V2, feature 0x8081)
— confirmed back in the original research pass that our G910 doesn't
even have that feature. We already have our own correct G-key/M-key
positions from the current skeleton (matches the reference screenshot
you sent: G1-G5 left column, G6-G9 top row above F1-F4, M1-M4 top
row) — that geometry carries over as-is, just re-expressed in the new
Cell format instead of grid row/col/colspan.

**One real gap noticed while planning this**: the current skeleton has
**no visual Logo key on the keyboard drawing at all** — "Logo" is only
reachable via the sidebar's bulk button, never drawn on the board
itself. This rearchitecture is the natural point to fix that, but I
don't know where you want it drawn (your reference screenshot shows it
between the M-keys and the G1 column) — see open questions below.

**Unaffected by any of this**: `g910_backlight.py` (the whole backend)
and the Color Mode sidebar's logic — this is a rendering-layer change
only. Real key names, block naming (`x01`-`x09` for gkeys/logo),
`GROUPS`, and every confirmed hardware fact stay exactly as they are.

## Proposed architecture

- **New geometry model**: our own small `Cell` structure —
  `(key_name, row, col, width, height, block)` — `key_name` is the
  REAL `keyledsctl` name (`"ESC"`, `"BACKSPACE"`, `"G1"`, ...), not a
  display label; `block` is `"keys"`/`"gkeys"`/`"logo"`/`None`
  (inert, matching the current skeleton's treatment of RCTRL/RALT/etc
  which have no individual LED).
- **Data source**: port Solaar's `_keyboard_base.py` row/col/gap
  values by hand into our own file (copy the numeric constants, credit
  the source and license in a comment — we do NOT import Solaar's
  actual package at runtime; that would be a fragile dependency on an
  unrelated installed app). Translate their `label` strings to our
  real `keyledsctl` key names carefully (e.g. their `"Bksp"` → our
  `"BACKSPACE"`) — this translation needs to be double-checked key by
  key against our own confirmed 105-name list, not assumed 1:1.
  Supply our own width overrides for the wide keys listed above.
  Author G-key/M-key/Logo cells ourselves, matching the reference
  screenshot.
- **Rendering**: a `QWidget` subclass with a `paintEvent(self, event)`
  override, using `QPainter` — following OpenRGB's proven pattern
  directly (same framework, most comparable reference). Each cell
  drawn as a rounded rect, filled with its color, label centered with
  luminance-based contrast text color (the same
  `0.299R + 0.587G + 0.114B` formula both Solaar and OpenRGB use).
- **Hit-testing**: convert each `Cell`'s `(row, col, width, height)`
  to a pixel `QRectF` via a fixed cell-size + gutter scale (same
  pattern as Solaar's `canvas.py`), test clicks with
  `QRectF.contains(point)`.
- **Backend integration**: unchanged for single clicks — still calls
  the exact same `g910_backlight.set_key_color`/`set_group_color`
  functions already proven working. For DRAG-PAINT specifically, see
  the buffer/commit finding below: single-click keeps calling the
  existing per-key function (already efficient enough for one key at a
  time), but drag-paint gets its own batched path.
- **Color Mode sidebar**: unchanged, sits next to the new canvas
  widget exactly like it sits next to the button grid today.

## Real protocol finding that changes the drag-paint design

Read `libkeyleds/src/feature_leds.c` (the real compiled source, same
tarball used in the earlier audit) directly rather than assume how
color-setting works. The HID++ `LEDS` feature is a **buffered
write + explicit commit** model:
`keyleds_set_leds()`'s own doc comment: *"Updates an internal buffer
on the device. Actual lights are not updated until
keyleds_commit_leds() is called."* Every test this session looked
instant because `keyledsctl set-leds` (`keyledsctl_set_leds.c` line
189) calls `keyleds_commit_leds()` exactly ONCE, after processing every
directive given to that single process invocation.

**Consequence for drag-paint**: if the canvas shelled out to
`keyledsctl` once per key while the mouse drags across many keys, each
call would pay the full cost of opening the HID++ device and
re-discovering its features every single time — slow, and wasteful
given the protocol is explicitly designed for batching. The correct
design: accumulate the keys touched during a drag stroke in memory,
and send them as ONE batched `set-leds` call on mouse release (or
periodically during a very long drag, not per-key). `g910_backlight`'s
`_run_set_leds` already accepts a list of directives and sends them in
one call — this is a natural extension of the existing plumbing, not a
rewrite. Single clicks stay exactly as they are now (one key, one
call) since there's no batching benefit at that scale.

## Decisions (resolved)

1. **Logo key placement**: between the M-keys row and the G1 column,
   matching the reference screenshot / real board.
2. **Interaction scope**: drag/multi-select IS in scope for this pass,
   not deferred. Adapt OpenRGB's actual proven selection-rect/Ctrl-XOR
   code (`qt/DeviceView.cpp`) rather than design one from scratch —
   efficient reuse, not a shortcut, since it's a real working reference
   in the same framework.
3. **Live color display / reboot persistence**: the user's own prior
   experience is that Solaar's on-device settings survived reboots for
   them before, and has decided to proceed on that basis rather than
   spend more time verifying it for this specific keyboard/feature
   right now. Worth being precise about what that evidence actually
   covers: Solaar's own per-key lighting targets a DIFFERENT HID++
   feature (`PER_KEY_LIGHTING_V2`, 0x8081) than what this G910 actually
   has (`leds`/`led-effects`, confirmed back in the original research
   pass) — so "Solaar persisted across reboot" was very likely observed
   on different hardware or a different feature than the one this
   project uses. Not re-litigating this now per the user's explicit
   instruction to move on, but noting the distinction honestly rather
   than treating it as directly-proven for our exact case. If colors
   turn out NOT to survive a real reboot once this is testable in
   practice, the fix is a login-time reapply script + systemd service,
   same shape as (but not copied from, since G510s's mechanism was for
   a different, simpler LED-class-sysfs backlight, not this HID++
   per-key system) — deferred, not designed now, since it isn't blocking
   this rendering-layer rearchitecture either way.

Nothing gets implemented until these are answered.

## Planned (not yet built): Profiles tab

Added to the plan 2026-09-14, per the user's request -- a third tab
alongside Backlight and G-Keys.

What it does: capture the CURRENT full lighting state (every key's
color across every LED block -- keys/gkeys/logo, queried live via
`keyledsctl get-leds` for each block) and save it as a named profile.
Load a saved profile back later to instantly reapply that whole
combination.

Rough shape, not fully designed yet:
- "Save Current as Profile" button, prompts for a name, snapshots
  `get-leds -b keys` + `-b gkeys` + `-b logo` output (already have the
  parsing logic for this in `g910_backlight._all_key_names`/
  `get_key_color` -- reusable, not a new mechanism), stores it as a
  named entry in a new file (`g910_profiles.json`, matching the
  `g910_macros.json` naming convention already established).
- A list of saved profiles (buttons or a dropdown), each with Load and
  Delete.
- Loading a profile replays it via `_run_set_leds`, block by block --
  already-proven plumbing, no new hardware-facing code needed, this is
  purely a save/list/load UI wrapping existing functions.
- Open question, not yet decided: should Main Board's excluded inert
  keys (Win/Alt/AltGr/Menu/right-Ctrl/right-Shift -- see the M-KEY/
  inert-key work earlier) matter here at all? They can't be saved/
  restored either way since they were never colorable, so this is
  purely about whether the UI should show them as part of a "full
  snapshot" cosmetically. Low priority, decide when actually building
  this.
- Does NOT need to touch feature 0x8070 (the hardware effects engine)
  at all -- this is about the existing static-color "leds" feature
  only, a snapshot of what's already controllable today.

## Macro daemon (g910_macro_daemon.py) -- root cause found, verified,
not yet run against real hardware

User reported multiple things that looked like separate bugs
("recorded macros don't record," "the M doesn't change when I press
the physical button"). Diagnosed via a live file-watcher (objective
timestamped diff of every write to g910_macros.json, not guesswork) --
recording and saving were actually working correctly the whole time.
The real, single root cause for both symptoms: **there was no
component at all listening for physical G-key/M-key/MR presses.**
Software-to-hardware (clicking M1 in the app lights the real LED)
worked because it was built explicitly; hardware-to-software
(physical presses affecting anything) never existed. Same gap as the
sibling G510s project's split between `g510_app.py` (records) and the
separate `g510_macro_daemon.py` service (plays back) -- G910 only had
the first half built.

Wrote `src/g910_macro_daemon.py`, structurally mirroring the G510s
daemon (same macro file shape, same `ydotool key <code:value>...`
replay mechanism, same "M-keys switch the live profile + write a
status file the GUI polls" pattern) but necessarily different at the
input layer: G510s reads plain evdev keycodes directly (its G-keys are
real Linux keycodes via `hid_lg_g15`); G910 has none -- decodes raw
HID++ reports on `/dev/hidraw1` instead, using the exact protocol
already reverse-engineered and documented in `G910_README.txt`.

**Verified before running anything, not assumed:**
- `decode_report()` unit-tested against the EXACT real byte sequences
  captured from this hardware earlier this session (not re-derived
  from memory) -- all 10 cases (G1/G2/G8/G9 press+release, M1/M2/M3,
  MR press+release) pass exactly.
- Checked whether `ydotool` (the replay mechanism, copied from the
  G510s daemon) is actually installed on this machine before trusting
  it -- it was NOT. Real gap caught before running, not after.
  Confirmed via `pacman -Si`/`pacman -Fl`: `extra/ydotool` (official
  repo, not AUR), provides both the `ydotool` client and `ydotoold`
  daemon binaries, ships its own systemd --user service unit
  (`ydotool.service`) and udev rule for uinput permissions already --
  nothing to hand-write there.

**NOT yet done, explicitly**:
- `ydotool` is not installed. `install-g910.sh` (on the `g910` branch)
  does not list it as a dependency yet -- needs updating there.
- `ydotoold` needs enabling (`systemctl --user enable --now
  ydotool.service`) before `ydotool key` calls will actually do
  anything.
- The daemon itself has NEVER been run against the real keyboard.
  Everything above is code-level verification (unit test against known
  bytes, dependency-availability check) -- not yet a live end-to-end
  test with real G-key presses driving real macro replay.
- No systemd --user service file written for the daemon itself yet
  (mirroring the G510s's `g510-macro-daemon.service`) -- currently
  would only run manually (`python3 g910_macro_daemon.py`), doesn't
  survive logout/reboot.
- MR's actual behavior beyond "toggle its own LED" is undefined --
  flagged honestly in the daemon's own docstring as a real open design
  question, not guessed at.
- Worth flagging plainly before this gets run live: `ydotool` can type
  arbitrary keystrokes and the "command" macro type runs arbitrary
  shell commands system-wide. A bug here has more real-world reach
  than anything touched so far in this project (which was all
  scoped to the keyboard's own LEDs). Get explicit go-ahead before
  installing `ydotool` and running this daemon against the live
  keyboard, not just before writing the code.
