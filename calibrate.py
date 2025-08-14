"""Pelco‑D rotor initial configuration & speed calibration tool.

Guides you through setting up the serial connection and measuring degrees‑per‑second
for azimuth and elevation. Supports interactive and CLI‑driven operation and prints
the results that were saved to the runtime config via RotorState.

Usage examples:
  python calibrate.py --list-ports
  python calibrate.py --port COM4 --baud 2400 --duration-az 10 --duration-el 10
  python calibrate.py                 # fully interactive wizard

Notes:
- Uses pelco_commands.init_serial() to open the serial port.
- Delegates measurement prompts to pelco_commands.test_azimuth_speed/test_elevation_speed
  so the saved keys are consistent: AZIMUTH_SPEED_DPS, ELEVATION_SPEED_DPS.
- Optionally runs a post-calibration (set to AZ=0, EL=90) with --post-calibrate.
"""

from __future__ import annotations

import argparse
import logging
from typing import Optional

# Optional dependency: pyserial (only needed for --list-ports convenience)
try:
    from serial.tools import list_ports as _LIST_PORTS  # type: ignore
except ImportError:  # pyserial not installed; --list-ports will be a no-op
    _LIST_PORTS = None  # type: ignore[assignment]

from pelco_commands import (
    init_serial,
    test_azimuth_speed,
    test_elevation_speed,
    calibrate,
)
from state import RotorState


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("calibrate")


def discover_ports() -> list[str]:
    """Return a list of likely serial port names (best effort).

    If pyserial is not installed, returns an empty list.
    """
    ports: list[str] = []
    if _LIST_PORTS is not None:
        try:
            ports = [p.device for p in _LIST_PORTS.comports()]  # type: ignore[attr-defined]
        except (OSError, AttributeError, ValueError) as err:
            log.warning("Could not enumerate serial ports: %s", err)
    return ports


def pick_port_interactive() -> Optional[str]:
    """Offer a simple picker for available ports; fallback to raw input."""
    ports = discover_ports()
    if ports:
        log.info("Found %d serial ports:", len(ports))
        for i, p in enumerate(ports, 1):
            log.info("  %d) %s", i, p)
        choice = input(
            "Select port by number (or press Enter to type manually): "
        ).strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(ports):
                return ports[idx - 1]
        # fall through to manual entry
    return input("Enter serial port (e.g., COM4 or /dev/ttyUSB0): ").strip() or None


def open_serial(port: Optional[str], baud: int) -> bool:
    """Initialize the serial connection via pelco_commands.init_serial.

    Returns True on success, False otherwise.
    """
    if not port:
        log.error("No serial port provided.")
        return False
    try:
        init_serial(port, baud)
        log.info("Serial port %s initialized at %d baud.", port, baud)
        return True
    except (OSError, ValueError) as err:
        log.error("Failed to open serial port %s @ %d: %s", port, baud, err)
        return False


def print_current_config() -> None:
    """Log the currently saved speeds from RotorState."""
    az = RotorState.get_config("AZIMUTH_SPEED_DPS")
    el = RotorState.get_config("ELEVATION_SPEED_DPS")
    log.info("Current speeds -> AZ: %s°/s, EL: %s°/s", az, el)


def run_speed_tests(dur_az: int, dur_el: int, skip_az: bool, skip_el: bool) -> None:
    """Run the interactive speed tests (delegates to pelco_commands).

    The called functions will prompt you to enter measured degrees moved, then persist
    speeds to the config via RotorState.
    """
    if not skip_az:
        log.info("--- Step 1: Azimuth speed test (%ds) ---", dur_az)
        test_azimuth_speed(dur_az)
    else:
        log.info("(Skipping azimuth speed test)")

    if not skip_el:
        log.info("--- Step 2: Elevation speed test (%ds) ---", dur_el)
        test_elevation_speed(dur_el)
    else:
        log.info("(Skipping elevation speed test)")


def sanity_hints() -> None:
    """Print helpful geometry/configuration reminders after calibration."""
    log.info("Sanity checks:")
    log.info("  • Verify limits.json matches your geometry (EL 45–135 with 90° neutral).")
    log.info(
        "  • If EL ‘sticks’ at 90°, ensure pelco_commands clamps use limits.json values."
    )
    log.info("  • Use the web UI ‘Reset Position’ if needed before/after tests.")


def main() -> None:
    """CLI entry point for serial setup and speed calibration."""
    parser = argparse.ArgumentParser(
        description=(
            "Pelco-D rotor initial configuration & speed calibration"
        )
    )
    parser.add_argument(
        "--port",
        help="Serial port (e.g., COM4 or /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=2400,
        help="Baud rate (default: 2400)",
    )
    parser.add_argument(
        "--duration-az",
        type=int,
        default=10,
        help="Azimuth test duration in seconds (default: 10)",
    )
    parser.add_argument(
        "--duration-el",
        type=int,
        default=10,
        help="Elevation test duration in seconds (default: 10)",
    )
    parser.add_argument(
        "--skip-az",
        action="store_true",
        help="Skip azimuth speed test",
    )
    parser.add_argument(
        "--skip-el",
        action="store_true",
        help="Skip elevation speed test",
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="List available serial ports and exit",
    )
    parser.add_argument(
        "--post-calibrate",
        action="store_true",
        help=(
            "Run full calibrate() after saving speeds (moves to AZ=0°, EL=90°)."
        ),
    )

    args = parser.parse_args()

    if args.list_ports:
        ports = discover_ports()
        if not ports:
            log.info("No serial ports found.")
        else:
            log.info("Available ports:\n  %s", "\n  ".join(ports))
        return

    port = args.port or pick_port_interactive()
    if not open_serial(port, args.baud):
        return

    print_current_config()
    run_speed_tests(args.duration_az, args.duration_el, args.skip_az, args.skip_el)

    # Show results saved by pelco_commands tests
    az = RotorState.get_config("AZIMUTH_SPEED_DPS")
    el = RotorState.get_config("ELEVATION_SPEED_DPS")
    log.info("Saved speeds -> AZ: %s°/s, EL: %s°/s", az, el)

    if args.post_calibrate:
        log.info("Running post-calibration: moving to AZ=0°, EL=90°…")
        calibrate()

    sanity_hints()
    log.info("✓ Configuration complete. You can now use the web UI or EasyComm server.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
