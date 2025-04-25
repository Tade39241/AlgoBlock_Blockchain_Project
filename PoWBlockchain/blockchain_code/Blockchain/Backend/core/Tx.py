import sys
import traceback
sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoWBlockchain/blockchain_code')
from Blockchain.Backend.core.script import Script
from Blockchain.Backend.util.util import int_to_little_endian, bytes_needed, decode_base58, little_endian_to_int, encode, hash256, read_varint
import logging # Add logging
import copy # Add copy

logger = logging.getLogger(__name__) # Setup logger

ZERO_HASH = b'\0' * 32
REWARD = 50
SATOSHI = 100000000

# PRIV_KEY = '65404450352388753766478610327763040364888428740098085792097801913225805083733'
# MINERS_ADDY = '1ALbtk4ocsg2Qb67aiZRegL5sdhQ1gW7FD'
SIG_HASH_ALL = 1

###############################################################################
# COINBASE TRANSACTION
###############################################################################

class Coinbase_tx:
    def __init__(self, BlockHeight, miner_address):
        # Store the BlockHeight in little-endian bytes.
        self.BlockHeight_in_little_endian = int_to_little_endian(BlockHeight,bytes_needed(BlockHeight))
        # Store the miner's address.
        self.miner_address = miner_address


    def coinbase_transaction(self):
        try:
            prev_tx = ZERO_HASH
            prev_index = 0xffffffff

            # Build the transaction input.
            tx_ins =[]
            tx_ins.append(TxIn(prev_tx,prev_index))
            # Append the block height (in little-endian bytes) as the first push in script_sig.
            tx_ins[0].script_sig.cmds.append(self.BlockHeight_in_little_endian)
            print(f"DEBUG Coinbase: TxIn created. ScriptSig cmds: {tx_ins[0].script_sig.cmds}") # Debug log

            # Build the transaction output.
            tx_outs =[]
            target_amount = REWARD * SATOSHI
            # --- Add specific try/except for decoding/script ---
            try:
                print(f"DEBUG Coinbase: Decoding address: {self.miner_address}") # Debug log
                target_h160 = decode_base58(self.miner_address)
                print(f"DEBUG Coinbase: Creating p2pkh script for h160: {target_h160.hex()}") # Debug log
                target_script = Script.p2pkh_script(target_h160)
                print(f"DEBUG Coinbase: Script created: {target_script.cmds}") # Debug log
            except Exception as e_script:
                print(f"ERROR Coinbase: Failed during address decode or script creation: {e_script}")
                traceback.print_exc()
                return None # Indicate failure
            # --- End specific try/except ---

            # target_h160 = decode_base58(self.miner_address)
            # target_script = Script.p2pkh_script(target_h160)
            tx_outs.append(TxOut(amount=target_amount,script_publickey=target_script))
            print(f"DEBUG Coinbase: TxOut created. Amount: {target_amount}") # Debug log

            # Create the transaction (version 1, coinbase has locktime 0).
            coinbaseTx= Tx(1,tx_ins,tx_outs,0)
            print("DEBUG Coinbase: Tx object created.") # Debug log
            # --- Add specific try/except for TxID ---
            try:
                print("DEBUG Coinbase: Calculating TxID...") # Debug log
                coinbaseTx.TxId = coinbaseTx.id() # Use property setter if available, else direct assignment
                print(f"DEBUG Coinbase: TxID calculated: {coinbaseTx.TxId}") # Debug log
            except Exception as e_id:
                print(f"ERROR Coinbase: Failed during TxID calculation (serialise?): {e_id}")
                traceback.print_exc()
                return None # Indicate failure
            # --- End specific try/except ---
            # Store the computed TxID in the coinbase transaction.
            # coinbaseTx.TxId = coinbaseTx.id()

            return coinbaseTx
        except Exception as e_main: # Catch any other unexpected errors
            print(f"ERROR Coinbase: Unexpected error in coinbase_transaction: {e_main}")
            traceback.print_exc()
            return None # Indicate failure
        
    
###############################################################################
# TRANSACTION, TxIn, and TxOut CLASSES
###############################################################################

