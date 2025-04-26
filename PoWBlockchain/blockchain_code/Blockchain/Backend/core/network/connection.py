import socket
from Blockchain.Backend.core.network.network import NetworkEnvelope, FINISHED_SENDING

class Node:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.ADDR = (self.host, self.port)

    """Start the servver and bind to a port number"""

    def startServer(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(self.ADDR)
        self.server.listen()
    
    # def connect(self, port, bindPort = None):
    #     self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    #     if bindPort:
    #        self.socket.bind((self.host, port))
            
    #     self.socket.connect((self.host, self.port))
    #     return self.socket

     # --- MODIFIED connect method ---
    def connect(self, bind_port=None):
        """
        Connects to the target host and port specified in self.ADDR.
        Optionally binds the source socket to bind_port.
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow address reuse for the client socket too
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if bind_port:
            try:
                # Bind to '0.0.0.0' and the specified bind_port
                bind_addr = ('0.0.0.0', bind_port)
                self.socket.bind(bind_addr)
                print(f"[Node {self.port}] Socket bound to source {bind_addr}") # Added log
            except OSError as e:
                print(f"[Node {self.port}] Error binding socket to {bind_addr}: {e}")
                self.socket.close() # Close socket if bind fails
                self.socket = None
                return None # Indicate failure

        try:
            # Connect to the target address (self.host, self.port)
            print(f"[Node {self.port}] Attempting to connect to target {self.ADDR}") # Added log
            self.socket.connect(self.ADDR)
            print(f"[Node {self.port}] Connected successfully to {self.ADDR}") # Added log
            return self.socket
        except ConnectionRefusedError:
            print(f"[Node {self.port}] Connection refused by target {self.ADDR}")
            self.socket.close()
            self.socket = None
            return None
        except Exception as e:
            print(f"[Node {self.port}] Error connecting to {self.ADDR}: {e}")
            self.socket.close()
            self.socket = None
            return None
    # --- END MODIFIED connect method ---

    
    def acceptConnection(self):
        self.conn, self.addr = self.server.accept()
        self.stream = self.conn.makefile('rb', None)
        return self.conn, self.addr
    
    def closeConnection(self):
        self.socket.close()

    def send(self, message):
        envelope = NetworkEnvelope(message.command, message.serialise())
        self.socket.sendall(envelope.serialise())

    def read(self):
        envelope = NetworkEnvelope.parse(self.stream)
        return envelope
    

# import socket
# from Blockchain.Backend.core.network.network import NetworkEnvelope, FINISHED_SENDING

# class Node:
#     def __init__(self, host, port):
#         self.host = host
#         self.port = port
#         self.ADDR = (self.host, self.port)
#         self.socket = None # Initialize socket attribute
#         self.server = None # Initialize server attribute
#         self.conn = None   # Initialize conn attribute
#         self.addr = None   # Initialize addr attribute
#         self.stream = None # Initialize stream attribute

#     """Start the server and bind to a port number"""
#     def startServer(self):
#         self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         # Allow address reuse immediately after closing
#         self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#         self.server.bind(self.ADDR)
#         self.server.listen()
#         print(f"[Node {self.port}] Server started, listening on {self.ADDR}") # Added log

#     # --- MODIFIED connect method ---
#     def connect(self, bind_port=None):
#         """
#         Connects to the target host and port specified in self.ADDR.
#         Optionally binds the source socket to bind_port.
#         """
#         self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         # Allow address reuse for the client socket too
#         self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

#         if bind_port:
#             try:
#                 # Bind to '0.0.0.0' and the specified bind_port
#                 bind_addr = ('0.0.0.0', bind_port)
#                 self.socket.bind(bind_addr)
#                 print(f"[Node {self.port}] Socket bound to source {bind_addr}") # Added log
#             except OSError as e:
#                 print(f"[Node {self.port}] Error binding socket to {bind_addr}: {e}")
#                 self.socket.close() # Close socket if bind fails
#                 self.socket = None
#                 return None # Indicate failure

#         try:
#             # Connect to the target address (self.host, self.port)
#             print(f"[Node {self.port}] Attempting to connect to target {self.ADDR}") # Added log
#             self.socket.connect(self.ADDR)
#             print(f"[Node {self.port}] Connected successfully to {self.ADDR}") # Added log
#             return self.socket
#         except ConnectionRefusedError:
#             print(f"[Node {self.port}] Connection refused by target {self.ADDR}")
#             self.socket.close()
#             self.socket = None
#             return None
#         except Exception as e:
#             print(f"[Node {self.port}] Error connecting to {self.ADDR}: {e}")
#             self.socket.close()
#             self.socket = None
#             return None
#     # --- END MODIFIED connect method ---

#     def acceptConnection(self):
#         if not self.server:
#              print(f"[Node {self.port}] Error: Server not started. Call startServer first.")
#              return None, None
#         try:
#             self.conn, self.addr = self.server.accept()
#             self.stream = self.conn.makefile('rb', None)
#             print(f"[Node {self.port}] Accepted connection from {self.addr}") # Added log
#             return self.conn, self.addr
#         except Exception as e:
#             print(f"[Node {self.port}] Error accepting connection: {e}")
#             return None, None

#     def closeConnection(self):
#         # Close client socket if it exists
#         if self.socket:
#             try:
#                 self.socket.close()
#                 print(f"[Node {self.port}] Client socket closed.") # Added log
#             except Exception as e:
#                 print(f"[Node {self.port}] Error closing client socket: {e}")
#             finally:
#                 self.socket = None
#         # Close accepted connection if it exists
#         if self.conn:
#             try:
#                 self.conn.close()
#                 print(f"[Node {self.port}] Accepted connection closed.") # Added log
#             except Exception as e:
#                 print(f"[Node {self.port}] Error closing accepted connection: {e}")
#             finally:
#                 self.conn = None
#                 self.stream = None
#         # Close server socket if it exists
#         if self.server:
#             try:
#                 self.server.close()
#                 print(f"[Node {self.port}] Server socket closed.") # Added log
#             except Exception as e:
#                 print(f"[Node {self.port}] Error closing server socket: {e}")
#             finally:
#                 self.server = None


#     def send(self, message):
#         if not self.socket:
#              print(f"[Node {self.port}] Error: Not connected. Cannot send message.")
#              return # Or raise error
#         try:
#             envelope = NetworkEnvelope(message.command, message.serialise())
#             self.socket.sendall(envelope.serialise())
#             # print(f"[Node {self.port}] Sent {message.command.decode()} message to {self.ADDR}") # Optional log
#         except Exception as e:
#             print(f"[Node {self.port}] Error sending message: {e}")
#             # Consider closing connection on send error
#             self.closeConnection()


#     def read(self):
#         if not self.stream:
#              print(f"[Node {self.port}] Error: No active input stream to read from.")
#              return None # Or raise error
#         try:
#             envelope = NetworkEnvelope.parse(self.stream)
#             # print(f"[Node {self.port}] Received {envelope.command.decode()} message") # Optional log
#             return envelope
#         except EOFError:
#              print(f"[Node {self.port}] Connection closed by peer during read.")
#              self.closeConnection() # Close our end too
#              return None
#         except Exception as e:
#             print(f"[Node {self.port}] Error reading message: {e}")
#             self.closeConnection() # Close connection on read error
#             return None