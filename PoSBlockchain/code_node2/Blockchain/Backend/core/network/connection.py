# import socket
# from Blockchain.Backend.core.network.network import NetworkEnvelope
# from Blockchain.Backend.core.block import Block
# import os
# import logging

# logger = logging.getLogger(__name__)

# class Node:
#     def __init__(self, host, port,sock=None):
#         self.host = host
#         self.port = port
#         self.sock = sock
#         self.ADDR = (self.host, self.port)
#         if self.sock:
#             # Create a file-like object for reading if needed by NetworkEnvelope.parse
#             self.stream = self.sock.makefile('rb')
#         else:
#             self.stream = None

#     """Start the servver and bind to a port number"""

#     def startServer(self):
#         self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         print(f"[DEBUG] PID {os.getpid()} binding to {self.ADDR}")
#         self.server.bind(self.ADDR)
#         self.server.listen()

    
#     def connect(self, port, bindPort = None):
#         self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

#         if bindPort:
#            self.socket.bind((self.host, port))
            
#         self.socket.connect((self.host, self.port))
#         return self.socket
    
#     def acceptConnection(self):
#         self.conn, self.addr = self.server.accept()
#         self.stream = self.conn.makefile('rb', None)
#         return self.conn, self.addr
    
#     def closeConnection(self):
#         self.socket.close()

#     def send(self, message):
#         envelope = NetworkEnvelope(message.command, message.serialise())
#         self.socket.sendall(envelope.serialise())

    

#     def read(self):
#         envelope = NetworkEnvelope.parse(self.stream)
#         return envelope

# In your Node class file

import socket
import select  # <<< ADD THIS IMPORT
from Blockchain.Backend.core.network.network import NetworkEnvelope
from Blockchain.Backend.core.block import Block # Keep imports even if not directly used here
import os
import logging

logger = logging.getLogger(__name__)

