"""
The code defines a way to construct a standard Bitcoin P2PKH script, 
which is fundamental for creating transactions that send coins to a specific address.
"""

import sys
sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoWBlockchain/blockchain_code')

from Blockchain.Backend.util.util import int_to_little_endian, little_endian_to_int, encode, read_varint
from Blockchain.Backend.core.EllepticCurve.op import OP_CODE_FUNCTION

from io import BytesIO # Import BytesIO for from_dict parsing
import logging # Add logging

logger = logging.getLogger(__name__) # Setup logger


class Script:
    def __init__(self, cmds=None):
        if cmds is None:
            self.cmds = []
        else:
            self.cmds = cmds
        
    def __add__(self,other):
        return Script(self.cmds + other.cmds)
    
    def raw_serialise(self):
        """Serialises the script commands without the total length prefix."""
        result = b''
        for cmd in self.cmds:
            if isinstance(cmd, int): # Opcode
                result += int_to_little_endian(cmd, 1)
            elif isinstance(cmd, bytes): # Data push
                length = len(cmd)
                if length < 75: # OP_PUSHDATA_N
                    result += int_to_little_endian(length, 1)
                elif length < 0x100: # OP_PUSHDATA1
                    result += int_to_little_endian(76, 1)
                    result += int_to_little_endian(length, 1)
                elif length <= 520: # OP_PUSHDATA2
                    result += int_to_little_endian(77, 1)
                    result += int_to_little_endian(length, 2)
                else:
                    raise ValueError("CMD is too long for script serialization")
                result += cmd
            else:
                 raise TypeError(f"Invalid type in script commands: {type(cmd)}")
        return result

    def serialise(self):
        """Serialises the script commands with the total length prefix."""
        result = self.raw_serialise()
        total = len(result)
        return encode(total) + result # encode prepends the varint length

    
    # def serialise(self):
    #     #initialise what we return
    #     result = b''
    #     # iterate through each command
    #     for cmd in self.cmds:
    #         #if cmd is an int then its an opcode
    #         if type(cmd) == int:
    #             #turn cmd into single byte integer
    #             result += int_to_little_endian(cmd, 1)
    #         else:
    #             # otherwise it is an element
    #             # get the length in bytes
    #             length = len(cmd)
    #             #for large lengths, use a pushdata opdcode
    #             if length < 75:
    #                 result += int_to_little_endian(length,1)
    #             elif length > 75 and length < 0x100:
    #                 # 76 is pushdata1
    #                 result += int_to_little_endian(76,1)
    #                 result += int_to_little_endian(length, 1)
    #             elif length >= 0x100 and length <= 520:
    #                 # 77 is pushdata2
    #                 result += int_to_little_endian(77,1)
    #                 result += int_to_little_endian(length, 2)
    #             else:
    #                 raise ValueError("CMD is too long")
    #             result+=cmd
    #     # get total length
    #     total = len(result)
    #     return encode(total)+result
    
    # @classmethod
    # def parse(cls, s):
    #     length = read_varint(s)
    #     cmds = []
    #     count = 0
    #     while count < length:
    #         current = s.read(1)
    #         count +=1
    #         current_byte = current[0]

    #         if current_byte >=1 and current_byte <= 75:
    #             n = current_byte
    #             cmds.append(s.read(n))
    #             count += n
    #         elif current_byte == 76:
    #             data_length = little_endian_to_int(s.read(1))
    #             cmds.append(s.read(data_length))
    #             count += data_length + 1
    #         elif current_byte == 77:
    #             data_length = little_endian_to_int(s.read(2))
    #             cmds.append(s.read(data_length))
    #             count += data_length + 2
    #         else:
    #             op_code = current_byte
    #             cmds.append(op_code)
    #     if count != length:
    #         raise SyntaxError('parsing script failed')
    #     return cls(cmds)

    @classmethod
    def parse(cls, s):
        """Parses a script from a stream, reading the length prefix first."""
        length = read_varint(s)
        cmds = []
        count = 0
        while count < length:
            current = s.read(1)
            if not current:
                 raise EOFError("Unexpected end of stream while parsing script.")
            count += 1
            current_byte = current[0]

            if 1 <= current_byte <= 75: # OP_PUSHDATA_N
                n = current_byte
                data = s.read(n)
                if len(data) != n:
                     raise EOFError("Unexpected end of stream reading data push.")
                cmds.append(data)
                count += n
            elif current_byte == 76: # OP_PUSHDATA1
                data_length = little_endian_to_int(s.read(1))
                count += 1
                data = s.read(data_length)
                if len(data) != data_length:
                     raise EOFError("Unexpected end of stream reading OP_PUSHDATA1.")
                cmds.append(data)
                count += data_length
            elif current_byte == 77: # OP_PUSHDATA2
                data_length = little_endian_to_int(s.read(2))
                count += 2
                data = s.read(data_length)
                if len(data) != data_length:
                     raise EOFError("Unexpected end of stream reading OP_PUSHDATA2.")
                cmds.append(data)
                count += data_length
            else: # Opcode
                op_code = current_byte
                cmds.append(op_code)

        if count != length:
            # This check might be redundant if EOFError is handled correctly above
            logger.warning(f"Script parse count mismatch: expected {length}, got {count}")
            # raise SyntaxError('parsing script failed - count mismatch')
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

        # Check stack state after evaluation (e.g., should be [True] for P2PKH)
        if not stack:
             logger.debug("Script evaluation failed: Stack empty at end.")
             return False
        if stack.pop() == b'': # Bitcoin Core considers empty byte array as False
             logger.debug("Script evaluation failed: Stack top element was false.")
             return False

        # If stack is not empty after popping the expected True, it might be an error depending on script type
        # if stack:
        #    logger.debug("Script evaluation warning: Stack not empty after final check.")

        return True # Evaluation successful


    @classmethod
    def p2pkh_script(cls,h160):
        return cls([0x76,0xa9, h160, 0x88, 0xac])
    
    # --- ADDED to_dict ---
    # def to_dict(self):
    #     """Converts the script to a dictionary with commands serialized as a hex string."""
    #     try:
    #         # Serialize commands without the overall length prefix
    #         raw_bytes = self.raw_serialise()
    #         return {'cmds': raw_bytes.hex()}
    #     except Exception as e:
    #         print(f"Error serializing script to dict: {e}")
    #         # Return an empty script representation or re-raise
    #         return {'cmds': ''}

    def to_dict(self):
        """Converts the script to a dictionary containing a list of commands.
           Bytes are hex-encoded, opcodes (ints) remain ints.
        """
        serialisable_cmds = []
        try:
            if self.cmds: # Check if cmds is not None or empty
                for cmd in self.cmds:
                    if isinstance(cmd, bytes):
                        serialisable_cmds.append(cmd.hex()) # Convert bytes to hex string
                    elif isinstance(cmd, int):
                        # Opcodes are usually ints, keep them as ints for JSON
                        serialisable_cmds.append(cmd)
                    else:
                        # Handle other potential types if necessary, or convert to string
                        logger.warning(f"Serializing unexpected type in script cmds: {type(cmd)}")
                        serialisable_cmds.append(str(cmd))
            # ALWAYS return a list for 'cmds', even if empty
            return {'cmds': serialisable_cmds}
        except Exception as e:
            print(f"Error converting script cmds to serializable list: {e}")
            # Return an empty list on error to maintain structure
            return {'cmds': []}

    # --- ADDED from_dict ---
    @classmethod
    def from_dict(cls, script_dict):
        """Creates a Script object from a dictionary containing a list of commands."""
        reconstructed_cmds = []
        try:
            if 'cmds' not in script_dict or not isinstance(script_dict['cmds'], list):
                 raise ValueError("Invalid script dictionary format: 'cmds' key missing or not a list.")

            for item in script_dict['cmds']:
                if isinstance(item, int):
                    # Assume integers are opcodes
                    reconstructed_cmds.append(item)
                elif isinstance(item, str):
                    # Assume strings are hex-encoded bytes
                    try:
                        reconstructed_cmds.append(bytes.fromhex(item))
                    except ValueError:
                         logger.error(f"Invalid hex string found in script cmds: {item}")
                         raise ValueError(f"Invalid hex string in script cmds: {item}")
                else:
                     logger.warning(f"Encountered unexpected type in script dict cmds: {type(item)}")
                     # Decide how to handle unexpected types - skip, error, or convert?
                     # For now, let's raise an error
                     raise TypeError(f"Unexpected type in script dict cmds: {type(item)}")

            return cls(reconstructed_cmds)
        except KeyError: # Should be caught by the initial check, but good practice
            print("Script dictionary missing 'cmds' key.")
            raise ValueError("Invalid script dictionary format: Missing 'cmds' key.")
        except ValueError as e: # Catches hex decoding errors and format errors
            print(f"Error parsing script cmds from list: {e}")
            raise ValueError(f"Invalid script dictionary list representation: {e}") from e
        except Exception as e:
            print(f"Error creating Script from dict: {e}")
            raise # Re-raise other unexpected errors
