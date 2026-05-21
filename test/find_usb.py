#!/usr/bin/env python3
"""
Find USB serial devices and their identifying info.

Lists all attached serial ports with their VID/PID/serial number, then
watches for plug/unplug events so you can see what just changed.

Usage:
    python3 find_usb.py            # list now, then watch
    python3 find_usb.py --once     # list and exit (no watch loop)
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    from serial.tools import list_ports
except ImportError:
    sys.exit("pip install pyserial")


def fmt_port(p) -> str:
    vid = f"{p.vid:04X}" if p.vid is not None else "----"
    pid = f"{p.pid:04X}" if p.pid is not None else "----"
    sn = p.serial_number or "-"
    desc = p.product or p.description or "-"
    mfr = p.manufacturer or "-"
    return f"  {p.device:<28} VID:PID {vid}:{pid}  SN: {sn:<24} {mfr} / {desc}"


def snapshot() -> dict[str, object]:
    """Map device path -> ListPortInfo for currently attached ports."""
    return {p.device: p for p in list_ports.comports()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true", help="List ports and exit (don't watch)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Polling interval in seconds (default 0.5)",
    )
    args = parser.parse_args()

    current = snapshot()
    print(f"\n{len(current)} serial port(s) currently attached:")
    if not current:
        print("  (none)")
    for p in current.values():
        print(fmt_port(p))

    if args.once:
        return

    print("\nWatching for changes. Plug or unplug a device. Ctrl-C to quit.")
    try:
        while True:
            time.sleep(args.interval)
            new = snapshot()
            added = set(new) - set(current)
            removed = set(current) - set(new)
            for d in added:
                print("\n+ ATTACHED:")
                print(fmt_port(new[d]))
            for d in removed:
                print("\n- REMOVED:")
                print(fmt_port(current[d]))
            current = new
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
