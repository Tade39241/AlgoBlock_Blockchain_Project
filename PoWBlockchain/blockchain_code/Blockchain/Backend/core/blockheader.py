import binascii
import sys
import time
import logging
from Blockchain.Backend.util.util import hash256, little_endian_to_int, int_to_little_endian, bits_to_targets
from Blockchain.Backend.core.database.db import BlockchainDB

# --- Add this basic configuration near the top ---
# Configure logging for this module/process
log_format = '%(message)s'
# Log INFO level messages and above to standard error
logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stderr)
# You could also configure a FileHandler here if you want logs in a separate file per process
# --- End configuration ---

# Get a logger for this module
logger = logging.getLogger('blockheader')




class BlockHeader:
    def __init__(self, version, prevBlockHash, merkleRoot, timestamp, bits, nonce=0, blockHash=None):
        self.version = version
        # --- Ensure prevBlockHash is bytes ---
        if isinstance(prevBlockHash, str):
            self.prevBlockHash = bytes.fromhex(prevBlockHash)
        elif isinstance(prevBlockHash, bytes):
            self.prevBlockHash = prevBlockHash
        else:
            raise TypeError(f"prevBlockHash must be bytes or a hex string, got {type(prevBlockHash)}")

        # --- Ensure merkleRoot is bytes ---
        if isinstance(merkleRoot, str):
            self.merkleRoot = bytes.fromhex(merkleRoot)
        elif isinstance(merkleRoot, bytes):
            self.merkleRoot = merkleRoot
        else:
            raise TypeError(f"merkleRoot must be bytes or a hex string, got {type(merkleRoot)}")

        self.timestamp = timestamp

        # --- Ensure bits is bytes ---
        if isinstance(bits, str):
            self.bits = bytes.fromhex(bits) # Convert hex string to bytes
        elif isinstance(bits, bytes):
            self.bits = bits # Already bytes
        # Add handling if bits could be int?
        # elif isinstance(bits, int):
        #    self.bits = int_to_little_endian(bits, 4) # Assuming 4 bytes
        else:
            raise TypeError(f"bits must be bytes or a hex string, got {type(bits)}")

        # --- Ensure nonce is int ---
        if isinstance(nonce, bytes):
             self.nonce = little_endian_to_int(nonce) # Convert bytes to int
        elif isinstance(nonce, int):
             self.nonce = nonce # Already int
        else:
             raise TypeError(f"nonce must be int or bytes, got {type(nonce)}")

        # --- Ensure blockHash is bytes or None ---
        if isinstance(blockHash, str):
            self.blockHash = bytes.fromhex(blockHash) # Convert hex string to bytes
        elif isinstance(blockHash, bytes) or blockHash is None:
            self.blockHash = blockHash # Already bytes or None
        else:
            raise TypeError(f"blockHash must be bytes, hex string, or None, got {type(blockHash)}")

    # def __init__(self, version, prevBlockHash, merkleRoot, timestamp, bits, nonce= None):
    #     self.version= version
    #     self.prevBlockHash = prevBlockHash
    #     self.merkleRoot = merkleRoot
    #     self.timestamp = timestamp
    #     self.bits = bits
    #     self.nonce = nonce
    #     self.blockHash = ''

    # @classmethod
    # def parse(cls, s):
    #     version = little_endian_to_int(s.read(4))
    #     prevBlockHash = s.read(32)[::-1]
    #     merkleRoot = s.read(32)[::-1]
    #     timestamp = little_endian_to_int(s.read(4))
    #     bits = s.read(4)
    #     nonce = s.read(4)
    #     return cls(version,prevBlockHash, merkleRoot, timestamp, bits, nonce)

    @classmethod
    def parse(cls, s):
        version = little_endian_to_int(s.read(4))
        prevBlockHash = s.read(32)[::-1] # Read 32 bytes, reverse for internal use
        merkleRoot = s.read(32)[::-1]    # Read 32 bytes, reverse for internal use
        timestamp = little_endian_to_int(s.read(4))
        bits = s.read(4) # Read bits as bytes
        nonce = little_endian_to_int(s.read(4))
        # Return instance with bytes hashes
        return cls(version, prevBlockHash, merkleRoot, timestamp, bits, nonce)


    # def serialise(self):
    #     result = int_to_little_endian(self.version, 4)
    #     result += self.prevBlockHash[::-1]
    #     result += self.merkleRoot[::-1]
    #     result += int_to_little_endian(self.timestamp, 4)
    #     result += self.bits
    #     result += self.nonce
    #     return result

    # def serialise(self):
    #     result = int_to_little_endian(self.version, 4)

    #     # --- Double check types before concatenation ---
    #     if not isinstance(self.prevBlockHash, bytes) or len(self.prevBlockHash) != 32:
    #          raise TypeError(f"prevBlockHash must be 32 bytes for serialisation, got {type(self.prevBlockHash)}")
    #     if not isinstance(self.merkleRoot, bytes) or len(self.merkleRoot) != 32:
    #          raise TypeError(f"merkleRoot must be 32 bytes for serialisation, got {type(self.merkleRoot)}")

    #     # Concatenate BYTES (reversed for network format)
    #     result += self.prevBlockHash[::-1]
    #     result += self.merkleRoot[::-1]

    #     result += int_to_little_endian(self.timestamp, 4)

    #     # Ensure bits is bytes
    #     bits_bytes = self.bits
    #     if isinstance(bits_bytes, str): # If bits was stored as hex string
    #          bits_bytes = bytes.fromhex(bits_bytes)
    #     elif isinstance(bits_bytes, int): # If bits was stored as int
    #          bits_bytes = int_to_little_endian(bits_bytes, 4) # Assuming 4 bytes
    #     elif not isinstance(bits_bytes, bytes):
    #          raise TypeError(f"bits must be bytes, hex string, or int for serialisation, got {type(bits_bytes)}")
    #     result += bits_bytes # Add bits (now guaranteed bytes)

    #     result += int_to_little_endian(self.nonce, 4)
    #     return result

    def serialise(self):
        """Serializes the block header into bytes for network transmission or hashing."""
        result = int_to_little_endian(self.version, 4)

        # Ensure prevBlockHash and merkleRoot are bytes
        if not isinstance(self.prevBlockHash, bytes) or len(self.prevBlockHash) != 32:
             raise TypeError(f"prevBlockHash must be 32 bytes for serialisation, got {type(self.prevBlockHash)}")
        if not isinstance(self.merkleRoot, bytes) or len(self.merkleRoot) != 32:
             raise TypeError(f"merkleRoot must be 32 bytes for serialisation, got {type(self.merkleRoot)}")

        result += self.prevBlockHash[::-1] # Reverse for network byte order
        result += self.merkleRoot[::-1]    # Reverse for network byte order

        result += int_to_little_endian(self.timestamp, 4)

        # Ensure bits is bytes
        bits_bytes = self.bits
        if isinstance(bits_bytes, str):
             bits_bytes = bytes.fromhex(bits_bytes)
        elif not isinstance(bits_bytes, bytes):
             # Add handling if bits could be int?
             # if isinstance(bits_bytes, int): bits_bytes = int_to_little_endian(bits_bytes, 4)
             raise TypeError(f"bits must be bytes or hex string for serialisation, got {type(bits_bytes)}")
        result += bits_bytes # Add bits (already in correct byte order)

        # --- FIX for Nonce Type ---
        nonce_to_serialise = self.nonce
        if isinstance(nonce_to_serialise, bytes):
            # If nonce is already bytes, ensure it's 4 bytes and use directly
            logger.warning(f"Nonce is unexpectedly bytes during serialise. Using directly. Value: {nonce_to_serialise.hex()}") # Add warning
            if len(nonce_to_serialise) < 4:
                nonce_bytes = nonce_to_serialise.ljust(4, b'\x00') # Pad if too short
            elif len(nonce_to_serialise) > 4:
                nonce_bytes = nonce_to_serialise[:4] # Truncate if too long
            else:
                nonce_bytes = nonce_to_serialise
        elif isinstance(nonce_to_serialise, int):
            # If nonce is int, convert to 4 bytes little-endian
            nonce_bytes = int_to_little_endian(nonce_to_serialise, 4)
        else:
            # Log the unexpected type before raising error
            logger.error(f"Nonce has unexpected type during serialise: {type(nonce_to_serialise)}")
            raise TypeError(f"nonce must be int or bytes for serialisation, got {type(nonce_to_serialise)}")
        result += nonce_bytes
        # --- END FIX ---

        return result

    
    def to_hex(self):
        self.blockHash =  self.generateBlockHash()
        self.nonce =  little_endian_to_int(self.nonce)
        self.prevBlockHash = self.prevBlockHash.hex()
        self.merkleRoot = self.merkleRoot.hex()
        self.bits = self.bits.hex()

    def to_bytes(self):
        self.nonce =  int_to_little_endian(self.nonce, 4)
        self.blockHash = bytes.fromhex(self.blockHash)
        self.prevBlockHash = bytes.fromhex(self.prevBlockHash)
        self.merkleRoot = bytes.fromhex(self.merkleRoot)
        self.bits = bytes.fromhex(self.bits)

    def mine(self, target, newBlockAvailable):
        self.blockHash = target + 1
        competitionOver = False
        start_time = time.time()  # Track mining start time
        log_interval = 100000 

        print(f" Mining started at {time.ctime()}", end='\r')

        attempts = 0

        if self.nonce is None:
             self.nonce = 0
        elif isinstance(self.nonce, bytes): # If nonce was loaded as bytes
             self.nonce = little_endian_to_int(self.nonce)
        
        print(f"[Mine Loop Start] Initial Nonce: {self.nonce}, Target: {target:064x}", flush=True)
        while self.blockHash > target:
            if newBlockAvailable:
                print(f"[Mine Loop {self.nonce}] newBlockAvailable is True. Competition lost.", flush=True)
                competitionOver = True
                return competitionOver
                
            # --- Prepare data for hashing ---
            version_bytes = int_to_little_endian(self.version, 4)
            # Ensure prevBlockHash and merkleRoot are bytes and reversed
            prev_hash_bytes = self.prevBlockHash if isinstance(self.prevBlockHash, bytes) else bytes.fromhex(self.prevBlockHash)
            merkle_root_bytes = self.merkleRoot if isinstance(self.merkleRoot, bytes) else bytes.fromhex(self.merkleRoot)
            timestamp_bytes = int_to_little_endian(self.timestamp, 4)
            bits_bytes = self.bits if isinstance(self.bits, bytes) else bytes.fromhex(self.bits)
            nonce_bytes = int_to_little_endian(self.nonce, 4)

            header_data = (
                version_bytes
                + prev_hash_bytes[::-1]
                + merkle_root_bytes[::-1]
                + timestamp_bytes
                + bits_bytes
                + nonce_bytes
            )

            current_hash_bytes = hash256(header_data)
            self.blockHash = little_endian_to_int(current_hash_bytes)
            
            self.nonce +=1
            attempts += 1
            if attempts % 10000 == 0:
                # pause 50 ms after every 10k hashes
                time.sleep(0.05)
            if self.nonce % log_interval == 0:
                elapsed_time = time.time() - start_time
                print(f" Mining in progress {self.nonce} Nonce: {self.nonce} Hash: {self.blockHash} Time elapsed: {elapsed_time:.2f}s", end='\r',flush=True)
        
        # Log final result when block is found
        elapsed = time.time() - start_time
        hashrate = self.nonce / elapsed if elapsed > 0 else 0
        print(f"\n Golden hash found! Nonce: {self.nonce:,}, Hashrate: {hashrate:.2f} h/s")

        final_hash_bytes_le = int_to_little_endian(self.blockHash, 32)
        self.blockHash = final_hash_bytes_le # Store standard BYTES

        self.nonce -= 1

        return competitionOver
    
    # def validateBlock(self):
    #     lastBlock = BlockchainDB().lastBlock()

    #     if self.prevBlockHash.hex() == lastBlock[0]['BlockHeader']['blockHash']:
    #         if self.check_pow():
    #             return True

    def validateBlock(self):
        lastBlock = BlockchainDB().lastBlock()
        
        # Handle potential different structures in a safe way
        if lastBlock is None:
            print("No blocks in blockchain to validate against")
            return False
            
        # Safely extract the block hash
        try:
            # If lastBlock is a list containing one dict
            if isinstance(lastBlock, list) and len(lastBlock) > 0:
                block_data = lastBlock[0]
                if isinstance(block_data, dict) and 'BlockHeader' in block_data:
                    prev_hash = block_data['BlockHeader']['blockHash']
                else:
                    print("Unexpected block structure (missing BlockHeader)")
                    return False
            # If lastBlock is directly a dict
            elif isinstance(lastBlock, dict) and 'BlockHeader' in lastBlock:
                prev_hash = lastBlock['BlockHeader']['blockHash']
            else:
                print(f"Unexpected lastBlock format: {type(lastBlock)}")
                return False
                
            # Now compare the hashes and check proof of work
            if self.prevBlockHash.hex() == prev_hash:
                if self.check_pow():
                    return True
            return False
            
        except Exception as e:
            print(f"Error validating block: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    def check_pow(self):
        sha = hash256(self.serialise())
        proof = little_endian_to_int(sha)
        return proof < bits_to_targets(self.bits)
    
    def generateBlockHash(self):
        block_data = self.serialise()
        return hash256(block_data).hex()
    
    # def generateBlockHash(self):
    #     sha = hash256(self.serialise())
    #     proof = little_endian_to_int(sha)
    #     return int_to_little_endian(proof, 32).hex()[::-1]
    
    # def to_dict(self):
    #     dt = self.__dict__
    #     return dt
    
    # def to_dict(self):
    #     # Convert bytes to hex strings for JSON compatibility
    #     return {
    #         'version': self.version,
    #         'prevBlockHash': self.prevBlockHash.hex(),
    #         'merkleRoot': self.merkleRoot.hex(),
    #         'timestamp': self.timestamp,
    #         'bits': self.bits.hex(),
    #         'nonce': little_endian_to_int(self.nonce), # Store nonce as int
    #         'blockHash': self.blockHash.hex() if self.blockHash else None # Store hash as hex
    #     }

    def to_dict(self):
        """
        Returns a dictionary representation of the block header,
        ensuring byte fields are converted to hex strings and nonce is an integer.
        """
        header_dict = {
            'version': self.version,
            'timestamp': self.timestamp,
        }

        # Handle fields that should be hex strings
        for attr_name in ['prevBlockHash', 'merkleRoot', 'bits', 'blockHash']:
            value = getattr(self, attr_name, None)
            if isinstance(value, bytes):
                header_dict[attr_name] = value.hex()
            elif isinstance(value, str): # Assume it's already hex if string
                header_dict[attr_name] = value
            elif value is None and attr_name == 'blockHash':
                 header_dict[attr_name] = None # Allow blockHash to be None
            # Add handling for other unexpected types if necessary

        # Handle nonce separately - STORE AS INTEGER
        nonce_val = getattr(self, 'nonce', None)
        if isinstance(nonce_val, bytes):
            # Convert nonce bytes to integer
            header_dict['nonce'] = little_endian_to_int(nonce_val) # <-- STORE AS INT
        elif isinstance(nonce_val, int):
            # Keep nonce as integer
            header_dict['nonce'] = nonce_val # <-- STORE AS INT
        elif isinstance(nonce_val, str): # If it's a hex string, convert to int
             try:
                 header_dict['nonce'] = int(nonce_val, 16) # <-- STORE AS INT
             except (ValueError, TypeError):
                 print(f"Warning: Could not convert nonce string '{nonce_val}' to int. Setting to 0.")
                 header_dict['nonce'] = 0
        else:
             header_dict['nonce'] = 0 # Default to 0 or handle error

        # Ensure blockHash is present, even if None
        if 'blockHash' not in header_dict:
             header_dict['blockHash'] = None

        return header_dict
    
    @classmethod
    def from_dict(cls, header_dict):
        header = cls(
            version=header_dict['version'],
            prevBlockHash=bytes.fromhex(header_dict['prevBlockHash']), # Store as bytes
            merkleRoot=bytes.fromhex(header_dict['merkleRoot']), # Store as bytes
            timestamp=header_dict['timestamp'],
            bits=bytes.fromhex(header_dict['bits']) # Store as bytes
            # Nonce and blockHash handled below
        )
        # --- Store nonce as INT ---
        if 'nonce' in header_dict:
             if isinstance(header_dict['nonce'], int):
                 header.nonce = header_dict['nonce'] # Already int
             else:
                 # Attempt conversion if not int (e.g., from string)
                 try: header.nonce = int(header_dict['nonce'])
                 except (ValueError, TypeError): header.nonce = 0 # Default or error
        else:
             header.nonce = 0 # Default if missing

        # --- Store blockHash as bytes or None ---
        header.blockHash = bytes.fromhex(header_dict['blockHash']) if header_dict.get('blockHash') else None
        return header