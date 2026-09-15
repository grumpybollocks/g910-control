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
  which have no individual LED). **Superseded 2026-09-14, see "Main
  Board block-fill correction" below** -- these keys DO respond to
  block-wide fills, just not individual addressing; they now use
  `block="keys", individually_colorable=False` instead of `block=None`.
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
- **Resolved 2026-09-14, see "Saved profiles never captured the six
  inert keys" below**: they ARE colorable (via block-fill, not
  individual addressing), so this did end up mattering. `load_profile`
  now infers their color from the snapshot's own Main Board dominant
  color and fills block "keys" with it before replaying exact per-key
  values, so a loaded profile matches on all six keys too.
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

### Daemon: CONFIRMED WORKING end-to-end on real hardware (2026-09-14)

User installed `ydotool` + enabled its service, then live-tested
against the real keyboard, in a safe isolated scratch window (a
Konsole running `cat`, so replayed macros couldn't land in an
unintended context).

First live run immediately surfaced a real bug: physical M-key LEDs
"went crazy," all three appearing to blink. Root-caused via a
purpose-built read-only diagnostic (logs every raw report, zero
hardware writes) rather than guessed at -- a single real G5 press was
followed by clean press/release pairs repeating every 100-400ms for
2.5+ seconds straight, confirmed via actual hidraw timestamps. That's
the keyboard firmware's own key-repeat behavior (same thing that makes
a held letter key auto-type), which the daemon had zero protection
against -- it replayed the macro on every single repeat. Fixed with a
per-key cooldown (`COOLDOWN_SECONDS`) plus moving macro replay onto
its own thread so a slow replay could never block the read loop and
delay/miss a genuine M-key press arriving during that window (a real,
separate contributing issue, not just the repeat flood).

Re-tested after the fix: G5 macro replay confirmed clean (typed "test"
correctly, no flooding, tested twice). M1/M2/M3 profile switching
confirmed reliable. Both confirmed directly by the user on the real
keyboard, not assumed from the code fix alone.

Still not done: MR's behavior beyond its own LED toggle still
undefined (deliberate scope, not a bug -- see below), and the
Profiles tab (see above) is still only planned, not built.

### Daemon: systemd --user service installed + rigorous audit pass (2026-09-14)

Merged `g910` branch's newer commits into `g910-canvas` first (both
had diverged -- `install-g910.sh`/`G910_README.md` only existed on
`g910`, the daemon only existed here -- clean merge, no conflicts).

Added `services/g910-macro-daemon.service` (mirrors the sibling
G510s's `g510-macro-daemon.service` exactly: `Requires=ydotool.service`,
`Restart=on-failure`, `WantedBy=default.target`), installed via
`~/.config/systemd/user/`, `daemon-reload`, `enable --now`. Confirmed
running clean (no errors in `journalctl`), and confirmed G5 replay
works identically through the systemd-managed instance as it did
running manually. `install-g910.sh` updated to do this automatically
for a fresh install, not just done by hand.

Per the user's explicit "make this bulletproof, verify yourself"
request, re-read the whole daemon file looking for silent-failure
paths rather than assuming the working test above was sufficient.
Found real gaps: `subprocess.run()`'s return code for the startup
`keyledsctl gkeys on` call was never checked; `bl.set_mkey_led()` and
`bl.set_mrkey_led()`'s `(ok, err)` return values were discarded at
every call site (startup and in the main loop); `replay()`'s
`subprocess.run()` result was also unchecked. All fixed to log a
clear `WARNING:`/`FAILED:` message to stderr (captured automatically
by `journalctl` since this runs as a systemd unit) instead of failing
silently.

Also directly confirmed MR had never been tested at all this session,
despite the whole G-key/M-key flow being tested repeatedly -- watched
the daemon's live log while the user pressed it for real. Confirmed
working exactly to its current, deliberately limited scope: the
physical LED toggles correctly (`set_mrkey_led` succeeds, no
warning logged). It does NOT arm/disarm any recording behavior --
that was never built, and the daemon's own docstring already says so
explicitly ("not yet designed"). User's "never recorded macro"
observation matches this exactly -- confirmed expected, not a bug.

