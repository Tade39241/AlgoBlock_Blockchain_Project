import logging
from Blockchain.Backend.util.util import hash256, little_endian_to_int, int_to_little_endian, bits_to_targets
from Blockchain.Backend.core.database.db import BlockchainDB
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import PrivateKey, PublicKey, Signature

logger = logging.getLogger(__name__)

class BlockHeader:
    def __init__(self, version, prevBlockHash, merkleRoot, timestamp, validator_pubkey, signature=None):
        self.version = version
        self.prevBlockHash = prevBlockHash
        self.merkleRoot = merkleRoot
        self.timestamp = timestamp
        self.validator_pubkey = validator_pubkey
        self.signature = signature
        self.blockHash = ''

    @classmethod
    def parse(cls, s):
        # ... (read version, prevBlockHash, merkleRoot, timestamp, validator_pubkey) ...
        version = little_endian_to_int(s.read(4))
        prevBlockHash = s.read(32)[::-1]
        merkleRoot = s.read(32)[::-1]
        timestamp = little_endian_to_int(s.read(4))
        validator_pubkey = s.read(33) # Read pubkey bytes

        sig_length = little_endian_to_int(s.read(1))
        signature_obj = None # Initialize
        if sig_length > 0:
            sig_bytes = s.read(sig_length)
            try:
                # --- PARSE TO OBJECT HERE ---
                signature_obj = Signature.parse(sig_bytes)
                # --- END PARSE ---
            except Exception as e:
                logger.error(f"Failed to parse signature bytes during BlockHeader parsing: {e}")
                # Decide how to handle: raise error, return None, or create header without signature?
                # Raising might be safest to prevent processing invalid blocks.
                raise ValueError("Invalid signature encoding received") from e
        # Pass the Signature OBJECT (or None) to the constructor
        return cls(version, prevBlockHash, merkleRoot, timestamp, validator_pubkey, signature_obj)

    # @classmethod
    # def parse(cls, s):
    #     version = little_endian_to_int(s.read(4))
    #     prevBlockHash = s.read(32)[::-1]
    #     merkleRoot = s.read(32)[::-1]
    #     timestamp = little_endian_to_int(s.read(4))
    #     validator_pubkey = s.read(33)
    #     sig_length = little_endian_to_int(s.read(1))
    #     signature = s.read(sig_length) if sig_length > 0 else None
    #     return cls(version, prevBlockHash, merkleRoot, timestamp, validator_pubkey, signature)


    # def serialise(self):

    #     # print(f"serialise: version type={type(self.version)}")
    #     # print(f"serialise: prevBlockHash type={type(self.prevBlockHash)}")
    #     # print(f"serialise: merkleRoot type={type(self.merkleRoot)}")
    #     # print(f"serialise: timestamp type={type(self.timestamp)}")
    #     # print(f"serialise: validator_pubkey type={type(self.validator_pubkey)}")
    #     # print(f"serialise: signature type={type(self.signature)}")

    #     result = int_to_little_endian(self.version, 4)
    #     result += self.prevBlockHash[::-1]
    #     result += self.merkleRoot[::-1]
    #     result += int_to_little_endian(self.timestamp, 4)
    #     return result

    def serialise(self):
        # Version: 4 bytes, little-endian.
        result = int_to_little_endian(self.version, 4)
        
        # Previous Block Hash: already in bytes format
        result += self.prevBlockHash[::-1] if isinstance(self.prevBlockHash, bytes) else bytes.fromhex(self.prevBlockHash)[::-1]
        
        # Merkle Root: already in bytes format
        result += self.merkleRoot[::-1] if isinstance(self.merkleRoot, bytes) else bytes.fromhex(self.merkleRoot)[::-1]
        
        # Timestamp: 4 bytes, little-endian.
        result += int_to_little_endian(self.timestamp, 4)
        
        # Validator Public Key: already in bytes format
        result += self.validator_pubkey if isinstance(self.validator_pubkey, bytes) else bytes.fromhex(self.validator_pubkey)
        
        # Signature handling
        if self.signature is None:
            # Write a single 0 byte for length.
            result += int_to_little_endian(0, 1)
        else:
            # Handle Signature object properly
            if isinstance(self.signature, bytes):
                sig_bytes = self.signature
            elif hasattr(self.signature, 'r') and hasattr(self.signature, 's'):
                # Assuming Signature has r and s components
                # This likely needs to be adapted to your actual Signature class structure
                r_bytes = self.signature.r.to_bytes(32, 'big')
                s_bytes = self.signature.s.to_bytes(32, 'big')
                sig_bytes = r_bytes + s_bytes
            else:
                # Convert to string representation first if needed
                sig_bytes = str(self.signature).encode()
            
            sig_length = len(sig_bytes)
            if sig_length > 255:
                raise Exception("Signature length exceeds 255 bytes")
            result += int_to_little_endian(sig_length, 1)
            result += sig_bytes
        
        return result

    def serialise_without_signature(self):
        # Version: 4 bytes, little-endian.
        result = int_to_little_endian(self.version, 4)
        
        # Previous Block Hash: stored in big-endian, convert to little-endian.
        result += self.prevBlockHash[::-1]  # 32 bytes

        # Merkle Root: stored in big-endian, convert to little-endian.
        result += self.merkleRoot[::-1]       # 32 bytes

        # Timestamp: 4 bytes, little-endian.
        result += int_to_little_endian(self.timestamp, 4)

        # Validator Public Key: should be 33 bytes.
        result += self.validator_pubkey  # assumed already bytes (compressed)

        return result
    
    def serialise_with_signature(self):
        """Serialize the block header including the signature (with a 1-byte length prefix)."""
        result = self.serialise_without_signature()

        sig_bytes_to_write = None
        if self.signature is None:
            sig_bytes_to_write = b'' # Empty bytes if no signature
        # --- PRIORITIZE Signature OBJECT and DER ---
        elif isinstance(self.signature, Signature):
            try:
                sig_bytes_to_write = self.signature.der() # ALWAYS use DER for Signature objects
            except Exception as e:
                 logger.error(f"Error getting DER signature: {e}")
                 raise # Re-raise, cannot serialize correctly
        # --- Fallback for RAW BYTES (Use with caution, ideally should always be Signature obj) ---
        elif isinstance(self.signature, bytes):
             logger.warning("Serializing raw bytes found in BlockHeader.signature. Ensure this is intended.")
             sig_bytes_to_write = self.signature # Use raw bytes directly
        elif isinstance(self.signature, str):
              try:
                   logger.warning("Serializing hex string found in BlockHeader.signature.")
                   sig_bytes_to_write = bytes.fromhex(self.signature)
              except ValueError:
                   raise TypeError("BlockHeader.signature hex string is invalid")
        else:
            raise TypeError(f"Unsupported BlockHeader.signature type for serialization: {type(self.signature)}")

        sig_length = len(sig_bytes_to_write)
        if sig_length > 255:
            raise Exception("Signature length exceeds 255 bytes")

        result += int_to_little_endian(sig_length, 1) # Length prefix
        result += sig_bytes_to_write # Actual signature bytes

        # Log the final bytes being produced for comparison
        # logger.debug(f"[Serialize Signature] Final header bytes with sig: {result.hex()}")

        return result
    
    # def serialise_with_signature(self):
    #     """Serialize the block header including the signature (with a 1-byte length prefix)."""
    #     result = self.serialise_without_signature()
    
    #     if self.signature is None:
    #         # If no signature is present, write a single 0 byte.
    #         result += int_to_little_endian(0, 1)
    #     else:
    #         # Normalize signature to bytes (DER encoding if Signature object)
    #         if hasattr(self.signature, 'der'):
    #             sig_bytes = self.signature.der()
    #         elif isinstance(self.signature, bytes):
    #             sig_bytes = self.signature
    #         elif isinstance(self.signature, str):
    #             # Assume hex string
    #             sig_bytes = bytes.fromhex(self.signature)
    #         else:
    #             raise TypeError(f"BlockHeader.signature must be Signature, bytes, or hex str, got {type(self.signature)}")
    
    #         sig_length = len(sig_bytes)
    #         if sig_length > 255:
    #             raise Exception("Signature length exceeds 255 bytes")
    #         result += int_to_little_endian(sig_length, 1)
    #         result += sig_bytes
    
    #         print("[DEBUG serialise_with_signature] BlockHeader fields before serialization:")
    #         print(f"  version: {self.version}")
    #         print(f"  prevBlockHash: {self.prevBlockHash} ({type(self.prevBlockHash)})")
    #         print(f"  merkleRoot: {self.merkleRoot} ({type(self.merkleRoot)})")
    #         print(f"  timestamp: {self.timestamp}")
    #         print(f"  validator_pubkey: {self.validator_pubkey} ({type(self.validator_pubkey)})")
    #         print(f"  signature: {self.signature} ({type(self.signature)})")
    #         print(f"  serialized header: {result.hex()}")
    #         print(f"[DEBUG] Signature type: {type(self.signature)}, value: {self.signature}")
    
    #     return result

    # def serialise_with_signature(self):
    #     """Serialize the block header including the signature (with a 1-byte length prefix)."""
    #     result = self.serialise_without_signature()
        
    #     if self.signature is None:
    #         # If no signature is present, write a single 0 byte.
    #         result += int_to_little_endian(0, 1)
    #     else:
    #         # Handle different signature types properly
    #         if isinstance(self.signature, bytes):
    #             sig_bytes = self.signature
    #         elif hasattr(self.signature, 'r') and hasattr(self.signature, 's'):
    #             # Convert Signature object to bytes
    #             r_bytes = self.signature.r.to_bytes(32, 'big')
    #             s_bytes = self.signature.s.to_bytes(32, 'big')
    #             sig_bytes = r_bytes + s_bytes
    #         else:
    #             # Convert to string representation first if needed
    #             sig_bytes = str(self.signature).encode()
            
    #         sig_length = len(sig_bytes)
    #         if sig_length > 255:
    #             raise Exception("Signature length exceeds 255 bytes")
    #         result += int_to_little_endian(sig_length, 1)
    #         result += sig_bytes

    #         print("[DEBUG serialise_with_signature] BlockHeader fields before serialization:")
    #         print(f"  version: {self.version}")
    #         print(f"  prevBlockHash: {self.prevBlockHash} ({type(self.prevBlockHash)})")
    #         print(f"  merkleRoot: {self.merkleRoot} ({type(self.merkleRoot)})")
    #         print(f"  timestamp: {self.timestamp}")
    #         print(f"  validator_pubkey: {self.validator_pubkey} ({type(self.validator_pubkey)})")
    #         print(f"  signature: {self.signature} ({type(self.signature)})")
    #         print(f"  serialized header: {result.hex()}")
    #         print(f"[DEBUG] Signature type: {type(self.signature)}, value: {self.signature}")

    #     return result
    
    # def serialise(self):
    #     result = int_to_little_endian(self.version, 4)
    #     result += self.to_bytes(self.prevBlockHash)[::-1]
    #     result += self.to_bytes(self.merkleRoot)[::-1]
    #     result += int_to_little_endian(self.timestamp, 4)
    #     result += self.to_bytes(self.validator_pubkey)
    #     if self.signature is None:
    #         result += int_to_little_endian(0, 1)
    #     else:
    #         sig_bytes = self.to_bytes(self.signature)
    #         sig_length = len(sig_bytes)
    #         if sig_length > 255:
    #             raise Exception("Signature length exceeds 255 bytes")
    #         result += int_to_little_endian(sig_length, 1)
    #         result += sig_bytes
    #     return result


    def to_hex(self):
        self.blockHash = self.generateBlockHash()
        self.prevBlockHash = self.prevBlockHash.hex()
        self.merkleRoot = self.merkleRoot.hex()
        self.validator_pubkey = self.validator_pubkey.hex()
        if isinstance(self.signature, Signature):
            self.signature = self.signature.der().hex()
        elif isinstance(self.signature, bytes):
            self.signature = self.signature.hex()

    def to_bytes(self):
        # Ensure prevBlockHash is in bytes.
        if isinstance(self.prevBlockHash, bytes):
            prev_hash = self.prevBlockHash
        else:
            prev_hash = bytes.fromhex(self.prevBlockHash)

        # Ensure merkleRoot is in bytes.
        if isinstance(self.merkleRoot, bytes):
            merkle = self.merkleRoot
        else:
            merkle = bytes.fromhex(self.merkleRoot)

        # Ensure validator_pubkey is in bytes.
        if isinstance(self.validator_pubkey, bytes):
            validator_pub = self.validator_pubkey
        else:
            validator_pub = bytes.fromhex(self.validator_pubkey)

        # For signature, if it's already bytes use it; otherwise convert.
        if self.signature:
            if isinstance(self.signature, bytes):
                signature_bytes = self.signature
            else:
                signature_bytes = bytes.fromhex(self.signature)

        result = int_to_little_endian(self.version, 4)
        result += prev_hash               # 32 bytes expected
        result += merkle                  # 32 bytes expected
        result += int_to_little_endian(self.timestamp, 4)
        result += validator_pub           # 33 bytes (compressed)
        result += signature_bytes         # variable or fixed length
        return result


    def sign_block(self, private_key_int):
        """Sign the block with validator's private key."""
        priv = PrivateKey(private_key_int)
        block_data = self.serialise_without_signature()
        self.signature = priv.sign(block_data)
        self.blockHash = hash256(block_data + self.signature).hex()

    # def validate_block(self, validators=None):
    #     """Validate block signature and, if provided, validator status."""
    #     try:
    #         pub_key = PublicKey.parse(self.validator_pubkey)
    #         block_data = self.serialise_with_signature()
    #         valid_signature = pub_key.verify(self.signature, block_data)
    #         if validators is None:
    #             return valid_signature
    #         return valid_signature and self.validator_pubkey.hex() in validators
    #     except Exception as e:
    #         print(f"Validation Error: {e}")
    #         return False
    def validate_block(self, validators=None):
        """Validate block signature and, if provided, validator status."""
        print(f"[ValidateBlockDEBUG] signature: {self.signature}")
        try:
            # Ensure signature is a Signature object
            if not isinstance(self.signature, Signature):
                print(f"Error: signature must be an instance of Signature class, got {type(self.signature)}")
                return False
            
            # Get message to verify
            message = self.serialise_without_signature()
            if not message or not isinstance(message, bytes):
                print(f"Error: serialise_without_signature() returned invalid data: {type(message)}")
                return False
                
            # Hash the message properly
            import hashlib
            hashed_message = hashlib.sha256(message).digest()
            # Convert to integer (z value for ECDSA verification)
            z = int.from_bytes(hashed_message, 'big')
            
            # Get the public key for verification
            if not self.validator_pubkey or not isinstance(self.validator_pubkey, bytes):
                print(f"Error: Invalid validator_pubkey: {type(self.validator_pubkey)}")
                return False
                
            # Create public key object and verify signature
            from Blockchain.Backend.core.EllepticCurve.EllepticCurve import PublicKey
            pub_key = PublicKey.parse(self.validator_pubkey)
            
            # Debug info to help identify issues
            # print(f"Validating with public key: {self.validator_pubkey.hex()}")
            # print(f"Signature being verified: {self.signature}")
            # print(f"Message hash (z): {z}")
            
            # Verify the signature
            valid_signature = pub_key.verify(self.signature, z)
            
            if validators is None:
                return valid_signature
            return valid_signature and self.validator_pubkey.hex() in validators
                
        except Exception as e:
            print(f"Validation Error: {e}")
            import traceback
            traceback.print_exc()
            return False


    def generateBlockHash(self):
        block_data = self.serialise_with_signature()
        return hash256(block_data).hex()

    def to_dict(self):
        return {
            'version': self.version,
            'prevBlockHash': self.prevBlockHash.hex() if isinstance(self.prevBlockHash, bytes) else self.prevBlockHash,
            'merkleRoot': self.merkleRoot.hex() if isinstance(self.merkleRoot, bytes) else self.merkleRoot,
            'timestamp': self.timestamp,
            'validator_pubkey': self.validator_pubkey.hex() if isinstance(self.validator_pubkey, bytes) else self.validator_pubkey,
            # Properly handle signature based on its type
            'signature': self.signature.der().hex() if hasattr(self.signature, 'der') else 
                        (self.signature.hex() if isinstance(self.signature, bytes) else 
                        str(self.signature) if self.signature else ''),
            'blockHash': self.blockHash
        }