class Tx:
    command = b'tx'

    def __init__(self, version, tx_ins, tx_outs, locktime):
        self.version = version        # 4-byte little-endian integer.
        self.tx_ins = tx_ins          # List of TxIn objects.
        self.tx_outs = tx_outs        # List of TxOut objects.
        self.locktime = locktime      # 4-byte little-endian integer.
    
    
    @property
    def txid(self):
        """Always compute the TxID from the serialized bytes."""
        return self.id()

    def id(self):
        
        """
        Return the human-readable TxID.
        The TxID is the double-SHA256 of the serialized transaction bytes,
        then reversed so that the most-significant byte is first.
        """
        return self.hash().hex()
    
    def hash(self):

        """
        Compute the binary hash (double-SHA256) of the serialized transaction.
        Note: We reverse the final digest for display purposes.
        """
        # Compute the double-SHA256 digest on the serialized byte representation.

        return hash256(self.serialise())[::-1]

    @classmethod
    def parse(cls, s):
        """
        Parse a byte stream (e.g. a BytesIO object) into a Tx object.
        The fields are read in the exact order that they are written in serialise().
        """
        version = little_endian_to_int(s.read(4))

        # Read the number of inputs (using varint encoding).
        num_inputs = read_varint(s)
        inputs = []
        for _ in range(num_inputs):
            inputs.append(TxIn.parse(s))

        # Read the number of outputs.
        num_outputs = read_varint(s)
        outputs = []
        for _ in range(num_outputs):
            outputs.append(TxOut.parse(s))

        # Read the 4-byte little-endian locktime.
        locktime = little_endian_to_int(s.read(4))
        return cls(version, inputs, outputs, locktime)
    
    def serialise(self):
        """
        Serialize the transaction into bytes, writing each field in the correct order.
        The order is:
          1. Version (4 bytes, little-endian)
          2. Input count (varint)
          3. Each TxIn (serialized)
          4. Output count (varint)
          5. Each TxOut (serialized)
          6. Locktime (4 bytes, little-endian)
        """
        result = b''
        result += int_to_little_endian(self.version, 4)

        # Encode the number of inputs as a varint.
        result += encode(len(self.tx_ins))
        for tx_in in self.tx_ins:
            result += tx_in.serialise()
        
        # Encode the number of outputs as a varint.
        result += encode(len(self.tx_outs))
        for tx_out in self.tx_outs:
            result += tx_out.serialise()
        
        result += int_to_little_endian(self.locktime, 4)
        # Uncomment for debugging:
        # print(f"DEBUG: Serialized transaction bytes: {result.hex()}")
        return result

    def is_coinbase(self):
        """
        Checks if the transaction is a coinbase transaction.
         - Must have exactly 1 input.
         - The input's prev_tx must be ZERO_HASH.
         - The input's prev_index must be 0xffffffff.
        """
         
        if len(self.tx_ins)!=1:
            return False
        
        first_input = self.tx_ins[0]

        if first_input.prev_tx != b'\x00'*32:
            return False
        
        if first_input.prev_index != 0xffffffff:
            return False

        return True
    
        # ... (inside Tx class) ...

    @classmethod
    def to_obj(cls, item):
        """
        Convert a dictionary representation of a transaction to a Tx object.
        Handles potential errors and reads version/locktime from the dictionary.
        Expects coinbase height in script_sig['cmds'] to be an integer.
        """
        try:
            TxInList = []
            TxOutList = []

            # --- Process Inputs ---
            for tx_in_dict in item.get('tx_ins', []): # Use .get for safety
                cmds = [] # Initialize cmds list INSIDE the loop for each TxIn
                script_sig_dict = tx_in_dict.get('script_sig', {})
                script_cmds = script_sig_dict.get('cmds', [])
                prev_tx_hex = tx_in_dict.get('prev_tx', '')

                for cmd in script_cmds:
                    # Handle Coinbase specific command (expecting height as int)
                    if prev_tx_hex == ZERO_HASH.hex(): # Compare with ZERO_HASH hex
                        if isinstance(cmd, int): # <<<< EXPECTING INT HERE
                            try:
                                # Convert the integer height to bytes for the Script object
                                height = cmd
                                cmds.append(int_to_little_endian(height, bytes_needed(height)))
                            except Exception as e:
                                logger.error(f"Error converting coinbase height int {cmd} to bytes: {e}")
                                continue # Skip this command if conversion fails
                        else:
                            # Log if coinbase cmd is not an int as expected
                            logger.warning(f"Unexpected type for coinbase script command: {type(cmd)}, value: {cmd}. Expected int.")
                            # Optionally try to handle string hex '07' if needed for backward compatibility?
                            # if isinstance(cmd, str): try bytes.fromhex?
                            continue # Skip non-integer command for coinbase

                    # Handle regular script commands (data as hex string, opcodes as int)
                    else:
                        if isinstance(cmd, int):
                            cmds.append(cmd) # Assume int represents an opcode
                        elif isinstance(cmd, str):
                            try:
                                cmds.append(bytes.fromhex(cmd)) # Assume string is hex data
                            except ValueError:
                                logger.error(f"Invalid hex string in script command: {cmd}")
                                continue # Skip invalid command
                        # No need to handle bytes here as JSON won't contain raw bytes
                        else:
                             logger.warning(f"Unsupported type in script command: {type(cmd)}, value: {cmd}")
                             continue # Skip unsupported type

                # Create TxIn object
                prev_tx_bytes = bytes.fromhex(prev_tx_hex) if prev_tx_hex else b''
                prev_index = tx_in_dict.get('prev_index', 0xffffffff) # Default if missing
                TxInList.append(TxIn(prev_tx_bytes, prev_index, Script(cmds))) # Script gets height as bytes

            # --- Process Outputs ---
            # (No changes needed for TxOut processing)
            for tx_out_dict in item.get('tx_outs', []):
                cmdsout = []
                script_pubkey_dict = tx_out_dict.get('script_pubkey', {}) # Renamed for clarity
                script_cmds = script_pubkey_dict.get('cmds', [])

                for cmd in script_cmds:
                    if isinstance(cmd, int):
                        cmdsout.append(cmd)
                    elif isinstance(cmd, str):
                        try:
                            cmdsout.append(bytes.fromhex(cmd))
                        except ValueError:
                            logger.error(f"Invalid hex string in script_pubkey command: {cmd}")
                            continue
                    else:
                         logger.warning(f"Unsupported type in script_pubkey command: {type(cmd)}, value: {cmd}")
                         continue

                amount = tx_out_dict.get('amount', 0)
                TxOutList.append(TxOut(amount, Script(cmdsout)))

            # Read version and locktime from the dictionary, default if missing
            version = item.get('version', 1)
            locktime = item.get('locktime', 0)

            return cls(version, TxInList, TxOutList, locktime)

        except KeyError as e:
            logger.error(f"Missing key in transaction dictionary for Tx.to_obj: {e}", exc_info=True)
            raise ValueError(f"Invalid transaction dictionary format: Missing key {e}") from e
        except Exception as e:
            logger.error(f"Error creating Tx object from dictionary: {e}", exc_info=True)
            raise # Re-raise other unexpected errors


        except KeyError as e:
            logger.error(f"Missing key in transaction dictionary for Tx.to_obj: {e}", exc_info=True)
            raise ValueError(f"Invalid transaction dictionary format: Missing key {e}") from e
        except Exception as e:
            logger.error(f"Error creating Tx object from dictionary: {e}", exc_info=True)
            raise # Re-raise other unexpected errors

    
    # @classmethod
    # def to_obj(cls, item):
    #     """
    #     Convert a dictionary representation of a transaction to a Tx object.
    #     """
        
    #     TxInList = []
    #     TxOutList = []
    #     cmds = []

    #     for tx_in in item['tx_ins']:
    #         for cmd in tx_in['script_sig']['cmds']:
    #             if tx_in['prev_tx'] == '0000000000000000000000000000000000000000000000000000000000000000':
    #                 cmds.append(int_to_little_endian(int(cmd), bytes_needed(int(cmd))))
    #             else:
    #                 # If the command is an int leave it or convert from hex if string.
    #                 if isinstance(cmd, int):
    #                     cmds.append(cmd)
    #                 else:
    #                     cmds.append(bytes.fromhex(cmd))
    #         TxInList.append(TxIn(bytes.fromhex(tx_in['prev_tx']), tx_in['prev_index'], Script(cmds))) 

    #     cmdsout = []
    #     for tx_out in item['tx_outs']:
    #         for cmd in tx_out['script_publickey']['cmds']:
    #             if isinstance(cmd, int):
    #                 cmdsout.append(cmd)
    #             else:
    #                 cmdsout.append(bytes.fromhex(cmd))
    #         TxOutList.append(TxOut(tx_out['amount'],Script(cmdsout)))
    #         cmdsout = []
    #     return cls(1, TxInList, TxOutList, 0)


    # def to_dict(self):
    #     """
    #     Convert the transaction object to a dictionary.
    #     This conversion includes converting bytes fields (such as prev_tx and script commands)
    #     to hex strings for storage.
    #     """

    #     for tx_index, tx_in in enumerate(self.tx_ins):
    #         if self.is_coinbase():
    #             tx_in.script_sig.cmds[0] = little_endian_to_int(tx_in.script_sig.cmds[0])
    #         tx_in.prev_tx = tx_in.prev_tx.hex()

    #         for index, cmd in enumerate(tx_in.script_sig.cmds):
    #             if isinstance(cmd, bytes):
    #                 tx_in.script_sig.cmds[index] = cmd.hex()
    #         tx_in.script_sig = tx_in.script_sig.__dict__
    #         self.tx_ins[tx_index] = tx_in.__dict__

    #     """
    #     convert Transaction output to dict
    #     # If there are numbers don't do anything
    #     # If value is in Bytes, convert it to hex
    #     # Loop through all the TxOut Objects and convert them into dict
    #     """

    #     for index, tx_out in enumerate(self.tx_outs):
    #         # Make sure to convert any bytes in the script to hex.
    #         tx_out.script_publickey.cmds[2] = tx_out.script_publickey.cmds[2].hex()
    #         tx_out.script_publickey = tx_out.script_publickey.__dict__
    #         self.tx_outs[index] = tx_out.__dict__

    #     return self.__dict__
    
    # --- REVISED to_dict (Non-mutating) ---
    def to_dict(self):
        """Converts the transaction object to a dictionary suitable for JSON serialization."""
        tx_ins_list = []
        for tx_in in self.tx_ins:
            # Get the standard dictionary representation from TxIn.to_dict()
            tx_in_dict = tx_in.to_dict()

            # --- Special handling for Coinbase Input ---
            # Check if this is a coinbase input (prev_tx is all zeros)
            if tx_in.prev_tx == ZERO_HASH:
                script_sig_dict = tx_in_dict.get('script_sig', {})
                cmds = script_sig_dict.get('cmds', [])
                # If cmds list exists and first element is a string (hex from Script.to_dict)
                if cmds and isinstance(cmds[0], str):
                    try:
                        # Convert the first element (hex height) back to bytes, then to int
                        height_bytes = bytes.fromhex(cmds[0])
                        height_int = little_endian_to_int(height_bytes)
                        # Replace the hex string with the integer in the dictionary's cmds list
                        # Assumes coinbase script_sig only contains height, or height first.
                        # If other elements exist, keep them (though unlikely for standard coinbase)
                        modified_cmds = [height_int] + cmds[1:]
                        tx_in_dict['script_sig']['cmds'] = modified_cmds
                        logger.debug(f"Coinbase TxIn {tx_in.prev_tx.hex()[:8]} script_sig['cmds'] converted height to int: {height_int}")
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Could not convert presumed coinbase height '{cmds[0]}' to int in to_dict: {e}")
                        # Keep the original hex string if conversion fails
            # --- End Special Handling ---

            tx_ins_list.append(tx_in_dict)

        # Process outputs (usually no special handling needed)
        tx_outs_list = [tx_out.to_dict() for tx_out in self.tx_outs]

        return {
            'version': self.version,
            'tx_ins': tx_ins_list,
            'tx_outs': tx_outs_list,
            'locktime': self.locktime,
            'TxId': self.id() # Include TxId for convenience
        }

    # --- REVISED/RENAMED from_dict (was to_obj) ---
    @classmethod
    def from_dict(cls, tx_dict):
        """
        Creates a Tx object from a dictionary representation.
        Assumes nested objects also have from_dict methods.
        """
        try:
            tx_ins = [TxIn.from_dict(tx_in_dict) for tx_in_dict in tx_dict.get('tx_ins', [])]
            tx_outs = [TxOut.from_dict(tx_out_dict) for tx_out_dict in tx_dict.get('tx_outs', [])]

            return cls(
                version=tx_dict['version'],
                tx_ins=tx_ins,
                tx_outs=tx_outs,
                locktime=tx_dict['locktime']
            )
        except KeyError as e:
            logger.error(f"Missing key in tx_dict for Tx.from_dict: {e}", exc_info=True)
            raise ValueError(f"Invalid transaction dictionary format: Missing key {e}") from e
        except Exception as e:
            logger.error(f"Error creating Tx from dict: {e}", exc_info=True)
            raise


    def sig_hash(self, input_index, script_pubkey):
        """
        Compute the signature hash for the input at input_index.
        This method rebuilds the transaction serialization with:
           - The script_pubkey replacing the script_sig for the input at input_index,
           - All other inputs having an empty script.
        Then appends the SIG_HASH_ALL flag.
        """

        s = int_to_little_endian(self.version,4)
        s += encode(len(self.tx_ins))

        for i,tx_in in enumerate(self.tx_ins):
            if i == input_index:
                s += TxIn(tx_in.prev_tx, tx_in.prev_index, script_pubkey).serialise()
            else:
                 s += TxIn(tx_in.prev_tx, tx_in.prev_index).serialise()
        
        s += encode(len(self.tx_outs))

        for tx_out in self.tx_outs:
            s += tx_out.serialise()

        s += int_to_little_endian(self.locktime, 4)
        s += int_to_little_endian(SIG_HASH_ALL, 4)

        h256 = hash256(s)
        return int.from_bytes(h256,'big')
    
    def verify_input(self, input_index, script_pubkey):
        """
        Verify the signature of the input at input_index.
        """
        tx_in = self.tx_ins[input_index]
        z = self.sig_hash(input_index, script_pubkey)
        combined = tx_in.script_sig + script_pubkey
        return combined.evaluate(z)

    def sign_input(self, input_index,priv_key,script_pubkey):
        """
        Sign the input at input_index using the provided private key.
        The signature is appended with SIG_HASH_ALL as a single byte.
        """
        sig_hash_value = self.sig_hash(input_index, script_pubkey)
        der = priv_key.sign(sig_hash_value).der()
        sig = der + SIG_HASH_ALL.to_bytes(1,'big')
        sec = priv_key.point.sec()
        self.tx_ins[input_index].script_sig = Script([sig,sec])
        return True
        