### Main Board block-fill correction + GUI catch-up (2026-09-14)

Earlier documentation (this file, `G910_README.md`) repeatedly and
confidently asserted that Win/Alt/AltGr/Menu/right-Ctrl/right-Shift
have NO way to be colored at all. That was wrong, and the user caught
it by testing directly: these six keys were visibly purple in a
screenshot, contradicting the claim. Verified live rather than
defending the prior assertion: `keyledsctl set-leds -b keys all=00ff00`
turned them green along with the rest of the board (user-confirmed).
Real mechanism, read from `keyledsctl_set_leds.c`'s actual source:
`all=` uses `keyleds_set_led_block` (a whole-block fill), a different
HID++ call than the per-key `keyleds_set_leds` used for named keys.
So the accurate statement is: these six keys have no INDIVIDUAL LED
(still true, confirmed many times over -- they never appear in
`get-leds`'s per-key listing, and addressing them by name is
rejected), but they DO respond to the block-wide fill. This is the
only mechanism that reaches them at all.

Propagated the correction through the whole stack:

- `g910_backlight.py`: `set_main_board_color()` rewritten to
  snapshot-fill-restore -- read F1-F12/Numpad/Nav Cluster's current
  colors first, do the `all=` fill (which now also reaches the six
  keys), then restore just those three dedicated-button groups back
  to what they were. Tested via CLI (F1 unchanged, A changed) and
  confirmed live by the user ("yes they turned orange, main board
  keeps them intact").
- `g910_canvas.py`: `Cell` gained `individually_colorable: bool`
  (True by default, False for the six keys) so the canvas can
  distinguish "can't be clicked individually" from "can't be colored
  at all" -- they kept `block="keys"` instead of `block=None`, and
  drag-selection now skips them via `individually_colorable` instead
  of the old `block is None` check.
- `g910_app.py`: `ColorModeSidebar.on_apply()`'s canvas preview call
  switched from `ZONE_KEYS` (strictly individually-addressable) to
  `ZONE_SELECTION_KEYS` (includes the six keys) so a Main Board apply
  visually updates them in the GUI too, matching the real keyboard.

### Startup live-sync + profile-load sync + inert-key preview (2026-09-14)

User request: "can you make the app always when opened to reflect the
current key colouring setup?" Added `get_all_live_colors()` to
`g910_backlight.py` -- queries every block in `PROFILE_BLOCKS`,
translates device names back to friendly canvas names (reverse of
`GKEY_NAMES`/`LOGO_NAMES`) -- and `KeyboardCanvas.sync_from_device()`
in `g910_canvas.py`, called once from `__init__`. Verified directly
(not just "should work"): ran `get_all_live_colors()` standalone
against the real device, got back 115 real key colors matching what
was actually set.

First visual test (screenshot) immediately surfaced the obvious gap:
the six individually-unaddressable keys showed as inert grey in the
preview even though they were physically orange -- expected, since
`get_all_live_colors()` can only report what the device reports, and
the device never reports these six at all (same root cause as the
block-fill discovery above). Fixed with an approximation, not a
guess about hardware: since the ONLY way these keys get colored is
the Main Board's `all=` fill, their live color on sync is inferred as
the most common (mode) color among the rest of the individually-
addressable Main Board keys -- exactly correct after any solid fill,
which is the only way they're colored today. Implemented as a
`Counter` over `ALL_CELLS` filtered to `block == "keys" and
individually_colorable`, applied to the ones that aren't. Confirmed
correct live by the user.

Two more real gaps found and fixed in the same session, both caught
by the user actually using the feature rather than assumed fixed
after the first confirmation:

1. **Profile Load didn't refresh the canvas.** `sync_from_device()`
   only ran once, at `KeyboardCanvas.__init__` -- loading a profile
   changed the device but nothing told the canvas to re-query. Fixed
   by giving `ProfilesTab` a reference to the Backlight tab's canvas
   (`BacklightTab` now stores `self.canvas`; `MainWindow` passes
   `backlight_tab.canvas` into `ProfilesTab(canvas)`), and calling
   `self.canvas.sync_from_device()` after a successful `on_load`.
   Confirmed live: canvas now updates immediately after clicking Load.

2. **Saved profiles never captured the six inert keys' color at all.**
   `save_profile()` snapshots via `_get_block_colors()`, which -- same
   root cause again -- never sees these six keys, so they were simply
   absent from every saved profile. On load, they'd silently keep
   whatever color was already on the device instead of matching the
   loaded profile. Fixed in `load_profile()`: before replaying the
   snapshot's exact per-key directives, first fill block "keys" with
   the dominant (mode) color among the snapshot's OWN Main Board keys
   (factored into a shared `_excluded_from_main_board()` helper, also
   used by `set_main_board_color`) -- this is, by definition, what the
   whole board was bulk-filled to when the profile was saved, so it's
   the correct color for the six keys too, not a guess. The per-key
   directives applied immediately after override the fill for every
   individually-addressable key back to its exact saved value, so
   nothing else is approximated. Confirmed live by the user after
   loading a real saved profile ("1"): the six keys matched the
   profile's Main Board color both on the physical keyboard and in
   the GUI preview.

Also did a small GUI polish pass per user request: "Pick Color &
Apply" (Backlight tab) and "Save Current as Profile..." (Profiles
tab) now use a distinct blue accent style (`QPushButton#Primary`) to
stand out as the primary action in each tab, instead of looking
identical to every other button.

