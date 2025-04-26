import json
import sys
sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoWBlockchain/blockchain_code')
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import Sha256Point
from Blockchain.Backend.core.database.db import AccountDB
from Blockchain.Backend.util.util import decode_base58, hash160, hash256
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
    
    @classmethod
    def get_account(cls, address,node_id=None, db_path=None):
        """
        Retrieve account data from database and create an account object for PoW.
        Values are stored in satoshis in the DB.
        """
        # Instantiate AccountDB to ensure it uses the correct node-specific path if configured
        db_instance = AccountDB(node_id=node_id, db_path=db_path) 
        account_data = db_instance.read_account(address)
        if account_data is None:
            print(f"No account found for address: {address}")
            return None
        
        # Debug the raw data
        # print(f"Raw account data from DB: {account_data}")

        # Try to determine which database file was used
        db_path = getattr(db_instance, 'db_path', getattr(db_instance, 'filepath', 'unknown_path'))
        print(f"Database path used: {db_path}")
        
        new_acct = cls()
        new_acct.public_addr = account_data.get('public_addr', '')
        
        # Handle the privateKey which might be stored as string or int
        private_key = account_data.get('privateKey', account_data.get('private_key', 0))
        if isinstance(private_key, str) and private_key.isdigit():
            private_key = int(private_key)
        new_acct.privateKey = private_key
        
        # Handle public key that might be stored as hex string
        public_key_hex = account_data.get('public_key', '')
        if isinstance(public_key_hex, str) and public_key_hex:
            try:
                # Ensure the hex string is valid (even length)
                if len(public_key_hex) % 2 != 0:
                    public_key_hex = '0' + public_key_hex # Pad if necessary, though usually indicates an issue
                new_acct.public_key = bytes.fromhex(public_key_hex)
            except ValueError:
                 print(f"Warning: Invalid hex string for public_key: {public_key_hex}")
                 new_acct.public_key = None # Or handle as appropriate
        else:
             # Assuming it might be stored directly as bytes or is missing/None
            new_acct.public_key = public_key_hex if isinstance(public_key_hex, bytes) else None

        # REMOVED Staking-related fields
        # new_acct.staked = int(account_data.get('staked', account_data.get('stake', 0)))
        # new_acct.locked_until = int(account_data.get('locked_until', 0))
        # new_acct.staking_history = ...

        # Keep track of unspent value if needed, otherwise remove this too
        # If your PoW chain doesn't track balance directly in the account DB, remove this.
        # new_acct.unspent = int(account_data.get('unspent', 0)) 

        # Debug the final account object values (Removed staking info)
        print(f"Account object created: address={new_acct.public_addr}") 
            # f"unspent={new_acct.unspent} satoshis ({new_acct.unspent/100000000} coins)") # Optional: if unspent is kept

        return new_acct
    
    def get_balance(self, utxo_set):
        spendable = 0
        h160_user = decode_base58(self.public_addr)
        for (txid, index), tx_out in utxo_set.items():
            cmds = tx_out.script_publickey.cmds
            # Standard spendable output (P2PKH)
            if len(cmds) >= 3 and cmds[2] == h160_user and cmds[0] == 0x76:
                # print(f"[DEBUG][get_balance] MATCH P2PKH for {txid}:{index}")
                spendable += tx_out.amount
            # else:
                # print(f"[DEBUG][get_balance] NO MATCH for {txid}:{index}")
        print(f"[DEBUG][get_balance] FINAL spendable={spendable}")
        return spendable



if __name__ == '__main__':
    acct = account()
    acct.createKeys()
    acct.save_to_db()
    print(acct.__dict__)
