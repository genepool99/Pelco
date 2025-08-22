# pelco_query_test.py
import time
import serial

ADDR = 0x01  # change if your head uses a different Pelco address
PORT = "/dev/ttyUSB0"  # or "COM4"
BAUD = 2400            # typical for Pelco-D

def frame(addr, c1, c2, d1, d2):
    ck = (addr + c1 + c2 + d1 + d2) & 0xFF
    return bytes([0xFF, addr, c1, c2, d1, d2, ck])

Q_PAN  = frame(ADDR, 0x00, 0x51, 0x00, 0x00)  # expect 0x59 response
Q_TILT = frame(ADDR, 0x00, 0x53, 0x00, 0x00)  # expect 0x5B response

def read_packet(ser, expect_c2, timeout=0.35):
    deadline = time.time() + timeout
    buf = bytearray()
    while time.time() < deadline:
        if ser.in_waiting:
            buf += ser.read(ser.in_waiting)
            # scan for 7-byte Pelco-D packet starting with 0xFF
            for i in range(0, max(0, len(buf) - 6)):
                if buf[i] == 0xFF:
                    pkt = buf[i:i+7]
                    if len(pkt) == 7 and pkt[3] == expect_c2:
                        # verify checksum
                        if ((pkt[1]+pkt[2]+pkt[3]+pkt[4]+pkt[5]) & 0xFF) == pkt[6]:
                            return bytes(pkt)
        time.sleep(0.005)
    return None

with serial.Serial(PORT, BAUD, timeout=0.05) as ser:
    ser.reset_input_buffer()

    # Query PAN
    ser.write(Q_PAN)
    ser.flush()
    pkt = read_packet(ser, 0x59)
    if pkt:
        pan_val = (pkt[4] << 8) | pkt[5]
        pan_deg = pan_val / 100.0  # many devices: hundredths of a degree
        print(f"Pan response: raw={pan_val} -> {pan_deg:.2f}°")
    else:
        print("No pan response (device may not support query or RS-485 wiring/turnaround issue).")

    time.sleep(0.05)

    # Query TILT
    ser.write(Q_TILT)
    ser.flush()
    pkt = read_packet(ser, 0x5B)
    if pkt:
        tilt_val = (pkt[4] << 8) | pkt[5]
        tilt_deg = tilt_val / 100.0
        print(f"Tilt response: raw={tilt_val} -> {tilt_deg:.2f}°")
    else:
        print("No tilt response.")