All of the above verified against the real device before being
called done -- compiled (`py_compile`), smoke-tested (every tab
class instantiated headless via `QT_QPA_PLATFORM=offscreen`), then
launched for real and confirmed visually by the user at each step,
per the "no more mistakes, verify yourself" standing rule.

### Reboot-safety audit (2026-09-14)

User asked directly: are we reboot-safe, are dependencies covered by
an installer, are we done on this step? Verified each claim rather
than assuming the earlier install work was sufficient:

- **Dependencies**: `install-g910.sh` covers everything -- official
  repo packages (PyQt5, python-evdev, ydotool, keyleds's AUR build
  deps), the `keyleds` AUR package itself, `ydotool.service` enabled,
  `g910-macro-daemon.service` installed+enabled. Confirmed live:
  both services show `enabled`+`active` via `systemctl --user
  is-enabled`/`is-active`.
- **Hidraw permissions**: confirmed non-root access survives reboot
  without any custom udev rule of our own -- the `keyleds` package
  ships `/usr/lib/udev/rules.d/70-logitech-hidpp.rules`, which tags
  the right interface with `uaccess` based on `idVendor`+
  `bInterfaceProtocol` (not a hardcoded path). Confirmed via
  `udevadm info`: `TAGS=:uaccess:seat:` on the live device.
