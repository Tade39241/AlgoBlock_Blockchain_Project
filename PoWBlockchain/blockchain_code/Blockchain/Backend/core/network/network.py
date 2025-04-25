from io import BytesIO
from Blockchain.Backend.util.util import int_to_little_endian, little_endian_to_int, hash256, encode, read_varint, encode_ports_varint

NETWORK_MAGIC = b'\xf9\xbe\xb4\xd9'
FINISHED_SENDING = b'\x0a\x11\x09\x07'


class NetworkEnvelope:
    def __init__(self, command, payload):
        self.command = command
        self.payload = payload
        self.magic = NETWORK_MAGIC

    @classmethod
    def parse(cls, s):
        magic = s.read(4)
        print(f"[DEBUG] NetworkEnvelope.parse: got magic bytes {magic.hex()}")
        if not magic:
            raise RuntimeError("Connection closed before magic bytes received")
        if magic != NETWORK_MAGIC:
            raise RuntimeError(f"Magic is not right {magic.hex()} vs {NETWORK_MAGIC.hex()}")
        
        command = s.read(12)
        command = command.strip(b'\x00')
        payloadLen = little_endian_to_int(s.read(4))
        checksum  = s.read(4)
        payload = s.read(payloadLen)
        calculatedChecksum = hash256(payload)[:4]

        if calculatedChecksum != checksum:
            raise IOError("checksum does not match")
        
        return cls(command, payload)
        
    def serialise(self):
        result = self.magic
        result += self.command + b'\x00' * (12 - len(self.command))
        result += int_to_little_endian(len(self.payload), 4)
        result += hash256(self.payload)[:4]
        result += self.payload
        return result
    
    def stream(self):
        return BytesIO(self.payload)

class requestBlock:
    command = b'requestBlock'

    def __init__(self, startBlock = None, endBlock = None):
        if startBlock is None:
            raise RuntimeError("starting Block cannot be None")
        else:
            self.startBlock = startBlock

        if endBlock is None:
            self.endBlock = b'\x00' * 32
        else:
            self.endBlock = endBlock

    @classmethod
    def parse(cls, stream):
        startBlock = stream.read(32)
        endBlock = stream.read(32)
        return startBlock, endBlock
    
    def serialise(self):
        result = self.startBlock
        result += self.endBlock
        return result

class portList:
    command = b'portlist'
    def __init__(self, ports = None):
        self.ports = ports

    @classmethod
    def parse(cls, s):
        ports = []
        length =  read_varint(s)
        print(f"DEBUG: length from varint = {length}")

        for idx in range(length):
            chunk = s.read(4)
            print(f"DEBUG: chunk #{idx} = {chunk.hex()}")
            port = little_endian_to_int(chunk)
            ports.append(port)
            
        return ports
    
    def serialise(self):
        result =  encode_ports_varint(len(self.ports))
        for port in self.ports:
            result += int_to_little_endian(port, 4)
        return result

class FinishedSending:
    command = b'Finished'

    @classmethod
    def parse(cls,s ):
        magic = s.read(4)

        if magic == FINISHED_SENDING:
            return "Finished"

    def serialise(self):
        result = FINISHED_SENDING
        return result
    
class AccountUpdateMessage:
    command = b'account'  # Matches the command in your handler
    
    def __init__(self, sender_port, address, data):
        self.sender_port = sender_port
        self.address = address
        self.data = data
        
    def serialise(self):
        """Convert to bytes in a format compatible with NetworkEnvelope"""
        import json
        message = {
            'type': 'account_update',
            'sender_port': self.sender_port,
            'address': self.address,
            'data': self.data
        }
        return json.dumps(message).encode()