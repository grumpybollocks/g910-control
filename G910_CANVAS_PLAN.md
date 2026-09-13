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
- **Backend integration**: unchanged. Click handling still calls the
  exact same `g910_backlight.set_key_color`/`set_group_color`
  functions already proven working.
- **Color Mode sidebar**: unchanged, sits next to the new canvas
  widget exactly like it sits next to the button grid today.

## Open questions — need your answer before any code gets written

1. **Logo key placement**: where should it sit on the redrawn
   keyboard? (Your screenshot shows it between the M-keys row and the
   G1 column, roughly where the physical Logitech "G" logo actually
   is on the real board.)
2. **Interaction scope for this pass**: single-click only (exactly
   matches current behavior — click a key, pick a color, done — just
   on more accurate geometry), or also build drag/multi-select now
   (bigger lift, matches Solaar/OpenRGB's full capability sooner but
   is more to get right in one pass)?
3. **Live color display**: should the canvas query the device's real
   current colors on startup (extra `get-leds` calls, shows true state
   but adds a bit of latency), or just track colors locally in the app
   as you apply them (simpler, but could show stale info if something
   else changed a color outside the app)?

Nothing gets implemented until these are answered.