- **Real bug found and fixed**: `g910_backlight.py`'s `DEVICE` and
  `g910_macro_daemon.py`'s `DEVICE_PATH` were hardcoded to
  `/dev/hidraw1`. hidraw numbering is just enumeration order across
  EVERY hidraw device on the system -- confirmed via `udevadm info`
  on all 12 hidraw nodes present on this machine (2 mice, a headset,
  this keyboard's own second interface all show up as hidrawN) -- not
  guaranteed stable across reboots/replugs, same class of bug the
  sibling G510s project already hit once with `/dev/hidrawN` before
  switching to a stable symlink. Fixed the same way: confirmed a
  stable `/dev/input/by-id/usb-..._G910_..._-if01-hidraw` symlink
  already exists (auto-created by udev's own built-in rules, zero
  custom rule needed -- same mechanism `g910_app.py`'s
  `MAIN_KEYBOARD_DEVICE` already relied on), pointed both constants at
  it instead. Verified live: `get_all_live_colors()` still reads all
  115 keys through the new path, daemon restarted clean and still
  responded to a real G-key/M-key press (both confirmed by the user).

Conclusion: yes, reboot-safe now (this bug meant it previously was
NOT, in the specific case where hidraw enumeration order shifted), and
yes, `install-g910.sh` alone is sufficient for a fresh install -- no
manual steps left outside it.

### GUI overhaul: single unified view -- reached "v1" (2026-09-14)

After the reboot-safety pass, the user wanted to actually redesign the
GUI (previously 3 tabs: Backlight/G-Keys/Profiles) rather than keep
adding features. Iterated live against the real running app,
confirming each change visually before moving to the next -- nothing
below was assumed to look right without the user actually seeing it.
End state: **one single view, no tabs at all.**

**Merged G-Keys and Profiles out of their own tabs, into the space
around the canvas:**
- `GKeysTab` (M1/M2/M3 + G1-G9 macro buttons) moved from its own tab
  into a compact horizontal strip directly under the keyboard canvas
  -- rewritten from a `QVBoxLayout` (title + description + profile row
  + 3x3 grid) into a single `QHBoxLayout` row, since the space under
  the canvas is only ~100px tall (canvas is 962x324, window was
  460 tall) -- nowhere near enough for the old vertical layout.
- `ProfilesTab` moved from its own tab into the empty space that was
  left on the right of the window after G-Keys moved out from there.
- `MainWindow` dropped `QTabWidget` entirely -- `BacklightTab` (now
  containing the canvas + sidebar + G-Keys strip + Profiles panel) is
  the sole central widget.
- Each panel (`ColorModeSidebar`, `GKeysTab`, `ProfilesTab`) got
  `objectName("Panel")` + a shared `QWidget#Panel` QSS rule (subtle
  card background/border), separated by 1px `QFrame` vertical
  dividers (`_vseparator()`), so the single view still reads as
  distinct sections instead of one undifferentiated block.

**Canvas got two new interactive features (both were explicit,
separate feature requests, not just visual polish):**
1. **M1/M2/M3/MR are now real, clickable cells on the canvas**, not
   inert grey placeholders. `Cell` entries for them changed from
   `block=None`-only to also carrying a real `key_name` (`_M1`.._MR`,
   NOT a keyledsctl name -- these still have zero LED color mechanism,
   confirmed empirically same as before) purely so the canvas can
   identify them for click handling. New `KeyboardCanvas` signals
   `mkey_clicked`/`zone_clicked`; clicking M1/M2/M3 calls
   `GKeysTab.select_profile()` (same path as clicking its own
   buttons, and physical M-key presses via the daemon's poll file --
   one method, three input sources, always in sync), clicking MR
   toggles `bl.set_mrkey_led()` same as the physical key. Active
   profile/MR-on state highlighted directly on the canvas
   (`ACTIVE_MKEY_COLOR`/`MR_ACTIVE_COLOR`) instead of only in the
   G-Keys strip.
2. **Clicking any key/cluster on the canvas auto-selects the matching
   zone in the sidebar's list** (`zone_clicked` signal + new
   `KEY_TO_ZONE` reverse map built from `ZONE_SELECTION_KEYS`). Had to
   add a separate `ColorModeSidebar.sync_target()` instead of reusing
   `select_target()` -- the existing method also calls
   `canvas.select_keys()`, which would stomp the canvas's own
   single-key selection (from the very click that triggered this) and
   turn a plain single-key click into "recolor the whole zone" by
   accident. `sync_target()` only updates the sidebar's own checked
   state, nothing on the canvas.

**Layout/sizing polish, several rounds of real user feedback each
verified live before moving on:**
- Sidebar zone buttons (`QPushButton#ZoneButton`): were left-aligned
  in a fixed-width column, looked like long empty bars -- centered
  text + tighter padding. Reused the same objectName for the G-Keys
  strip's M/G buttons too (they had the identical "long empty
  button" problem from the same root cause: global `QPushButton` QSS
  is `text-align: left`).
- M-key cells went through two size passes: first "half size" (0.45 x
  0.5) was too small for even a 2-char label at the normal 9pt font
  -- fixed with both a bigger cell (0.55 x 0.65) AND a dedicated
  smaller font (`MKEY_FONT_PT = 6`) just for these four labels.
  G6-G9 pushed right +0.6 columns to clear space from the M-keys
  cluster to their left (no longer perfectly above F1-F4 as the
  original comment described -- traded for the requested spacing).
- Logo cell bumped ~15% bigger (1.05 x 1.15, was 0.9 x 1.0) -- pure
  design choice, not a hardware constraint.
- Real bug: the window was hardcoded to `resize(1500, 460)` from
  earlier in the project. After all the panel changes the actual
  content needed less width, leaving a real empty gap on the right of
  the window. Fixed by dropping the hardcoded resize and calling
  `self.adjustSize()` instead, so the window always matches real
  content -- avoids this exact bug recurring the next time a panel's
  width changes.
- `KeyboardCanvas.main_board_pixel_span()` added so the G-Keys strip
  centers under the actual keyboard block (M-keys/Logo/G-keys/main
  board) specifically, not the whole canvas widget -- the canvas is
  wider than that because Nav Cluster + Numpad extend further right
  with a visual gap, so plain center-under-the-whole-canvas looked
  off-center relative to the keyboard itself.

**Desktop launcher added**: `install-g910.sh` now generates
`~/Desktop/G910 Control.desktop` itself, from the install script's own
resolved `$DIR` -- deliberately NOT hardcoding a path, unlike the
sibling G510s project's `.desktop` files (found during the reboot-
safety audit to be hardcoded to one specific machine/username and
silently broken everywhere else). Verified live: the exact `Exec=`
command from the generated file launches the app cleanly with no
errors.

