from pelco_commands import init_serial, test_azimuth_speed, test_elevation_speed

def prompt_serial():
    print("=== PELCO-D ROTOR CALIBRATION ===")
    port = input("Enter serial port (e.g., COM4): ").strip()
    baud = input("Enter baud rate (default 2400): ").strip()
    baudrate = int(baud) if baud else 2400

    try:
        init_serial(port, baudrate)
        print(f"[INFO] Serial port {port} initialized at {baudrate} baud.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to open serial port: {e}")
        return False

def main():
    if not prompt_serial():
        return

    print("\n--- Step 1: Azimuth Calibration ---")
    test_azimuth_speed(10)

    print("\n--- Step 2: Elevation Calibration ---")
    test_elevation_speed(10)

    print("\n[✓] Calibration complete! Saved to config.json")

if __name__ == "__main__":
    main()
