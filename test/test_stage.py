"""
Identifies the GRBL board by USB VID/PID + serial number,
Override the detected port manually with:
    GRBL_PORT=/dev/tty.usbmodemXXXX uv run pytest test -v

Run: uv run pytest test -v
"""

import os
import time

import pytest
import serial
import serial.tools.list_ports

from step2.stage import GrblStage

# Bench Arduino Uno running GRBL. Update if the board changes.
GRBL_VID = 0x2341
GRBL_PID = 0x0001
GRBL_SERIAL = "9563231343435130D011"
BAUD = 115200


def find_grbl_port() -> str | None:
    """Return the device path of the bench GRBL board, or None if absent."""
    for p in serial.tools.list_ports.comports():
        if (p.vid, p.pid) == (GRBL_VID, GRBL_PID) and p.serial_number == GRBL_SERIAL:
            return p.device
    return None


@pytest.fixture(scope="module")
def stage():
    port = os.environ.get("GRBL_PORT") or find_grbl_port()
    if port is None:
        pytest.skip(
            f"GRBL board not found "
            f"(VID 0x{GRBL_VID:04X} PID 0x{GRBL_PID:04X} SN {GRBL_SERIAL})"
        )
    try:
        ser = serial.Serial(port, BAUD, timeout=1)
    except (serial.SerialException, FileNotFoundError):
        pytest.skip(f"Found GRBL at {port} but couldn't open it")

    with ser:
        s = GrblStage(
            controller_target=ser,
            enable_homing=False,
            enable_tiling=False,
            autofocus_offset=0,
        )
        time.sleep(1.0)
        yield s


SEQ = [
    # square
    {"x": 2000, "y": 0},
    {"x": 0, "y": 2000},
    {"x": -2000, "y": 0},
    {"x": 0, "y": -2000},
    # diagonal X's
    {"x": 1500, "y": 1500},
    {"x": -1500, "y": -1500},
    {"x": 1500, "y": -1500},
    {"x": -1500, "y": 1500},
    # z bob
    {"z": 500},
    {"z": -500},
    {"z": 500},
    {"z": -500},
    # spiral-out
    {"x": 1000, "y": 0},
    {"x": 0, "y": 1000},
    {"x": -1500, "y": 0},
    {"x": 0, "y": -1500},
    {"x": 2000, "y": 0},
    {"x": 0, "y": 2000},
    {"x": -2000, "y": -2000},
]


@pytest.mark.stage
@pytest.mark.parametrize("move", SEQ)
def test_relative_move(stage, move):
    stage.move_relative(move)
    stage.wait_for_idle()