All of the above compiled clean (`py_compile`) and smoke-tested
(`QT_QPA_PLATFORM=offscreen`, every panel instantiated headless) before
each real launch; every visual claim in this section was confirmed by
the user actually looking at the running app, not assumed from the
code.

### Final bug check (2026-09-14)

Full pass over all four G910 Python files (`g910_app.py`,
`g910_backlight.py`, `g910_canvas.py`, `g910_macro_daemon.py`) before
calling this app done for now:

- `py_compile` + `ast.parse` clean on all four.
- Grepped for bare/broad `except:` blocks, TODO/FIXME/HACK markers,
  and every `subprocess.run()` call site -- checked each one by hand.
  All four `except Exception:` blocks are the same deliberate pattern
  (malformed/missing JSON profile or macro file -> fall back to empty
  defaults instead of crashing), and every `subprocess.run()` call
  checks `returncode` and surfaces the error -- no silent failures
  found.
- Manually traced the trickier logic for a second time looking for
  edge cases: `_FUNCTION_ROW_KEYS`'s `"F" + isdigit()` filter against
  the standalone `"F"` key (ASDF row) -- `"F"[1:]` is `""`, and
  `"".isdigit()` is `False`, so it's correctly excluded, not a bug.
  `on_mkey_clicked`'s MR-toggle failure path correctly reverts
  `self._mr_active` and returns without touching the canvas, so a
  failed hardware write never desyncs the displayed state from reality.
- **Real finding, not just a stale comment**: the class `BacklightTab`
  had drifted badly out of sync with what it actually does -- it
  started as literally the Backlight tab, then quietly became the
  entire app (sidebar + canvas + G-Keys strip + Profiles panel) as
  G-Keys and Profiles got merged in over the session, but the name and
  every docstring/comment referencing it still said "Backlight tab."
  Renamed to `MainView` throughout `g910_app.py` (class definition,
  `GKeysTab`'s docstring, `ProfilesTab`'s docstring, `MainWindow`'s
  instantiation, section comments), and fixed the module's own
  top-of-file docstring, which still claimed the app was "now tabbed"
  -- it hasn't had a single tab since G-Keys and Profiles moved in.
  Not a functional bug (nothing broke), but exactly the kind of stale
  documentation that causes a real bug later when someone trusts it.
- Verified live against the real hardware (this machine has the G910
  attached): `get_all_live_colors()` still reads all 115 keys,
  `set_mkey_led()`/`set_mrkey_led()` round-tripped cleanly (M2 then
  back to M1, MR on then off), the macro daemon has been running 9+
  hours with zero warnings in `journalctl`, the desktop launcher's
  exact `Exec=` command still launches cleanly, and the app itself
  launched with no errors after the rename.
