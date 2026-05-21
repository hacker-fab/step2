"""Hardware integration tests for GrblStage.

Requires a GRBL-flashed Arduino. Set GRBL_PORT env var to override default port.
Run: uv run pytest test -v
"""

import os
import time
import pytest
import serial

from step2.stage import GrblStage


PORT = os.environ.get("GRBL_PORT", "/dev/tty.usbmodem11101")
BAUD = 115200


@pytest.fixture(scope="session")
def stage():
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
    except (serial.SerialException, FileNotFoundError):
        pytest.skip(f"No GRBL device at {PORT}")

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
