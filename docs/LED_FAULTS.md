# Keys showing the wrong colour: finding out why, and hiding it

Some keys light pink under white, or orange under green, or stay dark.
This page is the method that settled it on one real G910: it was the
hardware, not the software, and a colour scheme can hide it completely.

## 1. Run the three-colour test

    tools/g910-led-test.sh green
    tools/g910-led-test.sh blue
    tools/g910-led-test.sh red

Each one lights the whole keyboard in one pure colour. Note which keys
look wrong in each. An LED has three parts (red, green, blue), so this
shows exactly which part of which key is faulty.

Result on the keyboard this was written for:

| Colour | What happened |
|---|---|
| green | Numpad 2/3, Pause, Right Shift turned orange; Arrow up dark |
| blue  | every key correct |
| red   | every key correct except Arrow up (dark) |

So on four keys the green signal leaks into the red LED, and Arrow up
only has a working blue LED.

## 2. Check it is not software

- `keyledsctl get-leds -d /dev/hidrawN -b keys` shows what the keyboard
  itself has stored. If it stores the right colour and shows the wrong
  one, the fault is after the firmware.
- `tools/g910-raw-set.py /dev/hidrawN 00ff00 5a 5b` writes HID++ frames
  directly, with no keyleds and no app involved (the numbers are USB HID
  key codes; 5a/5b are Numpad 2/3). Same wrong colour means it is not
  this app or its library.
- Logitech G HUB on Windows showing the same wrong colours settles it.

## 3. Why several keys at once

The keyboard's LEDs are driven as a matrix: keys share lines. One
leak on a shared line shows up on every key fed by it, even keys far
apart. Liquid damage is the usual cause; residue left on a board can
turn conductive and cause faults months or years later. On this
keyboard, spraying cleaner near one key made all the faulty keys
flicker together, which fits one shared fault rather than four dead
LEDs. The exact wiring is not published, so this is inference.

Each LED sits on the board under the centre of its switch, and the
switches are soldered. Cleaner sprayed from the top mostly does not
reach it. The repair that sources agree on is opening the keyboard and
cleaning the board with isopropyl alcohol. Unplug before any liquid.

## 4. Hide it

Use colours with no green in them, and keep the arrow block blue:

    tools/g910-mask-presets.py

saves four such profiles (Midnight Blue, Purple Rain, Synthwave,
Crimson Blue) and restores your current colours. Load them from the
app's Profiles list. Midnight Blue hid every faulty key on the test
keyboard. Adjust the rule to your own three-colour test result.

A single key that is only slightly off can also be corrected by
right-clicking it in the app (per-key colour correction).

## 5. Keys typing by themselves after cleaning

Wet switches can register as pressed. `tools/g910-block-numpad.py`
blocks the numpad only, so the rest of the keyboard stays usable while
it dries. It is a stopgap: an unplugged keyboard dries safely, a
powered wet one does not.
