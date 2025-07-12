"""TCP server for Gpredict control using EasyComm and Hamlib-style commands.

This module listens for connections from satellite tracking software such as
Gpredict and processes incoming commands to control a Pelco-D rotor.
"""

import socket
import threading
import logging
from state import get_position
from pelco_commands import send_command

HOST = '0.0.0.0'
PORT = 4533  # Default port used by Gpredict

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)


def handle_client(conn, addr):
    """Handle a single client connection and process rotor commands."""
    logging.info("[Gpredict] Connected: %s", addr)
    try:
        with conn:
            buffer = ""
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                try:
                    buffer += data.decode()
                except UnicodeDecodeError:
                    logging.warning("[Gpredict] Received undecodable data")
                    continue

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    cmd = line.strip()
                    logging.debug("[Gpredict] Received: %s", cmd)

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
                            logging.warning("[Gpredict] Invalid numeric values")

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
                            logging.warning("[Gpredict] Invalid AZEL values")

                    else:
                        logging.debug("[Gpredict] Unhandled command: %s", cmd)

    except (ConnectionError, OSError) as e:
        logging.error("[Gpredict] Connection error: %s", e)


def start_server(host='0.0.0.0', port=4533, update_callback=None):
    """Start the EasyComm-compatible TCP server for Gpredict."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(1)
    logging.info("[Gpredict] EasyComm server listening on %s:%d", HOST, PORT)
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
