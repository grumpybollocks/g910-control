#!/usr/bin/env python3
# Own HID++ writer (g810-led style frames), no keyleds involved.
# usage: rawset.py /dev/hidrawN RRGGBB id [id ...]
import os, sys, time
dev, col, ids = sys.argv[1], bytes.fromhex(sys.argv[2]), [int(x, 16) for x in sys.argv[3:]]
fd = os.open(dev, os.O_RDWR)
for i in range(0, len(ids), 14):
    chunk = ids[i:i + 14]
    body = b"".join(bytes([k]) + col for k in chunk)
    frame = bytes([0x12, 0xff, 0x0f, 0x3d, 0x00, 0x01, 0x00, len(chunk)]) + body
    os.write(fd, frame.ljust(64, b"\0")); time.sleep(0.02)
os.write(fd, bytes([0x11, 0xff, 0x0f, 0x5d]).ljust(20, b"\0"))   # commit
os.close(fd)
