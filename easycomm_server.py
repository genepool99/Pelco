
"""EasyComm TCP Server for Peltrack Rotor Control

Implements a TCP server to receive EasyComm commands (AZ/EL control)
and forward them to a Pelco-D antenna rotator.
"""

import socket
import threading
import logging
from state import get_position
from pelco_commands import send_command


class EasyCommServer:
    """Threaded TCP server that accepts EasyComm II commands and updates rotor position."""

    def __init__(self, host="0.0.0.0", port=4533, update_callback=None):
        self.host = host
        self.port = port
        self.update_callback = update_callback
        self._server_socket = None
        self._server_thread = None
        self._running = False

    def _parse_easycomm_command(self, command):
        """
        Parse either EasyComm (AZxxx ELxxx) or Hamlib (P az el) commands.
        Returns: (az, el) or None
        """
        command = command.strip().upper()

        # EasyComm format
        if command.startswith("AZ") and "EL" in command:
            try:
                az_index = command.index("AZ") + 2
                el_index = command.index("EL") + 2
                az = float(command[az_index:el_index - 2].strip())
                el = float(command[el_index:].strip())
                return az, el
            except (ValueError, IndexError) as e:
                logging.warning("Failed to parse EasyComm command '%s': %s", command, e)

        # Hamlib format (e.g., "P 180.0 90.0")
        elif command.startswith("P "):
            try:
                parts = command[1:].strip().split()
                if len(parts) >= 2:
                    az = float(parts[0])
                    el = float(parts[1])
                    return az, el
            except ValueError as e:
                logging.warning("Failed to parse Hamlib command '%s': %s", command, e)

        return None


    def _handle_client(self, client_socket):
        """Handle an individual TCP client."""
        with client_socket:
            while True:
                try:
                    data = client_socket.recv(1024)
                    if not data:
                        break
                    command = data.decode("utf-8").strip()
                    logging.info("Received EasyComm command: %s", command)

                    if command == "GET":
                        az, el = get_position()
                        response = f"AZ{az:.1f} EL{el:.1f}\n"
                        client_socket.sendall(response.encode("utf-8"))
                        continue

                    result = self._parse_easycomm_command(command)
                    if result:
                        az, el = result
                        send_command(az, el, update_callback=self.update_callback)
                except (ConnectionResetError, socket.error) as e:
                    logging.warning("Socket error: %s", e)
                    break

    def _run(self):
        """Main server loop."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._running = True

        logging.info("EasyComm TCP server running on %s:%d", self.host, self.port)

        while self._running:
            try:
                client, addr = self._server_socket.accept()
                logging.info("Client connected from %s", addr)
                thread = threading.Thread(
                    target=self._handle_client, args=(client,), daemon=True
                )
                thread.start()
            except socket.error as e:
                logging.warning("Socket error in server loop: %s", e)
                break

    def start(self):
        """Start the server thread."""
        if self._server_thread and self._server_thread.is_alive():
            logging.info("EasyComm server already running.")
            return
        self._server_thread = threading.Thread(target=self._run, daemon=True)
        self._server_thread.start()

    def stop(self):
        """Stop the server and close the socket."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.shutdown(socket.SHUT_RDWR)
                self._server_socket.close()
            except OSError:
                pass
        logging.info("EasyComm server stopped.")


class EasyCommServerManager:
    """Manages a singleton instance of EasyCommServer."""
    _instance = None

    @classmethod
    def start(cls, update_callback=None):
        """Start the EasyComm server in a background thread."""
        if not isinstance(cls._instance, EasyCommServer):
            cls._instance = EasyCommServer(update_callback=update_callback)
        cls._instance.start()

    @classmethod
    def stop(cls):
        """Stop the EasyComm server if it is running."""
        if isinstance(cls._instance, EasyCommServer):
            cls._instance.stop()
            cls._instance = None

    @classmethod
    def get_instance(cls):
        """Get the singleton instance of EasyCommServer."""
        return cls._instance
