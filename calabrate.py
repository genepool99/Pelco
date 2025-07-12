"""Pelco-D rotor calibration tool.

This script helps determine the degrees-per-second speed of a Pelco-D compatible
antenna rotator by running timed azimuth and elevation tests.
"""

import logging
from pelco_commands import init_serial, test_azimuth_speed, test_elevation_speed

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def prompt_serial():
    """Prompt the user for serial port info and initialize the connection."""
    logger.info("=== PELCO-D ROTOR CALIBRATION ===")
    port = input("Enter serial port (e.g., COM4): ").strip()
    baud = input("Enter baud rate (default 2400): ").strip()
    baudrate = int(baud) if baud else 2400

    try:
        init_serial(port, baudrate)
        logger.info("Serial port %s initialized at %d baud.", port, baudrate)
        return True
    except OSError as e:
        logger.error("Failed to open serial port: %s", e)
        return False


def main():
    """Run azimuth and elevation calibration steps."""
    if not prompt_serial():
        return

    logger.info("--- Step 1: Azimuth Calibration ---")
    test_azimuth_speed(10)

    logger.info("--- Step 2: Elevation Calibration ---")
    test_elevation_speed(10)

    logger.info("✓ Calibration complete! Saved to config.json")


if __name__ == "__main__":
    main()
