"""
The code defines a way to construct a standard Bitcoin P2PKH script, 
which is fundamental for creating transactions that send coins to a specific address.
"""

from Blockchain.Backend.util.util import encode_base58, int_to_little_endian, little_endian_to_int, encode, read_varint, decode_base58
from Blockchain.Backend.core.EllepticCurve.op import OP_CODE_FUNCTION, op_checksig, op_dup, op_checklocktimeverify, op_drop
import hashlib


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
        # print(f"[DEBUG Script.serialise] Start. Cmds: {self.cmds}")
        # iterate through each command
        for i, cmd in enumerate(self.cmds):
            #if cmd is an int then its an opcode
            if type(cmd) == int:
                # print(f"[DEBUG Script.serialise] Processing cmd {i}: Opcode {cmd}")
                #turn cmd into single byte integer
                result += int_to_little_endian(cmd, 1)
            else:
                # otherwise it is an element
                # get the length in bytes
                length = len(cmd)
                # print(f"[DEBUG Script.serialise] Processing cmd {i}: Data (len={length}) {cmd.hex()[:20]}...")
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
                    # print(f"[DEBUG Script.serialise] ERROR: CMD {i} is too long (len={length})")
                    raise ValueError("CMD is too long")
                result+=cmd
            # print(f"[DEBUG Script.serialise] After cmd {i}. Current result len: {len(result)}")
        # get total length
        total = len(result)
        # --- DEBUG LINE ---
        # print(f"[DEBUG Script.serialise] Finished commands payload (len={total}). Prepending varint length...")
        # Prepend the total length as a varint
        final_result = encode(total) + result
        # --- DEBUG LINE ---
        # print(f"[DEBUG Script.serialise] Done. Final script len (incl. varint): {len(final_result)}")
        # Uncomment for debugging:
        # print(f"DEBUG: Serialized Script: {final_result.hex()}")
        return final_result
    
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
    
    @classmethod
    def from_dict(cls, d):
        # Accepts either a dict with 'cmds' or a list directly
        cmds = d.get('cmds', d) if isinstance(d, dict) else d
        if len(cmds) != 3:
            raise ValueError("StakingScript expects exactly 3 cmds")
        # cmds[1] is the hash160, cmds[2] is lock_time as bytes
        hash160 = cmds[1]
        lock_bytes = cmds[2]
        if isinstance(lock_bytes, bytes):
            lock_time = int.from_bytes(lock_bytes, 'big')
        elif isinstance(lock_bytes, int):
            lock_time = lock_bytes
            lock_bytes = lock_time.to_bytes(8, 'big')
        else:
            raise ValueError("Invalid lock_time format in StakingScript cmds")
        # Reconstruct address from hash160 for constructor
        # Use mainnet prefix (b'\x00') for address
        import hashlib
        prefix = b'\x00'
        payload = prefix + hash160
        checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        address_bytes = payload + checksum
        BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
        num = int.from_bytes(address_bytes, 'big')
        address = ''
        while num > 0:
            num, mod = divmod(num, 58)
            address = BASE58_ALPHABET[mod] + address
        # Add '1's for leading zeros
        n_pad = 0
        for b in address_bytes:
            if b == 0:
                n_pad += 1
            else:
                break
        address = '1' * n_pad + address
        return cls(address, lock_time)