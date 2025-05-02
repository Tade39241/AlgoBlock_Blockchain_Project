from io import BytesIO
import json
from Blockchain.Backend.util.util import int_to_little_endian, little_endian_to_int, hash256, encode, read_varint, encode_ports_varint
import logging

logger = logging.getLogger(__name__)

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
    
class GetPeerTip:
    command = b'getpeertip'

    def __init__(self):
        pass # No payload needed

    def serialise(self):
        # Create an envelope with the command and empty payload
        return NetworkEnvelope(self.command, b'').serialise()

    @classmethod
    def parse(cls, stream):
        # No payload to parse, just return an instance
        return cls()

class PeerTip:
    command = b'peertip'

    def __init__(self, height, tip_hash):
        self.height = int(height)
        self.tip_hash = str(tip_hash) # Ensure it's a string

    def serialise(self):
        # Payload is a JSON dictionary
        payload_dict = {
            "height": self.height,
            "tip_hash": self.tip_hash
        }
        payload_bytes = json.dumps(payload_dict).encode('utf-8')
        return NetworkEnvelope(self.command, payload_bytes).serialise()

    @classmethod
    def parse(cls, stream):
        # Read the payload length (assuming NetworkEnvelope handles this or similar)
        # Here, we assume 'stream' contains *only* the JSON payload bytes
        payload_bytes = stream.read()
        try:
            payload_dict = json.loads(payload_bytes.decode('utf-8'))
            height = payload_dict.get('height')
            tip_hash = payload_dict.get('tip_hash')
            if height is None or tip_hash is None:
                raise ValueError("Missing 'height' or 'tip_hash' in PeerTip payload")
            # Perform basic validation if needed (e.g., is height int? is hash hex?)
            if not isinstance(height, int): raise ValueError("Height must be an integer")
            if not isinstance(tip_hash, str) or len(tip_hash) != 64: raise ValueError("Invalid tip_hash format")

            return cls(height, tip_hash)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
            logger.error(f"Failed to parse PeerTip payload: {e}. Payload: {payload_bytes[:100]}...")
            raise ValueError(f"Invalid PeerTip payload: {e}") from e
