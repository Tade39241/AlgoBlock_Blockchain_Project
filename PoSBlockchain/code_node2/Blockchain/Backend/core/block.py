from Blockchain.Backend.core.EllepticCurve.EllepticCurve import Signature
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.util.util import int_to_little_endian, little_endian_to_int, encode, read_varint
from Blockchain.Backend.core.tx import Tx




class Block:
    """
    Block is a storage container that stores transactions
    """

    command = b'block'

    def __init__(self, Height, Blocksize, BlockHeader, TxCount, Txs, Signature=None):
        self.Height = Height
        self.Blocksize = Blocksize
        self.BlockHeader = BlockHeader
        self.TxCount = TxCount
        self.Txs = Txs
        self.Signature = Signature

    @classmethod
    def to_obj(cls, data):
        # If 'data' is already an instance of Block, just return it.
        if isinstance(data, cls):
            return data

        # If data is a list, assume the block dictionary is its first element.
        if isinstance(data, list):
            block_dict = data[0]
        elif isinstance(data, dict):
            block_dict = data
        else:
            raise TypeError("Unsupported type for Block.to_obj; expected dict or list.")

        header_data = block_dict['BlockHeader']
        sig_hex = header_data.get('signature')
        print(f"DEBUG: BlockHeader signature field type: {type(sig_hex)}, value: {sig_hex}")
        if sig_hex:
            sig_bytes = bytes.fromhex(sig_hex)
            try:
                signature = Signature.parse(sig_bytes)
                print(signature)
            except Exception as e:
                print(f"Error parsing signature from dict: {e}")
                signature = None
        else:
            signature = None

        block_header = BlockHeader(
            header_data['version'],
            bytes.fromhex(header_data['prevBlockHash']),
            bytes.fromhex(header_data['merkleRoot']),
            header_data['timestamp'],
            bytes.fromhex(header_data['validator_pubkey']),
            signature
        )
        block_header.blockHash = header_data['blockHash']

        # Reconstruct transactions.
        Transactions = []
        for tx in block_dict['Txs']:
            Transactions.append(Tx.to_obj(tx))

        # Return a new Block instance.
        return cls(
            block_dict['Height'],
            block_dict['Blocksize'],
            block_header,
            len(Transactions),
            Transactions
        )
    
    @classmethod
    def parse(cls, s):
        print("[DEBUG/BLOCK PARSE] Starting block parse...")
        try:
            Height = little_endian_to_int(s.read(4))
            print(f"  [DEBUG/BLOCK PARSE] Parsed Height: {Height}")
            BlockSize = little_endian_to_int(s.read(4)) # Reading BlockSize field
            print(f"  [DEBUG/BLOCK PARSE] Parsed BlockSize: {BlockSize}") # We read it, but don't use it for parsing Txs

            blockHeader = BlockHeader.parse(s)
            print(f"  [DEBUG/BLOCK PARSE] Parsed BlockHeader. Hash: {blockHeader.blockHash[:8] if hasattr(blockHeader, 'blockHash') else 'N/A'}")

            # --- Check Tx Count Decoding ---
            try:
                numTxs = read_varint(s) # Use read_varint explicitly
                print(f"  [DEBUG/BLOCK PARSE] Parsed Tx Count (VarInt): {numTxs}")
            except NameError:
                print("[ERROR/BLOCK PARSE] 'read_varint' is not defined or imported!")
                raise # Stop if decoding function missing
            except Exception as e:
                print(f"[ERROR/BLOCK PARSE] Failed to read varint for tx count: {e}")
                raise # Stop on error
            # -----------------------------

            Txs = []
            print(f"  [DEBUG/BLOCK PARSE] Attempting to parse {numTxs} transactions...")
            for i in range (numTxs):
                print(f"    [DEBUG/BLOCK PARSE] Parsing Tx {i+1}/{numTxs}...")
                try:
                    tx_obj = Tx.parse(s)
                    print(f"      [DEBUG/BLOCK PARSE] Parsed Tx {i+1} ID: {tx_obj.id()}")
                    Txs.append(tx_obj)
                except Exception as e:
                    print(f"[ERROR/BLOCK PARSE] Failed to parse transaction at index {i}: {e}")
                    import traceback
                    traceback.print_exc() # Show where in Tx.parse it failed
                    # Decide how to handle: raise error? return partially parsed block?
                    raise # Stop parsing block if a tx fails

            print(f"  [DEBUG/BLOCK PARSE] Successfully parsed {len(Txs)} transactions.")

            # Note: We pass the original BlockSize read from the stream,
            # even though the actual size might differ slightly if calculation was off.
            # The receiving node might recalculate size if needed.
            return cls(Height, BlockSize, blockHeader, numTxs, Txs)

        except Exception as e:
            print(f"[ERROR/BLOCK PARSE] General error during block parsing: {e}")
            import traceback
            traceback.print_exc()
            # Depending on where the stream 's' is, this might leave it partially read.
            # Consider returning None or raising a specific BlockParseError.
            raise # Re-raise the exception


    
    # @classmethod
    # def parse(cls, s):
    #     Height = little_endian_to_int(s.read(4))
    #     BlockSize = little_endian_to_int(s.read(4))
    #     blockHeader = BlockHeader.parse(s)
    #     numTxs = read_varint(s)

    #     Txs = []

    #     for _ in range (numTxs):
    #         Txs.append(Tx.parse(s))

    #     return cls(Height, BlockSize, blockHeader, numTxs, Txs)
    
    def serialise(self):
        # --- Logging TxIDs ---
        try:
            tx_ids_hex = [tx.id() for tx in self.Txs] # Calculate IDs first
            # print(f"[DEBUG/BLOCK] Block {self.Height} TxIDs being serialized: {tx_ids_hex}") # Log the list
        except Exception as e:
            print(f"[ERROR/BLOCK SERIALIZE] Failed to get TxIDs for logging: {e}")
        # --------------------

        result = int_to_little_endian(self.Height, 4)
        result += int_to_little_endian(self.Blocksize, 4) # Using self.Blocksize attribute
        result += self.BlockHeader.serialise_with_signature() # Should include the final signature

        # --- Check Tx Count Encoding ---
        try:
            tx_count = len(self.Txs)
            result += encode(tx_count) # Use encode_varint explicitly
            # print(f"[DEBUG/BLOCK SERIALIZE] Serialized Tx Count: {tx_count} -> VarInt: {encode(tx_count).hex()}")
        except NameError:
            print("[ERROR/BLOCK SERIALIZE] 'encode_varint' is not defined or imported!")
            raise # Stop if encoding function missing
        except Exception as e:
            print(f"[ERROR/BLOCK SERIALIZE] Failed to encode tx count: {e}")
            raise # Stop on error
        # -----------------------------

        # --- Serialize Transactions ---
        try:
            for i, tx in enumerate(self.Txs):
                 tx_bytes = tx.serialise()
                #  print(f"  [DEBUG/BLOCK SERIALIZE] Serializing Tx {i} (ID: {tx.id()}): {len(tx_bytes)} bytes")
                 result += tx_bytes
        except Exception as e:
             print(f"[ERROR/BLOCK SERIALIZE] Failed to serialize transaction at index {i}: {e}")
             raise # Stop on error
        # ----------------------------

        # --- Verify Block Size (Optional but recommended) ---
        # Re-calculate actual size vs stored self.Blocksize
        actual_size = len(result)
        if hasattr(self, 'Blocksize') and self.Blocksize != actual_size:

            self.Blocksize = actual_size # Update Blocksize to match actual size
            #  print(f"[WARNING/BLOCK SERIALIZE] Stored Blocksize ({self.Blocksize}) != Actual Serialized Size ({actual_size}) for Block {self.Height}")
             # You might choose to update self.Blocksize here or just log it.
             # For sending, using the actual size might be better.
             # Re-create the size field? This adds complexity. Let's stick to logging for now.
        # ----------------------------------------------------

        # print(f"[DEBUG/BLOCK] Block serialized bytes: {result.hex()}") # Optional full hex log
        return result


    # def serialise(self):
    #     print(f"[DEBUG/BLOCK] Block {self.Height} TxIDs: {[tx.id() for tx in self.Txs]}")
    #     result = int_to_little_endian(self.Height, 4)
    #     result += int_to_little_endian(self.Blocksize, 4)
    #     result += self.BlockHeader.serialise_with_signature()
    #     result += encode(len(self.Txs))

    #     for tx in self.Txs:
    #         result += tx.serialise()

    #     print(f"[DEBUG/BLOCK] Block serialized bytes: {result.hex()}")
    #     return result
        
    
    # def to_dict(self):
    #     dt = self.__dict__
    #     if hasattr(self.BlockHeader, "__dict__"):
    #         self.BlockHeader = self.BlockHeader.__dict__
    #         # Do NOT call .to_dict() on BlockHeader or Txs
    #     return dt

    def to_dict(self):
        # Create a shallow copy to avoid modifying the original __dict__
        dt = self.__dict__.copy()

        # Convert BlockHeader object to dict *in the copy*
        if isinstance(self.BlockHeader, BlockHeader):
             # Assuming BlockHeader has a suitable to_dict or __dict__
             try:
                  # Prefer a dedicated method if it exists
                  dt['BlockHeader'] = self.BlockHeader.to_dict()
             except AttributeError:
                  # Fallback to __dict__ if necessary
                  dt['BlockHeader'] = self.BlockHeader.__dict__
        elif isinstance(self.BlockHeader, dict):
             # If it's already a dict, keep it as is in the copy
             dt['BlockHeader'] = self.BlockHeader
        # else: handle other unexpected types if necessary

        # Convert Tx objects to dicts *in the copy*
        tx_list_of_dicts = []
        if isinstance(self.Txs, list):
            for tx in self.Txs:
                if isinstance(tx, Tx):
                     try:
                          # Prefer a dedicated method if it exists
                          tx_list_of_dicts.append(tx.to_dict())
                     except AttributeError:
                          # Fallback to __dict__ if necessary
                          tx_list_of_dicts.append(tx.__dict__)
                elif isinstance(tx, dict):
                     tx_list_of_dicts.append(tx) # Already a dict
                # else: handle other unexpected types
        dt['Txs'] = tx_list_of_dicts

        # Convert Signature object if it exists
        if hasattr(self, 'Signature') and isinstance(self.Signature, Signature):
             # Assuming Signature needs hex representation
             dt['Signature'] = self.Signature.hex()
        elif isinstance(self.Signature, str):
             dt['Signature'] = self.Signature # Already a string/hex

        return dt