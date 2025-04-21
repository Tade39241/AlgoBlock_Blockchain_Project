"""
The code defines a way to construct a standard Bitcoin P2PKH script, 
which is fundamental for creating transactions that send coins to a specific address.
"""

from Blockchain.Backend.util.util import encode_base58, int_to_little_endian, little_endian_to_int, encode, read_varint, decode_base58
from Blockchain.Backend.core.EllepticCurve.op import OP_CODE_FUNCTION, op_checksig, op_dup, op_checklocktimeverify, op_drop


class Script:
    def __init__(self, cmds=None):
        if cmds is None:
            self.cmds = []
        else:
            self.cmds = cmds
        
    def __add__(self,other):
        return Script(self.cmds + other.cmds)
    
    def serialise(self):
        #initialise what we return
        result = b''
        # iterate through each command
        for cmd in self.cmds:
            #if cmd is an int then its an opcode
            if type(cmd) == int:
                #turn cmd into single byte integer
                result += int_to_little_endian(cmd, 1)
            else:
                # otherwise it is an element
                # get the length in bytes
                length = len(cmd)
                #for large lengths, use a pushdata opdcode
                if length < 75:
                    result += int_to_little_endian(length,1)
                elif length > 75 and length < 0x100:
                    # 76 is pushdata1
                    result += int_to_little_endian(76,1)
                    result += int_to_little_endian(length, 1)
                elif length >= 0x100 and length <= 520:
                    # 77 is pushdata2
                    result += int_to_little_endian(77,1)
                    result += int_to_little_endian(length, 2)
                else:
                    raise ValueError("CMD is too long")
                result+=cmd
        # get total length
        total = len(result)
        return encode(total)+result
    
    @classmethod
    def parse(cls, s):
        length = read_varint(s)
        cmds = []
        count = 0
        while count < length:
            current = s.read(1)
            count +=1
            current_byte = current[0]

            if current_byte >=1 and current_byte <= 75:
                n = current_byte
                cmds.append(s.read(n))
                count += n
            elif current_byte == 76:
                data_length = little_endian_to_int(s.read(1))
                cmds.append(s.read(data_length))
                count += data_length + 1
            elif current_byte == 77:
                data_length = little_endian_to_int(s.read(2))
                cmds.append(s.read(data_length))
                count += data_length + 2
            else:
                op_code = current_byte
                cmds.append(op_code)
        if count != length:
            raise SyntaxError('parsing script failed')
        return cls(cmds)
    
        
    def evaluate(self,z):
        cmds = self.cmds[:]
        stack = []

        while len(cmds) > 0:
            cmd = cmds.pop(0)

            if type(cmd) == int:
                operation  = OP_CODE_FUNCTION[cmd]

                if cmd == 172:
                    if not operation(stack,z):
                        print("Error in verifying signature")
                        return False
                
                elif not operation(stack):
                    print("Error in verifying signature")
                    return False

            else:
                stack.append(cmd)
        return True


    @classmethod
    def p2pkh_script(cls,h160):
        return cls([0x76,0xa9, h160, 0x88, 0xac])
    
    @classmethod
    def from_dict(cls, d):
        # If your script stores commands as a list of hex strings, convert them back to bytes or int as needed
        cmds = []
        for cmd in d.get('cmds', []):
            if isinstance(cmd, str):
                try:
                    # Try to decode as hex, fallback to int if not hex
                    cmds.append(bytes.fromhex(cmd))
                except ValueError:
                    try:
                        cmds.append(int(cmd))
                    except Exception:
                        cmds.append(cmd)
            else:
                cmds.append(cmd)
        return cls(cmds)

class StakingScript(Script):
    def __init__(self, address, lock_time):
        super().__init__()
        # Decode the Base58 address (20-byte hash160)
        decoded_hash160 = decode_base58(address)
        if len(decoded_hash160) != 20:
            raise ValueError("Invalid address length after Base58 decoding.")
        
        # Convert the lock_time (int) to bytes.
        # You can use 4 or 8 bytes. Here we use 8 for safety.
        lock_bytes = lock_time.to_bytes(8, 'big')

        # For staking, let’s store:
        #   - b'\x00' as a staking identifier
        #   - The user’s hash160
        #   - The lock_time bytes
        self.cmds = [
            b'\x00',        # staking marker
            decoded_hash160,# who can claim
            lock_bytes      # the locktime
        ]

    def is_staking(self):
        return True

    def is_staking(self):
        return True