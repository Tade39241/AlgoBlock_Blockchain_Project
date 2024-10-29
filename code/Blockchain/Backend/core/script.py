"""
The code defines a way to construct a standard Bitcoin P2PKH script, 
which is fundamental for creating transactions that send coins to a specific address.
"""

import sys
sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code')

from Blockchain.Backend.util.util import int_to_little_endian, little_endian_to_int, encode
from Blockchain.Backend.core.EllepticCurve.op import OP_CODE_FUNCTION



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