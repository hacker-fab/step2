"""
Tests for step2.dlpc6540.

Hardware tests skip if no DLPC6540 is on the USB bus.

Override discovery via env vars:
    DLPC_VID=0x0451 DLPC_PID=0x6128 DLPC_TIMEOUT_MS=2000 pytest
"""

from __future__ import annotations

import os
import time

import pytest

from step2.dlpc6540 import (
    DEST_COMMON,
    DEST_SYSTEM,
    DLPC,
    OP_CONTROLLER_INFO,
    OP_MODE,
    TI_VID,
    decode_controller_info,
    decode_mode,
    find_devices,
)


@pytest.fixture(scope="session")
def dlpc():
    """Open the connected DLPC6540 once for the whole test session."""
    vid = int(os.environ.get("DLPC_VID", str(TI_VID)), 0)
    pid_env = os.environ.get("DLPC_PID")
    pid = int(pid_env, 0) if pid_env else None
    timeout = int(os.environ.get("DLPC_TIMEOUT_MS", "1000"))

    devices = find_devices(vid, pid)
    if not devices:
        pytest.skip(f"No DLPC6540 on USB (VID 0x{vid:04X})")
    if len(devices) > 1:
        pytest.skip("Multiple matching devices; set DLPC_PID to disambiguate")

    with DLPC(devices[0], timeout_ms=timeout) as d:
        yield d


class TestDecodeControllerInfo:
    def test_id_is_little_endian(self):
        # Per Table 19-5: bytes 0-3 = Controller ID, LSB first.
        raw = bytes([0x40, 0x65, 0xDC, 0x01]) + b"DLPC6540\x00"
        cid, _ = decode_controller_info(raw)
        assert cid == 0x01DC6540

    def test_name_strips_trailing_nulls(self):
        raw = bytes(4) + b"FOO\x00\x00\x00\x00\x00\x00"
        _, name = decode_controller_info(raw)
        assert name == "FOO"

    def test_name_keeps_full_9_chars_when_no_padding(self):
        raw = bytes(4) + b"DLPC6540A"
        _, name = decode_controller_info(raw)
        assert name == "DLPC6540A"

    def test_rejects_short_response(self):
        with pytest.raises(ValueError):
            decode_controller_info(b"\x00" * 5)


class TestDecodeMode:
    @pytest.mark.parametrize(
        "byte, expected_app, expected_cfg",
        [
            (0x00, "Bootloader", "Single"),
            (0x01, "Main Application", "Single"),
            (0x02, "Bootloader", "Multiple"),
            (0x03, "Main Application", "Multiple"),
        ],
    )
    def test_known_modes(self, byte, expected_app, expected_cfg):
        result = decode_mode(bytes([byte]))
        assert expected_app in result
        assert expected_cfg in result

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            decode_mode(b"")


@pytest.mark.dlpc6540
class TestHardware:
    def test_controller_info_returns_valid_data(self, dlpc):
        data = dlpc.send_read_command(DEST_SYSTEM, OP_CONTROLLER_INFO, 13)
        assert len(data) == 13
        cid, name = decode_controller_info(data)
        assert cid != 0, "Controller ID should be nonzero"
        assert name, "Name field is empty"
        assert name.isprintable(), f"Name {name!r} is not printable ASCII"

    def test_mode_query_succeeds(self, dlpc):
        data = dlpc.send_read_command(DEST_COMMON, OP_MODE, 1)
        assert len(data) == 1
        decode_mode(data)  # raises on bad data

    def test_repeated_query_is_stable(self, dlpc):
        """Same query twice should yield identical bytes — checks bus state."""
        first = dlpc.send_read_command(DEST_SYSTEM, OP_CONTROLLER_INFO, 13)
        second = dlpc.send_read_command(DEST_SYSTEM, OP_CONTROLLER_INFO, 13)
        assert first == second

    def test_fetch_led_current(self, dlpc):
        """Fetch LED current levels and verify they are within valid range."""
        red, green, blue = dlpc.get_led_current()
        assert 0 <= red <= 32
        assert 0 <= green <= 32
        assert 0 <= blue <= 32

    def test_get_illumination_enable(self, dlpc):
        """Fetch illumination enable state and verify it is within valid range."""
        enable = dlpc.get_illumination_enable()
        print(bin(enable))
        assert 0 <= enable <= 7

    def test_cycle_leds_illumination(self, dlpc):
        """Cycle through r/g/b leds"""
        for en in range(0, 8):
            dlpc.set_illumination_enable(en)
            check_en = dlpc.get_illumination_enable()
            assert check_en == en
            time.sleep(0.1)

    def test_slowly_ramp_leds(self, dlpc):
        """Slowly ramp up/down LED current levels."""
        for drv_lev in range(150, 800):
            dlpc.set_led_drive_level(drv_lev, drv_lev, drv_lev)
            red, green, blue = dlpc.get_led_drive_level()
            print(red, green, blue)
            assert red == drv_lev
            assert green == drv_lev
            assert blue == drv_lev
