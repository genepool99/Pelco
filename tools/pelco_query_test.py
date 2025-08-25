#!/usr/bin/env python3
"""
pelco_query.py — Minimal Pelco‑D PAN/TILT query tool.

TL;DR: Use this script to check if you have one of those fancy rotators. If so,
send it to me. 

This script sends the standard Pelco‑D query commands for PAN (0x51) and TILT (0x53)
to a head at a given Pelco address and parses the expected replies (0x59, 0x5B).
Many heads report angles as hundredths of a degree; we convert those to degrees.

Typical use cases:
- Smoke test RS‑485 wiring and Pelco‑D comms.
- Read the current azimuth/elevation reported by a Pelco‑D pan/tilt head.

Requirements:
    pip install pyserial

Examples:
    # Linux/Unix
    python3 pelco_query.py --port /dev/ttyUSB0 --baud 2400

    # Windows
    python3 pelco_query.py --port COM4 --baud 2400

    # Custom device address and extra verbosity
    python3 pelco_query.py -p /dev/ttyUSB0 -b 2400 --addr 1 --verbose
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import serial  # pyserial


def build_frame(addr: int, c1: int, c2: int, d1: int, d2: int) -> bytes:
    """
    Build a 7‑byte Pelco‑D frame:
        0xFF, addr, c1, c2, d1, d2, checksum
    where checksum = (addr + c1 + c2 + d1 + d2) & 0xFF
    """
    for name, val in {"addr": addr, "c1": c1, "c2": c2, "d1": d1, "d2": d2}.items():
        if not 0 <= val <= 0xFF:
            raise ValueError(f"{name} out of byte range: {val}")
    ck = (addr + c1 + c2 + d1 + d2) & 0xFF
    return bytes([0xFF, addr, c1, c2, d1, d2, ck])


def verify_checksum(pkt: bytes) -> bool:
    """Return True if pkt is a 7‑byte Pelco‑D frame with a valid checksum."""
    if len(pkt) != 7 or pkt[0] != 0xFF:
        return False
    calc = (pkt[1] + pkt[2] + pkt[3] + pkt[4] + pkt[5]) & 0xFF
    return calc == pkt[6]


def read_packet(
    ser: serial.Serial,
    expect_c2: int,
    timeout: float = 0.35,
    *,
    verbose: bool = False,
) -> Optional[bytes]:
    """
    Read from the serial buffer until we find a valid 7‑byte Pelco‑D frame
    whose C2 byte matches `expect_c2`, or until `timeout` elapses.

    Returns the bytes if found, otherwise None.
    """
    deadline = time.time() + timeout
    buf = bytearray()

    while time.time() < deadline:
        if ser.in_waiting:
            buf += ser.read(ser.in_waiting)

            # Scan for possible frames aligned on 0xFF
            i = 0
            while i <= max(0, len(buf) - 7):
                if buf[i] == 0xFF:
                    candidate = buf[i : i + 7]
                    if len(candidate) == 7 and verify_checksum(candidate):
                        if candidate[3] == expect_c2:
                            if verbose:
                                print(f"[dbg] matched frame: {candidate.hex(' ')}")
                            return bytes(candidate)
                        else:
                            if verbose:
                                print(
                                    f"[dbg] frame with unexpected C2=0x{candidate[3]:02X}: "
                                    f"{candidate.hex(' ')}"
                                )
                    # Regardless, advance one byte (could be noise or wrong reply)
                    i += 1
                else:
                    i += 1
        time.sleep(0.005)

    return None


def hundredths_to_deg(high: int, low: int) -> float:
    """
    Interpret two data bytes as a 16‑bit unsigned integer representing
    hundredths of a degree, then convert to degrees.
    """
    raw = (high << 8) | low
    return raw / 100.0


def query_once(
    ser: serial.Serial,
    addr: int,
    *,
    do_pan: bool = True,
    do_tilt: bool = True,
    timeout: float = 0.35,
    delay_between: float = 0.05,
    verbose: bool = False,
) -> int:
    """
    Perform one PAN and/or TILT query cycle.
    Returns an exit code: 0 on success, non‑zero on partial/total failure.
    """
    exit_code = 0

    if do_pan:
        q_pan = build_frame(addr, 0x00, 0x51, 0x00, 0x00)  # expect C2=0x59
        if verbose:
            print(f"[dbg] -> PAN query: {q_pan.hex(' ')}")
        ser.write(q_pan)
        ser.flush()
        pkt = read_packet(ser, expect_c2=0x59, timeout=timeout, verbose=verbose)
        if pkt:
            pan_deg = hundredths_to_deg(pkt[4], pkt[5])
            print(f"Pan response: raw={(pkt[4] << 8) | pkt[5]} -> {pan_deg:.2f}°")
        else:
            print(
                "No pan response (device may not support query or RS‑485 wiring/turnaround issue)."
            )
            exit_code = 2

    if do_pan and do_tilt:
        time.sleep(delay_between)

    if do_tilt:
        q_tilt = build_frame(addr, 0x00, 0x53, 0x00, 0x00)  # expect C2=0x5B
        if verbose:
            print(f"[dbg] -> TILT query: {q_tilt.hex(' ')}")
        ser.write(q_tilt)
        ser.flush()
        pkt = read_packet(ser, expect_c2=0x5B, timeout=timeout, verbose=verbose)
        if pkt:
            tilt_deg = hundredths_to_deg(pkt[4], pkt[5])
            print(f"Tilt response: raw={(pkt[4] << 8) | pkt[5]} -> {tilt_deg:.2f}°")
        else:
            print("No tilt response.")
            exit_code = max(exit_code, 2)

    return exit_code


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments for pelco_query.py and return a Namespace."""
    p = argparse.ArgumentParser(
        description=(
            "Query a Pelco‑D head for PAN/TILT positions.\n"
            "Sends PAN(0x51)/TILT(0x53) queries and expects 0x59/0x5B replies."
        )
    )
    p.add_argument(
        "-p",
        "--port",
        required=True,
        help='Serial port (e.g. "/dev/ttyUSB0" or "COM4")',
    )
    p.add_argument(
        "-b",
        "--baud",
        type=int,
        default=2400,
        help="Baud rate (default: 2400)",
    )
    p.add_argument(
        "--addr",
        type=int,
        default=0x01,
        help="Pelco device address (0–255, default: 1)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=0.35,
        help="Read timeout in seconds for each reply (default: 0.35)",
    )
    p.add_argument(
        "--delay-between",
        type=float,
        default=0.05,
        help="Delay between PAN and TILT queries (default: 0.05)",
    )
    p.add_argument(
        "--pan-only",
        action="store_true",
        help="Only send PAN query (skip TILT).",
    )
    p.add_argument(
        "--tilt-only",
        action="store_true",
        help="Only send TILT query (skip PAN).",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show debug frames and parsing details.",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    """Entry point: parse args, open serial port, run queries, and return exit code."""
    args = parse_args(argv)

    if not 0 <= args.addr <= 0xFF:
        print("Error: --addr must be 0–255", file=sys.stderr)
        return 2

    # Determine which queries to run
    do_pan = not args.tilt_only
    do_tilt = not args.pan_only

    if not (do_pan or do_tilt):
        print("Error: nothing to do (both PAN and TILT disabled).", file=sys.stderr)
        return 2

    # Open serial port and run queries
    try:
        with serial.Serial(args.port, args.baud, timeout=0.05) as ser:
            # Clear stale bytes
            ser.reset_input_buffer()
            return query_once(
                ser,
                addr=args.addr,
                do_pan=do_pan,
                do_tilt=do_tilt,
                timeout=args.timeout,
                delay_between=args.delay_between,
                verbose=args.verbose,
            )
    except serial.SerialException as e:
        print(f"Serial error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
