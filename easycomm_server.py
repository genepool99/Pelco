import socket
import threading
from state import get_position
from pelco_commands import send_command

HOST = '0.0.0.0'
PORT = 4533  # Default port used by Gpredict

def handle_client(conn, addr):
    print(f"[Gpredict] Connected: {addr}")
    try:
        with conn:
            buffer = ""
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                buffer += data.decode()
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    cmd = line.strip()
                    print(f"[Gpredict] Received: {cmd}")

                    parts = cmd.split()
                    if not parts:
                        continue

                    # Hamlib style: 'P 153.4 21.6' = Set position
                    if parts[0].upper() == "P" and len(parts) == 3:
                        try:
                            az = float(parts[1])
                            el = float(parts[2])
                            send_command(az, el)
                        except ValueError:
                            print("[WARN] Invalid numeric values")

                    # Hamlib style: 'p' = get position
                    elif parts[0] == "p":
                        az, el = get_position()
                        conn.sendall(f"{az:.2f} {el:.2f}\n".encode())

                    # EasyComm style: 'AZEL 153.4 21.6'
                    elif parts[0].upper() == "AZEL" and len(parts) == 3:
                        try:
                            az = float(parts[1])
                            el = float(parts[2])
                            send_command(az, el)
                        except ValueError:
                            print("[WARN] Invalid AZEL values")

                    else:
                        print("[DEBUG] Unhandled command:", cmd)

    except Exception as e:
        print(f"[Gpredict] Connection error: {e}")


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"[Gpredict] EasyComm server listening on {HOST}:{PORT}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