- Known, deliberate (not a bug) remaining gap, restated for
  visibility: MR only toggles its own LED indicator today. It does
  NOT arm/disarm any actual recording behavior in the daemon -- that
  was scoped out explicitly earlier in this project and still isn't
  designed. Anyone picking this up next should treat that as an open
  feature, not a bug to "fix."

### GUI-daemon profile desync bug + gold border on assigned keys (2026-09-14)

The sibling G510s project's session found and fixed a real bug on
their side, then flagged the same class of bug might exist here --
checked, and it did.

**The bug**: `GKeysTab.select_profile()` (clicking M1/M2/M3 in the
GUI) only ever updated the LED and the canvas highlight -- it never
wrote `g910_macro_profile`, the status file `g910_macro_daemon.py`
uses to know which profile is active. The daemon only wrote that file
itself, on a real physical M-key press, and its `select.select([fd],
[], [])` blocked forever with no timeout, so it had no way to notice
an external change even if the file did change. Net effect: click M2
in the GUI, press a G-key -> daemon replays the OLD profile's macro
while the screen shows M2, and within ~500ms `poll_active_profile()`
silently flips the GUI back to whatever the daemon still thinks is
active. Confirmed live before calling it a bug (not just theorized
from reading the code) -- clicking M2 did visibly revert on its own.

**The fix**: `select_profile()` now writes the same status file
(`_write_active_profile`); the daemon's loop gained a 0.5s `select()`
timeout so it wakes up on its own and checks the file via the new
`read_active_profile()` on every wake, not just when it writes the
file itself. Confirmed live: clicked M2, waited several seconds,
stayed on M2.

**Also added**: a gold border on G-key buttons that have a macro
saved in the currently active profile (`GKeysTab.
refresh_assigned_keys()`, called on profile switch and after the
macro dialog closes) -- a feature request relayed from the user after
it was built on the G510s app's canvas first. Confirmed working live.

### Profiles panel overflow + color-picker workaround (2026-09-15, phase 1 wrap-up)

**Real bug**: `ProfilesTab`'s saved-profiles list had no scroll
container -- a plain `QVBoxLayout` added straight into the fixed-width
panel. Saving enough profiles to exceed the window's height just laid
the extra rows out past the bottom edge: invisible, unreachable, no
scrollbar. Not data loss (every profile was always intact in
`g910_profiles.json`, confirmed by reading the file directly) -- pure
rendering bug. Fixed: wrapped the list in a `QScrollArea`
(`setWidgetResizable(True)`, capped at 260px so a short list doesn't
stretch into a big blank gap before the status label), added matching
dark-theme `QScrollBar`/`QScrollArea` QSS.

That fix immediately surfaced two follow-on issues, both from live
use, both fixed the same session: each profile row's Load/Delete
buttons got cut off once the scrollbar ate into the already-narrow
220px panel width -- fixed by stacking the name above the buttons
instead of side-by-side (also more robust to arbitrarily long profile
names than any fixed width could be). And the profile name text
wasn't centered -- fixed.

**Color picker investigation**: the user reported purple consistently
applying as blue, "used to work." Traced this all the way down before
concluding anything: `bl.set_group_color()`/`set_main_board_color()`
called directly against the real device, across every block (keys,
gkeys, logo) -- each one sent `#8000ff` and `keyledsctl get-leds` read
back the exact same `#8000ff` every time, no exceptions. The actual
GUI code path (`ColorModeSidebar.on_apply_hex()`) tested the same way
with the same clean result. Checked git history for any change to the
color pipeline that could explain a regression -- found none, and no
prior record of purple specifically being verified working before
this. Since KDE's own native `QColorDialog` (not our code at all) was
also suspected -- the screenshot the user sent showed its own hex
readout as `#5500ff` regardless of which swatch was clicked -- added a
manual hex-entry field (`ColorModeSidebar.hex_edit` +
`on_apply_hex()`) as a reliable path that bypasses the picker's
gradient square entirely, refactoring the shared apply logic into
`_apply_color()` so both paths (dialog and hex field) go through the
same code. In the end the user confirmed the keys showed correctly as
purple -- resolved, cause never fully pinned down (possibly a
transient rendering state, possibly the hex field itself being the
fix), but the hex-entry field stays as a permanent, more reliable
alternative to the picker regardless.