class Node:
    def __init__(self, host, port, sock=None): # Keep existing __init__
        self.host = host
        self.port = port # This is usually the TARGET port for connect, or LOCAL port for server
        self.sock = sock # sock passed in is likely an ACCEPTED connection
        self.ADDR = (self.host, self.port)

        # Sockets this Node instance might manage
        self.server = None       # Listening socket (from startServer)
        self.socket = None       # Outgoing connection socket (from connect)
        self.conn = None         # Incoming connection socket (from acceptConnection OR passed via sock in __init__)
        self.addr = None         # Address for self.conn

        self.stream = None       # Read stream associated with EITHER self.socket or self.conn

        # --- Initialize stream based on sock IF provided ---
        if self.sock:
            # If a socket was passed in, assume it's an accepted connection
            self.conn = self.sock # Store it as the 'accepted' connection socket
            try:
                 # Create unbuffered binary stream for reading
                 self.stream = self.conn.makefile('rb', buffering=0)
                 logger.debug(f"Node __init__: Created stream for passed socket (assumed conn) fd={self.conn.fileno()}")
            except (OSError, ValueError, AttributeError) as e:
                 logger.error(f"Node __init__: Failed to create stream for passed socket: {e}")
                 self.conn = None
                 self.stream = None
        # --------------------------------------------------

    def startServer(self):
        # <<< KEEP THIS METHOD AS IS >>>
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Optional: Allow address reuse
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        print(f"[DEBUG] PID {os.getpid()} binding to {self.ADDR}") # Use self.ADDR
        self.server.bind(self.ADDR) # Bind to the port defined for this Node instance
        self.server.listen()
        print(f"Node Server Listening on {self.ADDR}") # Added log

    def connect(self, local_bind_port, bind_flag=False): # Use descriptive names
        """Connects OUTWARD to self.port (set during Node init), optionally binding locally first."""
        target_addr = (self.host, self.port) # Target is always self.port (set in __init__)

        if self.socket:
            logger.warning(f"Node connect: Socket already exists.")
            return self.socket

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if bind_flag: # Check the flag explicitly
                bind_addr = (self.host, local_bind_port) # Use the specific local port to bind
                logger.debug(f"Node connect: Binding client socket to {bind_addr}")
                self.socket.bind(bind_addr)

            logger.info(f"Node connect: Connecting to {target_addr}...") # Log the TARGET address
            self.socket.settimeout(10.0)
            self.socket.connect(target_addr) # <<< MUST connect to target_addr / self.port
            self.socket.settimeout(None)
            logger.info(f"Node connect: Connected successfully to {target_addr}")

            self.stream = self.socket.makefile('rb', buffering=0)
            self.conn = None
            return self.socket

        except (OSError, ConnectionRefusedError, socket.timeout) as e:
            logger.error(f"Node connect: Failed to connect to {target_addr}: {e}") # Log TARGET address on error
            if self.socket: self.socket.close()
            self.socket = None
            self.stream = None
            return None

    def acceptConnection(self):
        """ Accepts a connection on the listening server socket. """
        # <<< REPLACE acceptConnection method with this improved version >>>
        if not self.server:
            logger.error("Node acceptConnection: Cannot accept, server not started.")
            return None, None

        try:
            logger.debug(f"Node acceptConnection: Waiting on {self.ADDR}...")
            # Accept the connection using the server socket
            conn, addr = self.server.accept()
            logger.info(f"Node acceptConnection: Accepted connection from {addr}")

            # Store the accepted connection details in THIS Node instance
            self.conn = conn
            self.addr = addr
            # Create the stream for this accepted connection
            self.stream = self.conn.makefile('rb', buffering=0) # Unbuffered binary read stream
            # Ensure client socket is None when accepting
            if self.socket: logger.warning("Node acceptConnection: Overwriting existing client socket state.")
            self.socket = None

            return self.conn, self.addr # Return connection and address

        except OSError as e:
             logger.error(f"Node acceptConnection: Error accepting: {e}", exc_info=True)
             self.conn = None
             self.addr = None
             self.stream = None
             return None, None


    def closeConnection(self):
        """ Closes the active socket (client or accepted) and stream. """
        # <<< REPLACE closeConnection with this improved version >>>
        active_socket = self.socket if self.socket else self.conn
        socket_type = "client" if self.socket else ("accepted" if self.conn else "none")
        logger.debug(f"Node closeConnection: Closing {socket_type} socket.")

        if self.stream and not self.stream.closed:
            try:
                self.stream.close()
                logger.debug("Node closeConnection: Read stream closed.")
            except Exception as e_cls_stream:
                 logger.warning(f"Node closeConnection: Error closing stream: {e_cls_stream}")
        self.stream = None

        if active_socket:
            try:
                active_socket.close()
                logger.debug(f"Node closeConnection: {socket_type} socket closed.")
            except Exception as e_cls_sock:
                 logger.warning(f"Node closeConnection: Error closing {socket_type} socket: {e_cls_sock}")

        # Reset attributes
        self.socket = None
        self.conn = None
        self.addr = None


    def send(self, message):
        """ Sends a message object (requires .command, .serialise). """
        # <<< REPLACE send method with this improved version >>>
        # Determine which socket to use: outgoing (self.socket) or incoming (self.conn)
        active_socket = self.socket if self.socket else self.conn
        socket_type = "client" if self.socket else ("accepted" if self.conn else "none")

        if not active_socket or active_socket.fileno() < 0: # Check if socket is valid
            logger.error(f"Node send: No active {socket_type} socket to send message.")
            return False # Indicate failure

        try:
            # Create the envelope (assuming this is correct)
            envelope = NetworkEnvelope(message.command, message.serialise())
            bytes_to_send = envelope.serialise() # Assumes this returns bytes
            logger.debug(f"Node send: Sending {message.command} ({len(bytes_to_send)} bytes) via {socket_type} socket fd={active_socket.fileno()}")
            active_socket.sendall(bytes_to_send)
            return True # Indicate success
        except (OSError, BrokenPipeError) as e:
            logger.error(f"Node send: Error sending via {socket_type} socket: {e}")
            # Close the problematic connection
            self.closeConnection()
            return False # Indicate failure
        except Exception as e:
            logger.error(f"Node send: Unexpected error during send: {e}", exc_info=True)
            self.closeConnection()
            return False


    def read(self, timeout=None): # <<< ADD timeout=None argument
        """ Reads one NetworkEnvelope with optional timeout. """
        # <<< REPLACE read method with this improved version >>>
        if not self.stream or self.stream.closed:
            logger.debug("Node read: No valid stream.")
            return None

        # Determine the underlying socket for select
        underlying_socket = self.socket if self.socket else self.conn
        socket_type = "client" if self.socket else ("accepted" if self.conn else "none")

        if not underlying_socket or underlying_socket.fileno() < 0:
            logger.error(f"Node read: Stream exists but no valid {socket_type} socket found.")
            self.closeConnection() # Clean up potentially inconsistent state
            return None

        socket_info = f"{socket_type} socket fd={underlying_socket.fileno()}"

        # Use select() only if a timeout is provided
        if timeout is not None:
            try:
                ready_to_read, _, _ = select.select([underlying_socket], [], [], timeout)
                if not ready_to_read:
                    logger.warning(f"Node read: Timeout ({timeout}s) occurred on {socket_info}.")
                    return None # Return None specifically on timeout
                # Socket is ready, proceed to read
                logger.debug(f"Node read: {socket_info} ready after select.")
            except (OSError, ValueError) as e_sel: # ValueError if fd invalid
                 logger.error(f"Node read: Error during select() on {socket_info}: {e_sel}")
                 self.closeConnection() # Close on select error
                 return None

        # If no timeout or select indicated readiness, attempt to parse
        envelope = None
        try:
            # NetworkEnvelope.parse needs to handle reading from the stream
            # It should return None on clean EOF, raise Exception on error
            logger.debug(f"Node read: Calling NetworkEnvelope.parse on {socket_info}'s stream.")
            envelope = NetworkEnvelope.parse(self.stream)

            if envelope is None:
                # parse indicated clean close (EOF)
                logger.info(f"Node read: NetworkEnvelope.parse returned None (EOF) on {socket_info}. Closing connection.")
                self.closeConnection() # Close our end
                # Return None because the connection ended

        except (OSError, BrokenPipeError) as e_sock: # Socket errors during parse's internal read
            logger.error(f"Node read: Socket error during parse() on {socket_info}: {e_sock}")
            self.closeConnection() # Close connection
            envelope = None # Ensure None is returned
        except Exception as e_parse: # Other errors during parsing (ValueError, etc.)
            logger.error(f"Node read: Error during parse() on {socket_info}: {e_parse}", exc_info=True)
            self.closeConnection() # Close connection
            envelope = None # Ensure None is returned

        # Return the parsed envelope (if successful) or None (if timeout/EOF/error)
        return envelope