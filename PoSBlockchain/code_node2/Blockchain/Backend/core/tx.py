import sys
sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/code_node2')
from Blockchain.Backend.core.script import Script
from Blockchain.Backend.util.util import int_to_little_endian, bytes_needed, decode_base58, little_endian_to_int, encode, hash256, read_varint

ZERO_HASH = b'\0' * 32
REWARD = 50

# In a configuration file or a constants section:
STAKING_ADDRESS = "1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh"  # example hard‐coded staking address
SIG_HASH_ALL = 1

###############################################################################
# COINBASE TRANSACTION
###############################################################################

class Coinbase_tx:
    def __init__(self, BlockHeight, validator_address=None):
        # Store the BlockHeight in little-endian bytes.
        self.BlockHeight_in_little_endian = int_to_little_endian(BlockHeight,bytes_needed(BlockHeight))
        # Store the reward address.
        # self.reward_address = validator_address if validator_address else STAKING_ADDRESS
        self.reward_address = validator_address
        print(f"Creating coinbase reward for address: {validator_address} sent to {self.reward_address}")

    def coinbase_transaction(self):
        prev_tx = ZERO_HASH
        prev_index = 0xffffffff

        # Build the transaction input.
        tx_ins =[]
        tx_ins.append(TxIn(prev_tx,prev_index))
        # Append the block height (in little-endian bytes) as the first push in script_sig.
        tx_ins[0].script_sig.cmds.append(self.BlockHeight_in_little_endian)

        # Build the transaction output.
        tx_outs =[]
        target_amount = REWARD * 100000000
        target_h160 = decode_base58(self.reward_address)
        target_script = Script.p2pkh_script(target_h160)
        tx_outs.append(TxOut(amount=target_amount,script_publickey=target_script))

        # Create the transaction (version 1, coinbase has locktime 0).
        coinbaseTx= Tx(1,tx_ins,tx_outs,0)

        # Store the computed TxID in the coinbase transaction.
        coinbaseTx.TxId = coinbaseTx.id()

        return coinbaseTx
    
    
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

    @classmethod
    def to_obj(cls, item):
        """
        Convert a dictionary representation of a transaction back into a Tx object.
        This method expects the dictionary to encode scripts and transaction fields in hex.
        """
        
        TxInList = []
        TxOutList = []
        cmds = []

        for tx_in in item['tx_ins']:
            for cmd in tx_in['script_sig']['cmds']:
                if tx_in['prev_tx'] == '0000000000000000000000000000000000000000000000000000000000000000':
                    cmds.append(int_to_little_endian(int(cmd), bytes_needed(int(cmd))))
                else:
                    # If the command is an int leave it or convert from hex if string.
                    if isinstance(cmd, int):
                        cmds.append(cmd)
                    else:
                        cmds.append(bytes.fromhex(cmd))
            TxInList.append(TxIn(bytes.fromhex(tx_in['prev_tx']), tx_in['prev_index'], Script(cmds))) 

        cmdsout = []
        
        for tx_out in item['tx_outs']:
            for cmd in tx_out['script_publickey']['cmds']:
                if isinstance(cmd, int):
                    cmdsout.append(cmd)
                else:
                    cmdsout.append(bytes.fromhex(cmd))
            TxOutList.append(TxOut(tx_out['amount'],Script(cmdsout)))
            cmdsout = []
        return cls(1, TxInList, TxOutList, 0)

    def to_dict(self):
        """
        Convert the transaction object to a dictionary.
        This conversion includes converting bytes fields (such as prev_tx and script commands)
        to hex strings for storage.
        """

        for tx_index, tx_in in enumerate(self.tx_ins):
            if self.is_coinbase():
                tx_in.script_sig.cmds[0] = little_endian_to_int(tx_in.script_sig.cmds[0])
            tx_in.prev_tx = tx_in.prev_tx.hex()

            for index, cmd in enumerate(tx_in.script_sig.cmds):
                if isinstance(cmd, bytes):
                    tx_in.script_sig.cmds[index] = cmd.hex()
            tx_in.script_sig = tx_in.script_sig.__dict__
            self.tx_ins[tx_index] = tx_in.__dict__

        """
        convert Transaction output to dict
        # If there are numbers don't do anything
        # If value is in Bytes, convert it to hex
        # Loop through all the TxOut Objects and convert them into dict
        """
        from Blockchain.Backend.core.script import StakingScript

        for index, tx_out in enumerate(self.tx_outs):
            cmds = tx_out.script_publickey.cmds
            if len(cmds) >= 3:
                # Make sure to convert any bytes in the script to hex.
                tx_out.script_publickey.cmds[2] = tx_out.script_publickey.cmds[2].hex()
                tx_out.script_publickey = tx_out.script_publickey.__dict__
                self.tx_outs[index] = tx_out.__dict__
            elif len(cmds) == 2:
                new_cmds = []
                for cmd in cmds:
                    if isinstance(cmd, bytes):
                        new_cmds.append(cmd.hex())
                    else:
                        new_cmds.append(cmd)
                tx_out.script_publickey.cmds = new_cmds

        return self.__dict__

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
    
    def is_coinbase_transaction(tx):
        # Assuming ZERO_HASH is defined (e.g., '00...00')
        if not tx.tx_ins or len(tx.tx_ins) == 0:
            return False
        coinbase_indicator = (tx.tx_ins[0].prev_tx.hex() == ZERO_HASH or 
                            tx.tx_ins[0].prev_index == 0xffffffff)
        return coinbase_indicator
        
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
    
    @classmethod
    def from_dict(cls, d):
        script = d['script_publickey']
        # If script is a dict, extract cmds
        cmds = script.get('cmds', script) if isinstance(script, dict) else script
        # StakingScript: cmds[0] == b'\x00'
        if isinstance(cmds, list) and len(cmds) == 3 and cmds[0] == b'\x00':
            from Blockchain.Backend.core.script import StakingScript
            script_obj = StakingScript.from_dict(script)
        else:
            from Blockchain.Backend.core.script import Script
            script_obj = Script.from_dict(script)
        return cls(
            amount=d['amount'],
            script_publickey=script_obj
        )