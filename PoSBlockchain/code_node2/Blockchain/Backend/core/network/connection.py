import socket
from Blockchain.Backend.core.network.network import NetworkEnvelope
from Blockchain.Backend.core.block import Block
import os

class Node:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.ADDR = (self.host, self.port)

    """Start the servver and bind to a port number"""

    def startServer(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"[DEBUG] PID {os.getpid()} binding to {self.ADDR}")
        self.server.bind(self.ADDR)
        self.server.listen()

    
    def connect(self, port, bindPort = None):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if bindPort:
           self.socket.bind((self.host, port))
            
        self.socket.connect((self.host, self.port))
        return self.socket
    
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