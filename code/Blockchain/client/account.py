import sys
sys.path.append('/dcs/project/algoblock/CS351_PROJECT/code')
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import Sha256Point
from Blockchain.Backend.core.database.db import AccountDB
from Blockchain.Backend.util.util import hash160, hash256
import secrets


class account:
    def createKeys(self):

        """Secp256k1 Curve Generator Points"""
        Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
        Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

        G = Sha256Point(Gx, Gy)

        self.privateKey = secrets.randbits(256)

        unCompressesPublicKey = self.privateKey * G
        Xpoint = unCompressesPublicKey.x
        Ypoint = unCompressesPublicKey.y

        if Ypoint.num % 2 == 0:
            compressesKey = b'\x02' + Xpoint.num.to_bytes(32,'big')
        else:
            compressesKey = b'\x03' + Xpoint.num.to_bytes(32,'big')

        hash_160 = hash160(compressesKey)

        "prefix for wallet addresses"
        add_prefix = b"\x00"

        new_address = add_prefix + hash_160

        " Checksum "

        checksum = hash256(new_address)[:4]
        new_address+=checksum

        BASE58_ALPHA='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
        counter = 0

        for i in new_address:
            if i == 0:
                counter+=1
            else: break
        
        " Convert to Numeric from Bytes "
        num = int.from_bytes(new_address,'big')
        prefix = '1'*counter

        result = ''
        "Base 58 encoder"
        while num>0:
            num,mod = divmod(num, 58)
            result = BASE58_ALPHA[mod] + result
        
        self.public_addr = prefix + result

        print(f"Private Key is {self.privateKey}")
        print(f"TadeCoin Public address is {self.public_addr}")

    def save_to_db(self):
        """Save account details to the database"""
        AccountDB().write([self.__dict__])



if __name__ == '__main__':
    acct = account()
    acct.createKeys()
    acct.save_to_db()
    print(acct.__dict__)