**Phase 1 status**: with these fixed, G910 is being treated as having
reached its first complete, stable stage -- further features/polish
come later, this is a deliberate stopping point, not "done forever."

### Color picker rebuild + layout compaction pass (2026-09-15)

Replaced the sidebar's "Pick Color & Apply" button (KDE's native
`QColorDialog.getColor()`) with an in-app control: a live preview
swatch, a hex-entry field, and a preset grid -- all going through one
shared `_apply_color()` path. First iteration also included a custom
click/drag Hue/Saturation gradient square (`HueSatPicker`); removed
entirely by request in favor of presets + hex only, no gradient
square.

**Real preset-color research, not guessed**: checked solaar's own
color picker (`palette.py`) -- it's a plain GTK color button with zero
gamma/calibration logic, confirming there's no secret "hardware-
compatible" correction technique in use by a comparable real app. Then
found `logitech_receiver.special_keys.COLORS` (the library solaar is
built on) ships a real curated palette sourced directly from Xorg's
own `rgb.txt` -- swapped the sidebar's presets to that same list (Red/
Orange/Yellow/Green/Blue/Purple/Cyan/Magenta/Pink), dropping White and
the earlier guessed "Blue-Violet" hue.

**Real bug, investigated before fixing anything**: a report that
preset "Red" displayed as pink on the real keyboard turned out NOT to
be a bug -- `bl.set_group_color()` called directly with pure
`#ff0000` at full brightness was confirmed live as "deep red as
expected." The likely cause was the brightness slider sitting below
100% at the time of the original test (dimming can shift perceived
hue on RGB LEDs) -- not a color-value or hardware-compatibility
problem needing a fix.

**Layout, several rounds of live feedback, each verified before
moving to the next**:
- Sidebar's own content (6 zone buttons + brightness + color
  controls) was naturally taller than the keyboard canvas, so
  `MainWindow`'s `adjustSize()` grew the WHOLE window to fit the
  sidebar, leaving the canvas/G-Keys column with a big blank gap.
  Fixed the same way the Profiles panel already was: wrapped the
  sidebar's content in a capped `QScrollArea` so the canvas (not
  whichever side panel happens to be tallest) drives the window's
  height.
- That in turn made the Profiles panel the tallest column instead --
  tightened its own scroll cap to bring the window back down further.
- **Real bug in the first version of both fixes**: the scroll areas'
  `setMaximumHeight()` caps also blocked them from growing when the
  user manually dragged the window taller afterward -- confirmed live
  via a screenshot showing dead space below both panels after a
  manual resize. Fixed by relaxing the cap back to Qt's own
  `QWIDGETSIZE_MAX` immediately after `MainWindow`'s one-time
  `adjustSize()` call, so the cap only shapes the initial size, not
  ongoing resize behavior. Verified both synthetically (`win.resize()`
  + checking each panel's actual `QScrollArea` grew by the full
  delta) and live by the user actually dragging the window.
- Zone target buttons switched from a 6-row vertical list to a
  2-column grid -- real complaint that stacked full-width buttons for
  a small set of short labels wasted a lot of vertical space.
  Also tightened `QPushButton#ZoneButton` padding, and the hex field
  moved above the presets with a bolder label (found via live use:
  the user hadn't noticed it existed at all in its previous position
  below the swatches).
- Profile cards got their own distinct `QWidget#Card` background --
  real contrast bug found via live use: cards previously shared the
  exact same `QWidget#Panel` background as their own parent panel,
  giving zero visual separation between adjacent cards. Load/Delete
  buttons switched to the same compact `#ZoneButton` style as
  everywhere else.

Canvas itself also bumped ~18% bigger (`CELL_PX` 34->40,
`GUTTER_PX` 4->5) by request, to better fill the vertical space
freed up by the above compaction.

All of the above compiled clean, smoke-tested, and verified against
the real device (preset colors round-tripped through
`get_key_color()` after the full layout churn, confirming nothing
regressed functionally) before being called done, per the user's
explicit "recheck yourself" at the end of this pass.
