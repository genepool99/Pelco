"""EasyComm TCP Server for Peltrack Rotor Control

Implements a TCP server to receive EasyComm commands (AZ/EL control)
and forward them to a Pelco-D antenna rotator.
"""

import socket
import threading
import logging
from typing import Optional, Tuple

from state import get_position
from pelco_commands import send_command, stop as pelco_stop


class EasyCommServer:
    """Threaded TCP server that accepts EasyComm II / simple Hamlib commands
    and updates rotor position.

    Protocols supported (basic):
      - EasyComm II set:  "AZ<deg> EL<deg>" (e.g., "AZ180.0 EL90.0")
      - Query current:    "GET"  -> responds "AZ<deg> EL<deg>\n"
      - Hamlib-like set:  "P <az> <el>" (e.g., "P 180.0 90.0")
      - Stop (optional):  "STOP" -> immediate stop (best-effort), responds "OK\n"

    Notes:
      * Each command should be terminated by a newline ("\n") or semicolon (';').
        Multiple commands per TCP packet are supported. Whitespace is ignored.
      * Motion commands are executed asynchronously and serialized with a lock
        so they don't overlap. We immediately reply "OK\n" to the client.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 4533, update_callback=None):
        self.host = host
        self.port = port
        self.update_callback = update_callback
        self._server_socket: Optional[socket.socket] = None
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        self._move_lock = threading.Lock()

    # ------------------ Parsing ------------------
    def _parse_easycomm_command(self, command: str) -> Optional[Tuple[float, float]]:
        """Parse EasyComm (AZxxx ELxxx) or Hamlib-like (P az el) commands.

        Returns (az, el) for set-position commands, otherwise None.
        """
        cmd = command.strip().upper()

        # EasyComm format: AZ<deg> EL<deg>
        if cmd.startswith("AZ") and "EL" in cmd:
            try:
                az_index = cmd.index("AZ") + 2
                el_index = cmd.index("EL")
                az_str = cmd[az_index:el_index].strip()
                el_str = cmd[el_index + 2 :].strip()
                az = float(az_str)
                el = float(el_str)
                return az, el
            except (ValueError, IndexError) as err:
                logging.warning(
                    "Failed to parse EasyComm command '%s': %s", command, err
                )
                return None

        # Hamlib-like format: P <az> <el>
        if cmd.startswith("P "):
            try:
                parts = cmd[1:].strip().split()
                if len(parts) >= 2:
                    az = float(parts[0])
                    el = float(parts[1])
                    return az, el
            except ValueError as err:
                logging.warning(
                    "Failed to parse Hamlib command '%s': %s", command, err
                )
                return None

        return None

    # ------------------ Networking ------------------
    def _sendline(self, sock: socket.socket, text: str) -> None:
        try:
            payload = text if text.endswith("\n") else text + "\n"
            sock.sendall(payload.encode("utf-8"))
        except OSError as err:
            logging.debug("Client send failed: %s", err)

    def _move_async(self, az: float, el: float) -> None:
        """Run motion under a lock so commands don't overlap."""
        try:
            with self._move_lock:
                send_command(az, el, update_callback=self.update_callback)
        except (RuntimeError, ValueError, OSError) as err:
            logging.exception("Motion error for AZ=%.1f EL=%.1f: %s", az, el, err)

    def _handle_client(self, client_socket: socket.socket) -> None:
        """Handle an individual TCP client (line/; terminated)."""
        with client_socket:
            client_socket.settimeout(60)  # idle timeout to avoid ghost clients
            buffer = ""
            while True:
                try:
                    data = client_socket.recv(1024)
                    if not data:
                        break
                    try:
                        chunk = data.decode("utf-8")
                    except UnicodeDecodeError:
                        self._sendline(client_socket, "ERR")
                        continue

                    # Normalize separators: treat ';' as end-of-command as well
                    buffer += chunk.replace("\r", "\n").replace(";", "\n")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        cmd_u = line.upper()
                        logging.info("EasyComm: '%s'", line)

                        if cmd_u == "GET":
                            az, el = get_position()
                            self._sendline(client_socket, f"AZ{az:.1f} EL{el:.1f}")
                            continue

                        if cmd_u == "STOP":
                            try:
                                pelco_stop()
                                self._sendline(client_socket, "OK")
                            except (OSError, RuntimeError, ValueError) as err:
                                logging.warning("Stop failed: %s", err)
                                self._sendline(client_socket, "ERR")
                            continue

                        result = self._parse_easycomm_command(line)
                        if result is not None:
                            az, el = result
                            # run motion asynchronously but serialized
                            threading.Thread(
                                target=self._move_async,
                                args=(az, el),
                                daemon=True,
                            ).start()
                            self._sendline(client_socket, "OK")
                        else:
                            self._sendline(client_socket, "ERR")

                except socket.timeout:
                    logging.info("Client timed out; closing connection")
                    break
                except (ConnectionResetError, OSError) as err:
                    logging.warning("Socket error: %s", err)
                    break

    def _run(self) -> None:
        """Main server loop."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(5)
        except OSError as err:
            logging.error(
                "Failed to start EasyComm server on %s:%d: %s",
                self.host,
                self.port,
                err,
            )
            return

        self._running = True
        logging.info("EasyComm TCP server running on %s:%d", self.host, self.port)

        while self._running:
            try:
                client, addr = self._server_socket.accept()
                logging.info("Client connected from %s", addr)
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client,),
                    daemon=True,
                )
                thread.start()
            except OSError as err:
                if self._running:
                    logging.warning("Socket error in server loop: %s", err)
                break

    def start(self) -> None:
        """Start the server thread."""
        if self._server_thread and self._server_thread.is_alive():
            logging.info("EasyComm server already running.")
            return
        self._server_thread = threading.Thread(target=self._run, daemon=True)
        self._server_thread.start()

    def stop(self) -> None:
        """Stop the server and close the socket."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._server_socket.close()
            except OSError:
                pass
        logging.info("EasyComm server stopped.")


class EasyCommServerManager:
    """Manages a singleton instance of EasyCommServer."""
    _instance: Optional[EasyCommServer] = None

    @classmethod
    def start(cls, update_callback=None) -> None:
        """Start the EasyComm server in a background thread."""
        if not isinstance(cls._instance, EasyCommServer):
            cls._instance = EasyCommServer(update_callback=update_callback)
        cls._instance.start()

    @classmethod
    def stop(cls) -> None:
        """Stop the EasyComm server if it is running."""
        if isinstance(cls._instance, EasyCommServer):
            cls._instance.stop()
            cls._instance = None

    @classmethod
    def get_instance(cls) -> Optional[EasyCommServer]:
        """Get the singleton instance of EasyCommServer."""
        return cls._instance
