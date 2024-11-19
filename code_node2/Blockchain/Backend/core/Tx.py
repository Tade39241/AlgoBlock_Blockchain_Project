import sys
sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code_node2')
from Blockchain.Backend.core.script import Script
from Blockchain.Backend.util.util import int_to_little_endian, bytes_needed, decode_base58, little_endian_to_int, encode, hash256, read_varint

ZERO_HASH = b'\0' * 32
REWARD = 50

PRIV_KEY = '65404450352388753766478610327763040364888428740098085792097801913225805083733'
MINERS_ADDY = '1ALbtk4ocsg2Qb67aiZRegL5sdhQ1gW7FD'
SIG_HASH_ALL = 1

class Coinbase_tx:
    def __init__(self, BlockHeight):
        self.BlockHeight_in_little_endian = int_to_little_endian(BlockHeight,bytes_needed(BlockHeight))


    def coinbase_transaction(self):
        prev_tx = ZERO_HASH
        prev_index = 0xffffffff

        tx_ins =[]
        tx_ins.append(TxIn(prev_tx,prev_index))
        tx_ins[0].script_sig.cmds.append(self.BlockHeight_in_little_endian)

        tx_outs =[]
        target_amount = REWARD * 100000000
        target_h160 = decode_base58(MINERS_ADDY)
        target_script = Script.p2pkh_script(target_h160)
        tx_outs.append(TxOut(amount=target_amount,script_publickey=target_script))
        coinbaseTx= Tx(1,tx_ins,tx_outs,0)
        coinbaseTx.TxId = coinbaseTx.id()

        return coinbaseTx