class TxIn:
    def __init__(self, prev_tx, prev_index, script_sig = None, sequence = 0xffffffff):
        self.prev_tx = prev_tx            # 32 bytes (stored in internal natural order)
        self.prev_index = prev_index      # 4-byte integer
        # If no script is provided, initialize with an empty Script.
        self.script_sig = script_sig if script_sig is not None else Script()
        self.sequence = sequence          # 4-byte integer (default 0xffffffff)

    def serialise(self):
        """
        Serialize the transaction input.
         1. prev_tx: 32 bytes (reversed for transmission)
         2. prev_index: 4 bytes little-endian
         3. script_sig: serialized with its own internal length prefix (varint)
         4. sequence: 4 bytes little-endian
        """
        result = b''
        # Reverse the prev_tx bytes so that the transmitted bytes match wire format.
        result += self.prev_tx[::-1]
        result += int_to_little_endian(self.prev_index, 4)
        result += self.script_sig.serialise()
        result += int_to_little_endian(self.sequence, 4)
        # Uncomment for debugging:
        # print(f"DEBUG: Serialized TxIn: {result.hex()}")
        return result
    
    @classmethod
    def parse(cls, s):
        """
        Parse a transaction input from the stream.
        Exactly the inverse of serialise().
        """
        # Read 32 bytes then reverse them to recover the internal prev_tx.
        prev_tx = s.read(32)[::-1]
        prev_index = little_endian_to_int(s.read(4))
        # The Script.parse method should take care of reading the varint length.
        script_sig = Script.parse(s)
        sequence = little_endian_to_int(s.read(4))
        return cls(prev_tx, prev_index, script_sig, sequence)
    
    def to_dict(self):
        """Converts TxInput to a dictionary, serializing bytes to hex."""
        # Assumes Script.to_dict exists and returns {'cmds': hex_string}
        script_sig_dict = self.script_sig.to_dict()
        return {
            'prev_tx': self.prev_tx.hex(),
            'prev_index': self.prev_index,
            'script_sig': script_sig_dict,
            'sequence': self.sequence
        }
    
     # --- ADDED from_dict ---
    @classmethod
    def from_dict(cls, tx_in_dict):
        """Creates a TxInput object from a dictionary."""
        try:
            # Assumes Script.from_dict exists and accepts {'cmds': hex_string}
            script_sig = Script.from_dict(tx_in_dict['script_sig'])
            prev_tx_bytes = bytes.fromhex(tx_in_dict['prev_tx'])

            return cls(
                prev_tx=prev_tx_bytes,
                prev_index=tx_in_dict['prev_index'],
                script_sig=script_sig,
                sequence=tx_in_dict['sequence']
            )
        except KeyError as e:
            logger.error(f"Missing key in tx_in_dict for TxIn.from_dict: {e}", exc_info=True)
            raise ValueError(f"Invalid TxInput dictionary format: Missing key {e}") from e
        except Exception as e:
            logger.error(f"Error creating TxIn from dict: {e}", exc_info=True)
            raise
    
