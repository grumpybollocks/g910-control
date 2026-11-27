#!/bin/sh
# Lights the whole keyboard in one pure colour so faulty LEDs stand out.
# usage: g910-led-test.sh red|green|blue|white|off
case "$1" in
  red) c=ff0000 ;; green) c=00ff00 ;; blue) c=0000ff ;; white) c=ffffff ;; off) c=000000 ;;
  *) echo "usage: $0 red|green|blue|white|off"; exit 1 ;;
esac
for h in /sys/class/hidraw/hidraw*; do
  grep -qi "HID_ID=0003:0000046D:0000C335" "$h/device/uevent" || continue
  d=/dev/${h##*/}
  keyledsctl set-leds -d "$d" "all=$c" 2>/dev/null || continue
  keyledsctl set-leds -d "$d" -b gkeys "all=$c"
  keyledsctl set-leds -d "$d" -b logo "all=$c"
  echo "keyboard set to $1"; exit 0
done
echo "No G910 found."; exit 1