class Tx:
    def __init__(self,version, tx_ins, tx_outs, locktime):
        self.version = version
        self.tx_ins = tx_ins
        self.tx_outs = tx_outs
        self.locktime = locktime

    def id(self):
        "human readable Tx ID"
        return self.hash().hex()
    
    def hash(self):
        "Binary Hash of serialisation"
        return hash256(self.serialise())[::-1]

    @classmethod
    def parse(cls, s):
        version = little_endian_to_int(s.read(4))
        num_inputs = read_varint(s)
        inputs = []
        for _ in range( num_inputs):
            inputs.append(TxIn.parse(s))
        num_outputs = read_varint(s)
        outputs = []
        for _ in range(num_outputs):
            outputs.append(TxOut.parse(s))
        locktime = little_endian_to_int(s.read(4))
        return cls(version, inputs, outputs, locktime)
    
    def serialise(self):
        result = int_to_little_endian(self.version, 4)
        result += encode(len(self.tx_ins))

        for tx_in in self.tx_ins:
            result += tx_in.serialise()
        
        result += encode(len(self.tx_outs))

        for tx_out in self.tx_outs:
            result += tx_out.serialise()
        
        result += int_to_little_endian(self.locktime, 4)
        return result

    def is_coinbase(self):
        "checks that there is only 1 input, checks prev_tx is b'\x00'*32,and prev_index is 0xfffffff "
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
        TxInList = []
        TxOutList = []
        cmds = []

        for tx_in in item['tx_ins']:
            for cmd in tx_in['script_sig']['cmds']:
                if tx_in['prev_tx'] == '0000000000000000000000000000000000000000000000000000000000000000':
                    cmds.append(int_to_little_endian(int(cmd), bytes_needed(int(cmd))))
                else:
                    if type(cmd) == int:
                        cmds.append(cmd)
                    else:
                        cmds.append(bytes.fromhex(cmd))
            TxInList.append(TxIn(bytes.fromhex(tx_in['prev_tx']),tx_in['prev_index'], Script(cmds))) 

        cmdsout = []

        for tx_out in item['tx_outs']:
            for cmd in tx_out['script_publickey']['cmds']:
                if type(cmd) == int:
                    cmdsout.append(cmd)
                else:
                    cmdsout.append(bytes.fromhex(cmd))
            TxOutList.append(TxOut(tx_out['amount'],Script(cmdsout)))
            cmdsout = []
        return cls(1, TxInList, TxOutList, 0)


                
    def to_dict(self):

        "converts both prev_tx Hash and Blockheight to hex, to let us store in file"

        for tx_index, tx_in in enumerate(self.tx_ins):
            if self.is_coinbase():
                tx_in.script_sig.cmds[0] = little_endian_to_int(tx_in.script_sig.cmds[0])
            
            tx_in.prev_tx = tx_in.prev_tx.hex()

            for index, cmd in enumerate(tx_in.script_sig.cmds):
                if isinstance(cmd, bytes):
                    tx_in.script_sig.cmds[index] = cmd.hex()
            
            tx_in.script_sig = tx_in.script_sig.__dict__
            self.tx_ins[tx_index] = tx_in.__dict__

        # if self.is_coinbase():
        #     self.tx_ins[0].prev_tx = self.tx_ins[0].prev_tx.hex()
        #     self.tx_ins[0].script_sig.cmds[0] = little_endian_to_int(self.tx_ins[0].script_sig.cmds[0])
        #     self.tx_ins[0].script_sig = self.tx_ins[0].script_sig.__dict__
        
        # self.tx_ins[0] = self.tx_ins[0].__dict__

        """
        convert Transaction output to dict
        # If there are numbers don't do anything
        # If value is in Bytes, convert it to hex
        # Loop through all the TxOut Objects and convert them into dict
        """

        # self.tx_outs[0].script_publickey.cmds[2] = self.tx_outs[0].script_publickey.cmds[2].hex()
        # self.tx_outs[0].script_publickey = self.tx_outs[0].script_publickey.__dict__
        # self.tx_outs[0] = self.tx_outs[0].__dict__

        for index, tx_out in enumerate(self.tx_outs):
            tx_out.script_publickey.cmds[2] = tx_out.script_publickey.cmds[2].hex()
            tx_out.script_publickey = tx_out.script_publickey.__dict__
            self.tx_outs[index] = tx_out.__dict__

        return self.__dict__

    def sig_hash(self, input_index, script_pubkey):
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

        s += int_to_little_endian(self.locktime,4)
        s += int_to_little_endian(SIG_HASH_ALL,4)

        h256 = hash256(s)
        return int.from_bytes(h256,'big')
    
    def verify_input(self, input_index, script_pubkey):
        tx_in = self.tx_ins[input_index]
        z = self.sig_hash(input_index, script_pubkey)
        combined = tx_in.script_sig + script_pubkey
        return combined.evaluate(z)

    def sign_input(self, input_index,priv_key,script_pubkey):
        sig_hash_value = self.sig_hash(input_index, script_pubkey)
        der = priv_key.sign(sig_hash_value).der()
        sig = der + SIG_HASH_ALL.to_bytes(1,'big')
        sec = priv_key.point.sec()
        self.tx_ins[input_index].script_sig = Script([sig,sec])
        
class TxIn:
    def __init__(self, prev_tx, prev_index, script_sig = None, sequence = 0xffffffff):
        self.prev_tx = prev_tx
        self.prev_index = prev_index
        if script_sig is None:
            self.script_sig = Script()
            # print(self.script_sig.__dict__)
        else:
            self.script_sig = script_sig
        self.sequence = sequence

    def serialise(self):
        # print(self.script_sig)
        result = self.prev_tx[::-1]
        result += int_to_little_endian(self.prev_index, 4)
        result += self.script_sig.serialise()
        result += int_to_little_endian(self.sequence, 4)
        return result
    
    @classmethod
    def parse(cls, s):
        prev_tx=s.read(32)[::-1]
        prev_index = little_endian_to_int(s.read(4))
        script_sig = Script.parse(s)
        sequence = little_endian_to_int(s.read(4))
        return cls(prev_tx, prev_index, script_sig, sequence)
    
class TxOut:
    def __init__(self, amount, script_publickey):
        self.amount = amount
        self.script_publickey = script_publickey

    def serialise(self):
        result = int_to_little_endian(self.amount, 8)
        result += self.script_publickey.serialise()
        return result
    
    @classmethod
    def parse(cls, s):
        amount = little_endian_to_int(s.read(8))
        script_publickey = Script.parse(s)
        return cls(amount, script_publickey)