class TxOut:
    def __init__(self, amount, script_publickey):
        self.amount = amount                      # 8-byte integer amount
        self.script_publickey = script_publickey  # Script object

    def serialise(self):
        """
        Serialize the transaction output.
         1. amount: 8 bytes little-endian
         2. script_publickey: serialized (includes its varint length prefix)
        """

        result = b''
        result += int_to_little_endian(self.amount, 8)
        result += self.script_publickey.serialise()
        # Uncomment for debugging:
        # print(f"DEBUG: Serialized TxOut: {result.hex()}")
        return result
    
    @classmethod
    def parse(cls, s):
        """
        Parse a transaction output from the stream.
        """
        amount = little_endian_to_int(s.read(8))
        script_publickey = Script.parse(s)
        return cls(amount, script_publickey)
    
    # --- ADDED to_dict ---
    def to_dict(self):
        # Ensure this correctly calls script_pubkey.to_dict()
        return {
            'amount': self.amount,
            'script_pubkey': self.script_publickey.to_dict() if self.script_publickey else None
        }

    @classmethod
    def from_dict(cls, tx_out_dict):
        amount = tx_out_dict.get('amount')
        script_pubkey_dict = tx_out_dict.get('script_pubkey')

        if script_pubkey_dict:
            try:
                script_pubkey_obj = Script.from_dict(script_pubkey_dict)
            except Exception as e:
                print(f"ERROR creating Script object in TxOut.from_dict: {e}")
                raise ValueError(f"Invalid script_pubkey data: {script_pubkey_dict}") from e
        else:
            script_pubkey_obj = None

        try:
            # --- FIX: Change keyword argument name ---
            return cls(amount=amount, script_publickey=script_pubkey_obj) # Use 'script_publickey'
            # --- End FIX ---
        except TypeError as e:
            print(f"ERROR calling TxOut constructor: {e}. Amount: {amount}, ScriptObj: {script_pubkey_obj}")
            raise
