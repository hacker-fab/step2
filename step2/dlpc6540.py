from __future__ import annotations

import argparse
import sys

try:
    import usb.core
    import usb.util
except ImportError:
    sys.exit("pip install pyusb")

TI_VID = 0x0451  # Texas Instruments

DEST_COMMON = 1
DEST_SYSTEM = 4

HDR_READ = 1 << 7
HDR_BUSY = 1 << 7  # I2C only; should always be 0 on USB
HDR_ERROR = 1 << 6
HDR_DEST_MASK = 0x07

OP_MODE = 0x00  # dest 1 -> 1 data byte
OP_CONTROLLER_INFO = 0x00  # dest 4 -> 13 data bytes


class DLPC:
    """Wraps a claimed Interface 0 with its bulk OUT/IN endpoints."""

    INTERFACE = 0  # Projector Control per §15.3

    def __init__(self, dev: usb.core.Device, timeout_ms: int = 1000):
        self.dev = dev
        self.timeout_ms = timeout_ms
        self._reattach = False

        # Linux: kernel may have grabbed the device with a generic driver.
        # We need raw access, so detach if necessary.
        try:
            if dev.is_kernel_driver_active(self.INTERFACE):
                dev.detach_kernel_driver(self.INTERFACE)
                self._reattach = True
        except (NotImplementedError, usb.core.USBError):
            pass  # Windows / no driver attached

        dev.set_configuration()
        cfg = dev.get_active_configuration()
        intf = cfg[(self.INTERFACE, 0)]

        self.ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(e.bmAttributes)
                == usb.util.ENDPOINT_TYPE_BULK
            ),
        )
        self.ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
                and usb.util.endpoint_type(e.bmAttributes)
                == usb.util.ENDPOINT_TYPE_BULK
            ),
        )
        if self.ep_out is None or self.ep_in is None:
            raise IOError("Did not find bulk OUT and IN endpoints on interface 0")

    def close(self) -> None:
        usb.util.dispose_resources(self.dev)
        if self._reattach:
            try:
                self.dev.attach_kernel_driver(self.INTERFACE)
            except usb.core.USBError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def send_read_command(
        self, destination: int, opcode: int, response_len: int
    ) -> bytes:
        """Issue a read-style command, return data bytes (response header stripped)."""
        header = HDR_READ | (destination & HDR_DEST_MASK)
        self.ep_out.write(bytes([header, opcode]), timeout=self.timeout_ms)

        # USB bulk reads return whatever the device sent in one transfer.
        # Ask for response_len + 1 (header) but tolerate up to one packet.
        wanted = response_len + 1
        resp = bytes(self.ep_in.read(max(wanted, 64), timeout=self.timeout_ms))

        if len(resp) < 1:
            raise IOError("Empty response from controller")

        resp_header = resp[0]
        if resp_header & HDR_ERROR:
            err_code = resp[1] if len(resp) > 1 else 0xFF
            raise RuntimeError(
                f"Controller returned error code {err_code} (see Table 16-5 in DLPU110B). Header = 0x{resp_header:02X}"
            )
        if resp_header & HDR_BUSY:
            # Shouldn't happen on USB per §16.5.2, but flag it if it does.
            raise RuntimeError(
                f"BUSY bit set on USB response (header 0x{resp_header:02X}). Unexpected — protocol says USB uses NAK for busy."
            )

        return resp[1:wanted]


def find_devices(vid: int, pid: int | None) -> list[usb.core.Device]:
    """Return all USB devices matching the given VID (and PID if specified)."""
    kw = {"idVendor": vid}
    if pid is not None:
        kw["idProduct"] = pid
    return list(usb.core.find(find_all=True, **kw))


def decode_controller_info(data: bytes) -> tuple[int, str]:
    """Table 19-5: bytes 0-3 = Controller ID (LE), bytes 4-12 = Name."""
    if len(data) < 13:
        raise ValueError(f"expected 13 bytes, got {len(data)}: {data.hex()}")
    controller_id = int.from_bytes(data[0:4], "little")
    name = data[4:13].rstrip(b"\x00").decode("ascii", errors="replace")
    return controller_id, name


def decode_mode(data: bytes) -> str:
    """Table 19-4: bit 0 = app mode (0 bootloader / 1 main), bit 1 = single/multi."""
    if not data:
        raise ValueError("empty response")
    b = data[0]
    app = "Main Application" if b & 0x01 else "Bootloader"
    cfg = "Multiple controllers" if b & 0x02 else "Single controller"
    return f"{app}, {cfg}"
