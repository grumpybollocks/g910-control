# G910 Orion Spectrum Control App -- Planning Notes
Branch: g910-macros (started as an untouched copy of `main`, the G510s
LCD app -- diverging from here). This file documents the G910 project
specifically; README.txt in this same repo is the G510s LCD project's
docs and describes different hardware -- don't conflate the two.

PROJECT STATUS -- read this block first:

PLANNING PHASE. NO APP CODE WRITTEN YET. Do not start implementation
until the user explicitly signs off on the finalized plan below --
they have said this multiple times and it matters to them. The deep
research pass mentioned below has long since completed; all backend
decisions are FINALIZED (see DECISIONS section). The G-key/M-key/MR
HID protocol AND the M1/M2/M3/MR indicator LED control have both now
been empirically proven working end-to-end on the real keyboard (see
M-KEY/MR INDICATOR LED CONTROL section near the end of this file --
this was the last major open unknown and it's now resolved). What
remains is writing the actual g910_app.py / macro daemon / systemd
service -- see NEXT STEPS at the end of this file.

## WHAT THIS IS SUPPOSED TO BECOME
Same kind of app as g510_app.py (PyQt5, one window, QTabWidget,
tab-per-feature) but for a Logitech G910 Orion Spectrum keyboard
instead of a G510s. Two tabs only, no LCD tab (G910 has no screen):
  - Backlight/RGB tab: per-key color, brightness, effects (breathing/
    wave/cycle).
  - G-Keys tab: G1-G9 macro record/playback (keystroke combo or shell
    command), switchable via M1/M2/M3 profiles, reusing g510_app.py's
    RecorderThread/MacroRecordDialog pattern. MR key = a literal
    macro-record toggle (the user explicitly chose this over treating
    MR as a 4th M-profile, which is what one of the reference projects
    below does by default).

## HARDWARE FACTS -- CONFIRMED EMPIRICALLY on ac130arch (2026-09-13)
Do NOT re-derive these, they were checked directly on the real device,
not assumed:
- USB ID 046d:c335, lsusb identifies it as "G910 Orion Spectrum
  Mechanical Gaming Keyboard".
- Kernel driver bound: plain `usbhid` / `hid-generic` -- NOT
  `hid_lg_g15` like the G510s. This machine has no special in-kernel
  driver for this device at all.
- Two USB interfaces, each with its own hidraw node (confirmed via
  /dev/input/by-id symlinks and each hidraw's uevent HID_PHYS field):
    hidraw0 = interface 0 (paired with evdev event2, has EV_LED bits --
      the caps/num/scroll-lock-style interface)
    hidraw1 = interface 1 (paired with evdev event3)
- evdev capture confirmed EMPTY for G-keys: ran a live 90-second
  python-evdev listener on both event2 and event3 while attempting to
  press G-keys/M-keys/MR -- zero relevant events. Unlike the G510s's
  L1-L5 buttons (which ARE plain Linux keycodes, KEY_KBD_LCD_MENU1..5),
  this keyboard's G-keys/M-keys/MR do NOT show up as normal Linux
  keycodes at all. They must be read as raw vendor-specific HID++ 2.0
  reports via hidraw (or libusb) -- confirmed necessary, not assumed.
- No /sys/class/leds/ entry for this device beyond the standard
  input209/input211/... capslock/numlock/scrolllock LEDs every keyboard
  gets. Confirmed there is NO simple LED-class sysfs backlight
  mechanism like the G510s's /sys/class/leds/g15::kbd_backlight/ --
  RGB control needs a real HID++ 2.0-speaking tool, not a sysfs write.
- python-evdev already installed and importable on this machine.
  PyQt5 usage is already proven via the sibling g510_app.py.
- `yay` is available as the AUR helper.

## GITHUB ACCESS -- SET UP 2026-09-13
This machine did NOT have GitHub SSH access before this
project -- the only existing key (~/.ssh/id_ed25519) is for a
separate cross-machine bridge to the user's other Arch box, not
GitHub, and was never registered on GitHub.
Fixed by generating a SEPARATE dedicated key:
  ~/.ssh/id_ed25519_github (public half added to the user's GitHub
  account by the user themselves)
  ~/.ssh/config now has:
    Host github.com
        IdentityFile ~/.ssh/id_ed25519_github
Verified working: `ssh -T git@github.com` returns "Hi grumpybollocks!
You've successfully authenticated". Don't recreate this key or config
-- it's done.

## DECISIONS -- FINALIZED after a deep research pass (2026-09-13)
- MR key = literal macro-record toggle. CONFIRMED user decision.
- SUPERSEDED: the earlier lean toward `g810-led` for the Backlight tab
  is WRONG and must not be used -- confirmed via the AUR RPC API that
  both `g810-led` and `g810-led-git` have been REMOVED from AUR
  (resultcount:0 for both names as of 2026-09-13). `yay -S
  g810-led-git` would fail on a fresh install. Do not resurrect this
  plan without re-checking AUR first.
- FINAL BACKEND for BOTH tabs: `keyleds` (plain AUR package name, NOT
  `keyleds-git` -- that's the original upstream, abandoned since 2021).
  The correct package is maintained by `ticpu` (co-maintained by the
  original author `spectras` + `jtyr`), points at
  github.com/ticpu/keyleds, confirmed NOT archived and last pushed
  2026-09-08 (5 days before this was checked) -- a live, actively
  maintained project. One tool covers both the Backlight tab (per-key
  RGB) and the G-Keys tab (G-key/M-key event source) instead of
  stitching together two separate dependencies.
  - Explicitly lists G410/G513/G610/G810/G910/GPro support, ships a
    `keyledsctl` CLI, a DBUS interface, and a `python/keyleds.pyx`
    Cython binding directory (a real Python API MAY be usable directly
    -- unconfirmed whether it builds automatically with the main
    package, see unknowns below).
  - Its shipped `logitech.rules` udev file uses `uaccess` tagging
    (systemd-logind seat-based access) on hidraw nodes restricted to
    `bInterfaceProtocol=="00"` and on `ID_INPUT_KEY`-tagged event
    nodes -- confirmed it does NOT use libusb's
    detach_kernel_driver() anywhere. Same non-exclusive-claim
    philosophy this repo's G510s project already validated. No custom
    udev rule needs to be hand-written -- the AUR package installs its
    own, and no runtime root/sudo is needed once installed.
  - REAL, NOT HYPOTHETICAL CAVEAT: keyleds' own GitHub issues (#17,
    #36, #57) show mixed real-world results from other G910 owners --
    one report of the device not being detected at all, another of
    individual zone names ("logo", "light") not working even though
    broader effects do. These may predate ticpu's fork improvements,
    but this is NOT confirmed clean -- treat as a real risk to verify
    on this actual keyboard, not swept under the rug.
- RULED OUT, with reasons (don't re-litigate without new evidence):
  - OpenRGB: confirmed zone-only control for G910 per its own wiki
    (established before this research pass).
  - logiops/logid (AUR `logiops`, otherwise a healthy 29-vote
    package): its own TESTED.md lists 17 devices, all MX-series
    mice/keyboards -- zero G-series, zero "Orion", zero G910.
    Definitively does not support this keyboard.
  - LogiGSK: Java-based, LED-only (no G-key support at all), unusual
    heavier toolchain (Apache Ant + `alien` .deb/.rpm conversion), no
    evidence of recent activity. Not worth it next to keyleds.
  - gkeybind: built on top of keyleds itself, plus needs the Crystal
    language toolchain just to build. Unnecessary extra layer since
    keyleds already exposes G-key events and we're building our own
    PyQt5 macro UI, not reusing gkeybind's separate keybinding engine.
  - aquova/g910-macros (Rust, uinput-remap-only): superseded by
    keyleds' more complete feature set -- would still need something
    else bolted on for actual macro/profile logic.
- KEPT AS FALLBACK REFERENCE ONLY (not the primary plan): JSubelj's
  g910-gkey-macro-support. Its actual usb_device.py source was
  directly verified: detach_kernel_driver() targets INTERFACE 1 ONLY
  (never interface 0, normal typing stays untouched) -- so the
  "hogging" risk is smaller than first assumed. Real, working,
  forum-confirmed option to fall back to if keyleds' G910 G-key
  support turns out incomplete on real hardware.

## FINAL DEPENDENCY LIST (from real AUR RPC data, not guessed)
`keyleds` AUR package Depends: libevdev, libuv, libx11, libxi,
libyaml, luajit, systemd-libs. MakeDepends: cmake. License GPL-3.0.
All ordinary Arch extra/core packages, no exotic transitive AUR chain.

## INSTALL SCRIPT: ./install-g910.sh (added 2026-09-14)
Actual runnable script now, not just a pasted command -- mirrors the
sibling G510s project's install.sh style (numbered steps, safe to
re-run, --needed everywhere so it just skips what's already there).
Separate script from install.sh on purpose (that one is the G510s
project, different hardware/deps entirely).

Equivalent to the one-shot command that was originally pasted here and
confirmed working on 2026-09-13:
  sudo pacman -S --needed base-devel git cmake libevdev libuv libx11 \
      libxi libyaml luajit systemd-libs python-pyqt5 python-evdev python-dbus
  yay -S --needed keyleds

(base-devel/git/cmake = AUR build tooling; the rest are keyleds's own
Depends, pre-installed via pacman so yay won't prompt mid-build.
python-pyqt5/python-evdev already proven via the G510s app. python-dbus
turned out to NOT actually be needed by the final architecture -- this
project ended up bypassing keyledsd entirely, reading hidraw directly
and using keyledsctl/libkeyleds.so via ctypes instead -- kept anyway
since it was part of the original confirmed-working install and costs
nothing to have. yay -S keyleds compiles from source via cmake --
expect a short wait, not instant. No reboot needed; the udev rule
takes effect on replug, or `sudo udevadm control --reload` + replug if
it doesn't pick up live.)

UPDATE (2026-09-14): added `ydotool` to the script -- the macro
daemon's (`g910_macro_daemon.py`, on the `g910-canvas` branch) replay
mechanism, same as the sibling G510s project already uses. Official
`extra` repo, not AUR -- confirmed via `pacman -Si`/`pacman -Fl` before
adding it, not assumed missing-then-guessed-present. This was a real
gap: the daemon code was written and committed before checking whether
`ydotool` was actually installed, and it was not -- caught via a
direct `which ydotool` check before ever running the daemon live.
Ships both the `ydotool` client and `ydotoold` background daemon it
needs, plus its own systemd --user service unit and udev rule for
uinput permissions already -- install-g910.sh now also runs
`systemctl --user enable --now ydotool.service` as its final step.

## INSTALL CONFIRMED (2026-09-13)
User ran the one-shot install command. Verified via `pacman -Qi
keyleds`: version 1.2.0-1, all Depends satisfied, installed cleanly.
Binaries present: /usr/bin/keyledsctl, /usr/bin/keyledsd. Confirmed
`keyledsctl list` detects the real hardware:
  /dev/hidraw1 046d:c335 [096239583837]   <- the G910
  /dev/hidraw4 046d:c332 [1062376D3633]   <- the G502 mouse, also HID++
`keyledsctl info -d /dev/hidraw1` output (real, not summarized):
  Name: G910 Orion Spectrum, Model: c33500000000, Serial: 33394709
  Known features: ... gamemode name layout2 gkeys mkeys mrkeys
    reportrate dfu-control leds led-effects
  G-keys: 9
  LED block[01]: 105 keys, max_rgb(255,255,255)  <- main keys, TRUE
    per-key RGB, all 105 keys individually addressable (NOT zone-only
    -- this is real confirmation the earlier OpenRGB-vs-keyleds
    reasoning was correct)
  LED block[02]:   5 keys, max_rgb(1,0,0)        <- CORRECTED below:
    this is MULTIMEDIA (0x02 in the block enum), NOT the M-keys as
    first guessed here -- see M-KEY/MR INDICATOR LED CONTROL section.
    Never written to this session; leave alone, user confirmed these
    keys already work perfectly.
  LED block[04]:   9 keys, max_rgb(255,255,255)  <- G-keys' own
    individual backlighting, full RGB (KEYLEDS_BLOCK_GKEYS = 0x04)
  LED block[10]:   2 keys, max_rgb(255,255,255)  <- LOGO block
    (KEYLEDS_BLOCK_LOGO = 0x10, confirmed by exact match against the
    real block enum, not a guess)
  (Note: M1/M2/M3/MR have NO color-settable LED block on this unit at
  all -- confirmed later in this file, "Led block 40 not found" -- they
  are controlled via separate dedicated functions, not the block-color
  system. See M-KEY/MR INDICATOR LED CONTROL section below.)

## G-KEY/M-KEY/MR PROTOCOL -- FULLY CONFIRMED VIA REAL RAW CAPTURE
This was the single biggest open unknown and it is now COMPLETELY
resolved, not guessed. Method: a small non-exclusive hidraw reader
(os.open/os.read, no libusb, no detach_kernel_driver -- same low-risk
approach as the G510s project) was run against /dev/hidraw1 while the
user physically pressed G1 through G9, then M1-M3, then MR, in that
exact order, one at a time. Every single press/release produced a
clean, unambiguous 20-byte report. Full results:

  G1: 11 ff 08 00 01 00 00...   (press) / 11 ff 08 00 00 00... (release)
  G2: 11 ff 08 00 02 00 00...
  G3: 11 ff 08 00 04 00 00...
  G4: 11 ff 08 00 08 00 00...
  G5: 11 ff 08 00 10 00 00...
  G6: 11 ff 08 00 20 00 00...
  G7: 11 ff 08 00 40 00 00...
  G8: 11 ff 08 00 80 00 00...
  G9: 11 ff 08 00 00 01 00...   <- spills into byte 5, bit 0 (9th key,
                                    can't fit in the byte4 bitmask with
                                    G1-G8)
  M1: 11 ff 09 00 01 00 00...
  M2: 11 ff 09 00 02 00 00...
  M3: 11 ff 09 00 04 00 00...
  MR: 11 ff 0a 00 01 00 00...   <- CONFIRMED a genuinely distinct event
                                    (report type 0x0a), not just a 4th
                                    M-profile -- directly supports the
                                    user's requested "literal
                                    macro-record toggle" design, no
                                    workaround needed.

Report structure: byte0=0x11, byte1=0xff (standard HID++ 2.0 "long
report" prefix), byte2=event type (0x08=gkeys, 0x09=mkeys,
0x0a=mrkeys), byte3=always 0x00 (reserved, confirmed constant across
every single capture), byte4(+byte5 for G9 only)=bitmask, one bit per
key in that group, set on press. Release = the exact same report shape
with the bitmask zeroed (confirmed on every single key, no exceptions).
20 bytes total per report.

CRITICAL SETUP STEP, don't skip: by default the G910's G-keys act as
plain F13-F21 passthrough (per aquova/g910-macros' and JSubelj's
projects, matches what we saw too) and DO NOT emit these HID++ reports
at all -- confirmed empirically: an earlier capture attempt with zero
setup produced ZERO bytes on hidraw1 despite real key presses. The fix:
  keyledsctl gkeys -d /dev/hidraw1 on
run once, after which every press produced clean reports immediately
and repeatably across multiple separate test runs. This command must
run at daemon startup (systemd service ExecStartPre, or first line of
the daemon itself) every time, since it's a live device-mode toggle,
not a persisted setting.

## ARCHITECTURE REVISION based on this confirmed data
Since the exact report format is now fully known and verified, the
G-Keys tab does NOT need keyledsd (the background daemon) running at
all -- and there's good reason to avoid it: keyledsd has its own real,
observed bug on this exact machine (see BUGS FOUND below) and its
Lua-plugin/effect discovery mechanism was fought with for a while
without success (custom .lua effects placed via -m and in an effects/
subdirectory were never found -- "no module <keytest> in search
paths" -- root cause not resolved, not worth chasing further since we
don't need it).
Revised plan:
  - G-Keys tab: our own small Python daemon reads /dev/hidraw1 directly
    (hidraw_sniff.py in this session's scratchpad is a working proof of
    concept for the read loop -- same pattern, not literally reused
    verbatim, will become g910_macro_daemon.py mirroring
    g510_macro_daemon.py's structure), sends `keyledsctl gkeys -d
    /dev/hidraw1 on` once at startup, decodes the confirmed byte
    format above, and drives macro playback/M-profile switching/MR
    record-toggle directly -- no keyleds daemon in the loop for this
    part at all.
  - Backlight tab: still uses `keyledsctl` (the CLI, shelled out to,
    not the Python binding -- see BUGS FOUND below for why) for
    `set-leds`/`get-leds` per-key color commands against LED block 01
    (confirmed 105 keys, true per-key RGB) and possibly block 04 (the
    G-keys' own backlighting) as a secondary control.
  - `keyleds` package stays installed for its `keyledsctl` binary and
    udev rule (uaccess tagging -- confirmed this is what allows
    non-root reads of hidraw1 at all). The `keyledsd` background
    service itself is NOT needed and should not be enabled/autostarted
    for this project.

BUGS FOUND while testing keyledsd directly (real, observed, not
hypothetical -- keep in mind if keyledsd is ever reconsidered):
1. `could not load layout <c33500000000_0037.yaml>: No such file or
   directory` -- logged on every single keyledsd startup against this
   exact keyboard. The package only ships layout files for this model
   suffixed 0001-0005,0007,0008,000a,000b -- 0037 (this unit's actual
   firmware/region variant) isn't among them. keyledsd silently falls
   back to loading a DIFFERENT KEYBOARD MODEL's layout entirely
   (c32b00000000_0002.yaml, model c32b -- not c335) rather than erroring
   out. If keyledsd's own key-name resolution is ever relied upon, key
   names could be silently wrong. Not a blocker for the revised
   architecture above since we bypass keyledsd's layout system
   entirely, but worth knowing if this project ever revisits it.
2. Custom Lua effects (the `-m <path>` / effects/ subdirectory
   mechanism documented in the sample config) could not be gotten
   working in this session -- consistently "no module <name> in search
   paths" regardless of directory placement. Not investigated further
   since the revised architecture doesn't need it, but don't assume
   custom Lua effects "just work" per the docs without re-verifying.

RESOLVED UNKNOWNS from the previous research pass:
  1. RGB granularity: CONFIRMED true per-key (105 keys, full RGB) --
     see LED block 01 above.
  2. G-key/M-key/MR event delivery: CONFIRMED via direct hidraw read,
     full byte-level mapping captured -- see protocol table above.
  3. MR as distinct event: CONFIRMED (report type 0x0a, separate from
     M1-M3's 0x09) -- supports the literal record-toggle design as-is.
  4. python/keyleds.pyx Cython binding: NOT NEEDED given the
     architecture revision above (we shell out to keyledsctl and read
     hidraw directly instead) -- no longer a blocking unknown.
  5. Session compatibility (X11/Wayland): moot given the architecture
     revision -- we're not using keyledsd's X-focus-based profile
     switching, so this doesn't affect the plan either way.

## M-KEY/MR INDICATOR LED CONTROL -- CONFIRMED WORKING (2026-09-13)
User noticed M1/M2/M3/MR indicator LEDs weren't lit and asked whether
this was the same class of bug as the G510s's M-key LED fix. It is
NOT the same bug -- confirmed by research before touching anything:
the G510s issue was a udev permissions bug (a declarative rule that
silently never matched). The G910's case is architecturally different.

Root cause, confirmed from the actual keyleds source (the real
compiled tarball, cached locally at
~/.cache/yay/keyleds/keyleds-1.2.0.tar.xz -- read directly, not
fetched from a possibly-different upstream commit):
- The installed /usr/include/keyleds.h defines LED blocks as a
  bitmask enum: KEYLEDS_BLOCK_KEYS=0x01, KEYLEDS_BLOCK_MULTIMEDIA=0x02,
  KEYLEDS_BLOCK_GKEYS=0x04, KEYLEDS_BLOCK_LOGO=0x10,
  KEYLEDS_BLOCK_MODES=0x40. CORRECTION to an earlier mistaken
  assumption in this file: block "02" (5 keys, red-only) is
  MULTIMEDIA, NOT the M-keys -- don't touch it, the user confirmed
  those buttons already work perfectly and asked explicitly not to
  mess with them. Nothing in this session ever wrote to block 02.
- `keyledsctl get-leds -b modes` returned "Led block 40 not found" --
  this exact G910 unit's firmware does not expose a MODES color-block
  via the standard LED_BLOCK_INFO enumeration at all.
- BUT libkeyleds.so (already installed, /usr/lib/libkeyleds.so.1) has
  dedicated functions for this, confirmed by reading
  libkeyleds/src/feature_gkeys.c directly from the real compiled
  source: `keyleds_mkeys_set(device, target_id, mask)` -- doc comment:
  "A bit mask of MKeys leds to turn on, bit0 for M1, bit1 for M2, ..."
  -- and `keyleds_mrkeys_set(device, target_id, mask)` -- "bit0 for
  MR." These call a SEPARATE HID++ feature (KEYLEDS_FEATURE_MKEYS /
  KEYLEDS_FEATURE_MRKEYS) from MULTIMEDIA or the LED_BLOCK color
  system entirely -- confirmed safe, no overlap with the working media
  keys. The `keyledsctl` CLI tool simply never exposes these two
  functions as a subcommand (confirmed by reading
  keyledsctl/src/keyledsctl_gkeys.c -- it only calls
  keyleds_gkeys_enable, nothing else). That's the actual root cause:
  a missing CLI feature, not a permissions or hardware bug.

FIX, tested and confirmed physically working by the user, one key at a
time, via a minimal ctypes wrapper calling libkeyleds.so directly
(bypassing the CLI's gap, using the exact same keyleds_open() calling
convention as the real CLI: path + app_id 0x9 (KEYLEDSCTL_APP_ID from
keyledsctl/include/config.h.in), target_id 0xff
(KEYLEDS_TARGET_DEFAULT)):
  M1 lit:  keyleds_mkeys_set(device, 0xff, 0x01) -> user confirmed lit
  M2 lit:  keyleds_mkeys_set(device, 0xff, 0x02) -> user confirmed lit,
           AND confirmed M1 turned off automatically (mask REPLACES,
           doesn't add -- only one bit needs to be set at a time for
           normal M1/M2/M3 exclusivity)
  M3 lit:  keyleds_mkeys_set(device, 0xff, 0x04) -> user confirmed lit
  MR lit:  keyleds_mrkeys_set(device, 0xff, 0x01) -> user confirmed
           lit, AND confirmed it's fully independent of M1/M2/M3 (M3
           stayed lit at the same time MR was lit -- separate feature,
           separate LED, can be on simultaneously)
  MR off:  keyleds_mrkeys_set(device, 0xff, 0x00) -> confirmed working
Keyboard left in a clean state after testing: M1 lit, MR off.
Working test scripts (not final app code, proof-of-concept only) live
in this session's scratchpad: light_m1.py, light_mr.py.

IMPORTANT DISTINCTION the user specifically asked about: calling
keyleds_mkeys_set only changes the LED. It does NOT select a "profile"
on this keyboard -- unlike some other Logitech keyboards, the G910 via
this library has no firmware-level onboard profile memory being
switched here. "Profile" is a concept our own macro daemon will own in
software: when the daemon sees a real M1/M2/M3 press (via the
already-confirmed 0x09 HID++ report), it must (a) update its own
in-memory/on-disk "current profile" state, used to pick which G1-G9
macro set is active, AND (b) separately call keyleds_mkeys_set to keep
the LED in sync with that software state. Same two-steps-tied-together
architecture as the G510s sibling project's already-working M1/M2/M3
profile switching (see README.txt's v1.0 section: "GUI now polls the
daemon's live-profile file every 500ms"). MR will work the same way
for the user's requested literal record-toggle behavior: daemon sees
the MR press event, flips its own "currently recording" state, and
calls keyleds_mrkeys_set to reflect that state on the physical LED.

SELF-AUDIT PASS (2026-09-13) -- re-verifying claims before planning
further, since earlier in this session there were real mistakes
(wrong block-02 guess, corrected above; a failed disown/backgrounding
approach; time lost fighting keyledsd's Lua plugin loader). Went back
and checked what was actually tested vs. merely asserted:
- GAP FOUND: block 01 ("keys", the 105-key main RGB block the entire
  Backlight tab plan depends on) had NEVER been empirically tested
  this session -- only "gkeys" (block 04) and "modes" (confirmed
  absent) had been queried. This was a real hole in the verification,
  not just a hypothetical worry.
- NOW TESTED AND CONFIRMED:
  - `keyledsctl get-leds -d /dev/hidraw1 -b keys` returns exactly 105
    real key=color entries (matches the block's reported key count
    exactly).
  - `keyledsctl set-leds -d /dev/hidraw1 -b keys ESC=0000ff` -> user
    physically confirmed the Escape key turned blue. Takes effect
    immediately, no separate "commit" call needed (contradicts nothing
    in the plan, just confirms it directly rather than assuming from
    the man page).
  - Restored ESC to its original color (`008001`, read from get-leds
    before the test) afterward -- keyboard left exactly as found.
- STILL UNVERIFIED, flagged honestly rather than asserted as fact:
  - Block 04 (gkeys backlighting) has only been read (get-leds), never
    written to (set-leds). Lower priority since the Backlight tab's
    core plan targets block 01; block 04 was always described as
    "possibly...secondary," not a commitment.
  - Whether `keyledsctl gkeys on` truly needs to be re-run every
    session/boot (vs. persisting) was inferred from how similar
    third-party G910 projects describe the default F-key passthrough
    behavior, not directly tested via an actual replug/reboot cycle.
  - Practically low-stakes either way -- the daemon will call it at
    every startup regardless, so this doesn't change the plan, just
    noting it's an inference, not a directly observed fact.

## NEXT STEPS (in order)
1. Write g910_app.py (Backlight tab using `keyledsctl set-leds`/
   `get-leds` against LED block 01 only -- 105 keys, true per-key RGB
   -- then G-Keys tab), reusing g510_app.py's
   RecorderThread/MacroRecordDialog pattern for macro recording.
2. Write g910_macro_daemon.py: reads /dev/hidraw1 directly using the
   now-fully-confirmed report format above, runs `keyledsctl gkeys -d
   /dev/hidraw1 on` at startup, dispatches G1-G9 macros filtered by an
   in-daemon "active profile" variable that M1/M2/M3 presses update,
   calls keyleds_mkeys_set (via ctypes, same pattern as light_m1.py)
   to keep the physical LED in sync with that variable, and treats MR
   as a literal record-toggle event (flips daemon state + calls
   keyleds_mrkeys_set to match) per the user's decision.
3. Write the systemd --user service mirroring
   g510-macro-daemon.service's pattern (no udev rule needed, keyleds
   already installed one that grants non-root hidraw1 access).
4. Test on real hardware, iterate with the user before calling
   anything "done" (per this whole repo's established standard: don't
   claim something works without it being physically confirmed by the
   user on the actual device).

HID++ FEATURE MAP -- FULLY IDENTIFIED (2026-09-13/14, canvas-plan
research), mandatory cross-post from the g910-canvas-rearchitect
branch per the user's instruction that everything learned updates the
## main skeleton, not just a side branch.
Raw feature list from `keyledsctl info -d /dev/hidraw1`:
  [0001, 0003, 4522, 0005, 1e00, 4540, 1eb0, 8010, 8020, 8030, 8060,
   00c1, 1801, 1802, 8080, 8070, 1821]
Mapped against libkeyleds' own real header
(libkeyleds/include/keyleds/features.h, from the same compiled source
tarball used in the earlier audit -- not guessed):
  0001 = FEATURE            0003 = VERSION           0005 = NAME
  4522 = GAMEMODE           4540 = KEYBOARD_LAYOUT_2  00c1 = DFU_CONTROL
  8010 = GKEYS              8020 = MKEYS              8030 = MRKEYS
  8060 = REPORTRATE         8080 = LEDS (the static per-key color
                             feature we've been using this whole
                             project, via feature_leds.c/keyledsctl)
  8070 = LED_EFFECTS (separate from LEDS -- see below, NOT what we've
                       been using, previously and WRONGLY assumed by
                       the assistant to be the same as 8080 or to not
                       exist -- corrected here)

CORRECTION to an earlier mistake: at one point this session the
assistant said "0x8070 = leds" -- that was backwards, caught while
reading the real header directly instead of relying on memory.
0x8080 = LEDS, 0x8070 = LED_EFFECTS. Keep this straight for any future
protocol work.

STILL UNIDENTIFIED by libkeyleds' own header (not in features.h at
all): 1e00, 1eb0, 1801, 1802, 1821. Researched via web search (not
guessed): on OTHER Logitech devices (G402 mouse, MX Master 3S) these
same five IDs appear as "hidden" features. ONE OF THEM IS DANGEROUS,
CONFIRMED BY A REAL SOURCE: 0x1802 = DEVICE RESET, explicitly flagged
by other researchers as excluded from automated feature-probing sweeps
because of what it does. DO NOT call/probe 0x1802 on this device. The
other four (1e00, 1eb0, 1801, 1821) remain genuinely unidentified --
not researched further yet, not assumed to be safe or relevant.

FEATURE 0x8070 (LED_EFFECTS) -- REAL, DETAILED THIRD-PARTY SPEC FOUND,
NOT YET VERIFIED ON THIS HARDWARE:
Found a real, detailed HID++ 2.0 protocol writeup for this feature
(openlogi.org/hidpp/features/x8070-color-led-effects) -- NOT
implemented anywhere in libkeyleds (confirmed: no feature_led_effects.c
or any 0x8070 reference exists in the whole keyleds-1.2.0 source tree).
If accurate for this exact keyboard, this would be a genuine per-zone
HARDWARE-SIDE effects engine (Disabled/FixedColor/PulsingBreathing/
Cycling/ColorWave/Starlight/LightOnPress/BootUp/DemoMode/Ripple, effect
IDs 0-11) with a persistence model (Volatile/VolatileAndNonVolatile/
NonVolatileOnly -- the non-volatile options write to EEPROM, meaning
colors/effects COULD survive power cycles at the firmware level if
this works as documented). This would be a fundamentally better answer
than anything considered so far for BOTH the "effects" feature request
AND the reboot-persistence open question from the canvas plan --
better than running keyledsd (which we already ruled out for real
bugs) or a host-side software color-cycling loop.
CAVEATS, stated honestly, not swept under the rug:
- This is THIRD-PARTY reverse-engineering documentation, not Logitech's
  own spec, and not yet tested against this specific G910 unit's
  firmware at all.
- The source document itself does not confirm G-series gaming
  keyboards are covered by this feature description -- it says
  "Logitech keyboards and mice" generally, without listing this model.
- Nothing has been sent to feature 0x8070 on the real device yet. Any
  actual use requires: (a) a safe READ-ONLY probe first (get_info,
  function index 0, 3-byte short request) to see if the response shape
  matches the documented format at all, before trusting any of the
  write-side functions (set_zone_effect etc.), and (b) doing that probe
  with the user's awareness/go-ahead first, same discipline as every
  other write to this device throughout this project.
- libkeyleds has zero code for this feature, so using it would mean
  either implementing the raw HID++ calls ourselves (ctypes + manual
  report construction, following the same report format already
  reverse-engineered for reading gkeys/mkeys/mrkeys earlier in this
  project) or finding another existing tool that already implements
  0x8070 correctly.
NEXT STEP if this gets pursued: a read-only get_info probe on
/dev/hidraw1, reported back before anything else is attempted.

FEATURE 0x8070 -- CONFIRMED REAL AND WORKING ON THIS EXACT HARDWARE
## (2026-09-14), READ-ONLY PROBES ONLY, NOTHING WRITTEN TO THE DEVICE YET
The "next step" above was carried out. Method, precise, not guessed:
cross-referenced two independent real sources first (a documented
third-party spec, openlogi.org, AND libratbag's actual production C
implementation, github.com/libratbag/libratbag src/hidpp20.c/.h --
the second one confirmed this isn't just theoretical, it's real code
running against real Logitech hardware today via Piper). Got the exact
byte layout from libratbag's source rather than assume anything:
REPORT_ID_SHORT=0x10, REPORT_ID_LONG=0x11 (from src/hidpp-generic.h),
CMD_COLOR_LED_EFFECTS_GET_INFO=0x00, GET_ZONE_INFO=0x10 (from
hidpp20.c), and the exact struct layouts from hidpp20.h.

Reused proven, already-tested code where possible rather than
reinvent: called the PUBLICLY EXPORTED `keyleds_get_feature_index()`
from libkeyleds.so (the same library already used successfully for the
M-key LED fix) via ctypes to resolve 0x8070's real per-device
feature-index slot -- confirmed keyleds_call() itself (the library's
internal generic request function) is NOT publicly exported, so the
actual GET_INFO/GET_ZONE_INFO requests were constructed by hand as raw
HID++ short reports and sent via a plain os.write()/os.read() on
/dev/hidraw1 -- same non-exclusive hidraw approach already proven
throughout this project, nothing new architecturally.

RESULTS, verified against the real struct field order in libratbag's
header (byte-by-byte, not assumed):
  GET_INFO reply: zone_count=2, nv_capabilities=0x0001 (bit0 =
    BOOT_UP_EFFECT supported per the spec's bitmask), ext_capabilities
    =0x0000 (no extended capability flags set).
  GET_ZONE_INFO zone 0: location=1 (PRIMARY -- the main keyboard),
    num_effects=6, persistency_caps=0x00.
  GET_ZONE_INFO zone 1: location=2 (LOGO), num_effects=4,
    persistency_caps=0x00.
So: this exact G910 Orion Spectrum genuinely has a working,
responsive, real hardware-side effects engine via feature 0x8070,
covering the Primary (main board) zone with 6 effects and the Logo
zone with 4 effects. This is a real, confirmed capability, not
speculation -- the device answered with correctly-structured data
matching the documented protocol precisely.

A REAL MISTAKE MADE AND CAUGHT WHILE DOING THIS, kept here honestly
rather than silently fixed: the first version of the zone-info probe
script mis-indexed the reply bytes (forgot the zone_info struct's
leading `index` echo byte shifts every subsequent field over by one),
so its first printed output mislabeled `num_effects` as
`persistency_caps`. Caught by going back and reading the EXACT struct
field order from libratbag's header (`index, location(BE16),
num_effects, persistency_caps`) instead of trusting the quick script's
first pass -- the numbers above are the corrected, struct-verified
ones. Lesson: when parsing an unfamiliar binary reply, get the exact
field layout from source first, don't reason about byte offsets from
memory alone, even when the request format itself is already confirmed
correct (the request worked fine; the mistake was only in interpreting
the reply).

WHAT'S STILL NOT KNOWN, explicitly, not swept under the rug:
- WHICH of the 6 Primary-zone / 4 Logo-zone effects are which (effect
  IDs, via GET_ZONE_EFFECT_INFO per zone+effect index) -- not yet
  queried. Next safe read-only step if this is pursued further.
- What persistency_caps=0x00 on both zones actually means for surviving
  reboots in practice -- the enum in libratbag's header suggests
  "unsupported" but this hasn't been tested against a real reboot, and
  the field's exact semantics for THIS firmware aren't confirmed by a
  primary source, only inferred from a general enum used across many
  different Logitech devices.
- Nothing has been WRITTEN to feature 0x8070 yet -- no set_zone_effect
  call has been attempted. All probes so far are 100% read-only.
- Feature 0x1802 (DEVICE RESET, see the feature map section above)
  remains untouched and off-limits.

FULL EFFECT CATALOG PER ZONE -- CONFIRMED VIA GET_ZONE_EFFECT_INFO
(2026-09-14), still 100% read-only, nothing written:
Queried every effect slot for both zones (request: function 0x20,
params[0]=zone_index, params[1]=zone_effect_index; reply struct per
libratbag's header: zone_index, zone_effect_index, effect_id(BE16),
effect_caps(BE16), effect_period(BE16)).

  Zone 0 (Primary, main board), 6 effects:
    slot 0: Disabled            caps=0x0000 period=0ms
    slot 1: Fixed (solid color) caps=0x0005 period=0ms
    slot 2: Breathing           caps=0xc001 period=992ms
    slot 3: Cycling             caps=0xc001 period=992ms
    slot 4: Wave                caps=0xdce1 period=30ms
    slot 5: Starlight           caps=0x0000 period=0ms
  Zone 1 (Logo), 4 effects:
    slot 0: Disabled            caps=0x0000 period=0ms
    slot 1: Fixed (solid color) caps=0x0005 period=0ms
    slot 2: Breathing           caps=0xc001 period=992ms
    slot 3: Cycling             caps=0xc001 period=992ms
    (no Wave/Starlight on the Logo zone -- makes sense, single small
    zone, those effects need more physical area to read as intended)

This is a real, confirmed, hardware-side effects engine on this exact
keyboard -- genuine Breathing/Cycling/Wave/Starlight, running entirely
on the device's own firmware, no keyledsd or any host daemon needed at
all. Directly answers the original "effects" request from early in
this project's planning far better than anything considered before
(keyledsd was ruled out for real bugs; a host-side software color-loop
was the fallback plan) -- IF the write side (set_zone_effect) actually
works as documented once tested, which it has NOT been yet.

`effect_caps` bit meanings not yet decoded (would need either more
libratbag source reading or empirical bit-flipping against a real
set_zone_effect call to infer, neither done yet). `effect_period` is
likely the effect's natural animation cycle length in milliseconds
where applicable (Breathing/Cycling both report 992ms, Wave reports a
much faster 30ms) -- plausible reading, not confirmed against a
primary source.

NEXT STEP if this gets pursued further: an actual set_zone_effect
write call -- e.g. setting zone 0 to effect slot 1 (Fixed) with a
specific RGB color, the safest possible first write since it's
equivalent to something already proven safe via the "leds" feature's
static colors, just through a different feature. Requires the user's
explicit go-ahead first, same as every other write to this device
throughout this project -- not yet attempted.
