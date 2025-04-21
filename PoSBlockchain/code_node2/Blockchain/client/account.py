import sys
sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/code_node2')
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import Sha256Point, PrivateKey, PublicKey
from Blockchain.Backend.core.database.db import AccountDB
from Blockchain.Backend.util.util import hash160, hash256, decode_base58
from Blockchain.Backend.core.tx import Tx, TxOut, TxIn
from Blockchain.Backend.core.script import Script, StakingScript
import time, secrets, hashlib, json
import traceback


class account:
    def __init__(self):
        self.privateKey = None
        self.public_addr = None
        self.public_key = None
        self.unspent = 0           # Calculated from UTXOs owned by the user, stored in satoshis.
        self.staked = 100            # Funds the user has explicitly staked, stored in satoshis.
        # self.pending_rewards = 0   # Rewards allocated to the user, awaiting claim, stored in satoshis.
        self.locked_until = 0
        # New field to store staking/unstaking events (list of dicts)
        self.staking_history = []

    def createKeys(self):

        """Secp256k1 Curve Generator Points"""
        Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
        Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

        G = Sha256Point(Gx, Gy)

        self.privateKey = (secrets.randbits(256))

        unCompressesPublicKey = self.privateKey * G
        Xpoint = unCompressesPublicKey.x
        Ypoint = unCompressesPublicKey.y

        if Ypoint.num % 2 == 0:
            compressesKey = b'\x02' + Xpoint.num.to_bytes(32,'big')
        else:
            compressesKey = b'\x03' + Xpoint.num.to_bytes(32,'big')

        public_key_obj = PrivateKey(self.privateKey).get_public_key()
        self.public_key = public_key_obj.serialise_compressed()

        hash_160 = hash160( self.public_key)

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
        print(f"Public Key is {self.public_key}")
        print(f"TadeCoin Public address is {self.public_addr}")

    def save_to_db(self):
        """Save account details to the database and broadcast to other nodes."""
        try:
            # Prepare data with consistent field names
            data_to_store = {
                'privateKey': self.privateKey,
                'public_addr': self.public_addr,
                'public_key': self.public_key.hex() if isinstance(self.public_key, bytes) else self.public_key,
                'staked': self.staked,
                'unspent': self.unspent,
                'locked_until': self.locked_until,
                'staking_history': json.dumps(self.staking_history) if isinstance(self.staking_history, list) else self.staking_history
            }
            
            # First save locally
            AccountDB().update_account(self.public_addr, data_to_store)
            print(f"Account {self.public_addr} saved to local DB.")
            
            # Then broadcast to other nodes
            self.broadcast_account_update(data_to_store)
            
            return True
        except Exception as e:
            print(f"Error saving account to database: {e}")
            return False
        
    def broadcast_account_update(self, account_data):
        """Broadcast account updates to all other nodes in the network."""
        try:
            from Blockchain.Backend.core.database.db import NodeDB
            from Blockchain.Backend.core.network.syncManager import syncManager
            import os
            import re
            
            # Try to detect node ID and port
            node_id = 0
            local_port = None
            cwd = os.getcwd()
            match = re.search(r'node_(\d+)', cwd)
            if match:
                node_id = int(match.group(1))
                local_port = 9000 + node_id  #port pattern is 9000, 9001, etc.
            
            if not local_port:
                print("Warning: Could not detect local port, using fallback port 9000")
                local_port = 9000
                
            # Get list of other nodes
            node_db = NodeDB()
            print(f"NodeDB path: {node_db.filepath}")
            port_list = node_db.read_nodes() if hasattr(node_db, 'read_nodes') else node_db.read()
            print(port_list)
            
            broadcast_count = 0
            for port in port_list:
                # Skip local port
                if hasattr(port, '__iter__') and 'port' in port:
                    port = port['port']
                
                if port != local_port:
                    try:
                        print(f"Broadcasting account update to node at port {port}")
                        sync = syncManager(host="127.0.0.1", port=port, MemoryPool={})
                        sync.publish_account_update(local_port, port, self.public_addr, account_data)
                        broadcast_count += 1
                    except Exception as e:
                        print(f"Failed to broadcast account update to port {port}: {e}")
            
            print(f"Account update broadcast to {broadcast_count} nodes")
            return broadcast_count > 0
        except Exception as e:
            print(f"Error in broadcast_account_update: {e}")
            return False

    # def get_balance(self, utxo_set):
    #     """
    #     Calculate the spendable and staked balance of the user.
        
    #     - Spendable balance: Sum of UTXOs belonging to the user's public address.
    #     - Staked balance: Value stored in self.staked (updated via staking transactions).

    #     The utxo_set is a dictionary where keys are (txid, index) and values are TxOut objects.
    #     """
    #     spendable = 0
    #     staked = self.staked  # Staked balance is now managed **in the account DB**.

    #     # Decode the user’s public key hash
    #     h160_user = decode_base58(self.public_addr)

    #     for (txid, index), tx_out in utxo_set.items():
    #         cmds = tx_out.script_publickey.cmds
    #         if len(cmds) >= 3 and cmds[2] == h160_user:
    #             # Standard spendable output (belongs to the user's public key)
    #             spendable += tx_out.amount

    #     return spendable, staked

    def get_balance(self, utxo_set):
        spendable = 0
        staked = 0
        h160_user = decode_base58(self.public_addr)
        for (txid, index), tx_out in utxo_set.items():
            cmds = tx_out.script_publickey.cmds
            # Standard spendable output (P2PKH)
            if len(cmds) >= 3 and cmds[2] == h160_user and cmds[0] == 0x76:
                spendable += tx_out.amount
            # Staked output (StakingScript)
            elif len(cmds) == 3 and cmds[0] == b'\x00' and cmds[1] == h160_user:
                staked += tx_out.amount
        return spendable, staked
    
    # def create_claim_rewards_transaction(self, claim_amount):
    #     """
    #     Create a transaction that moves claim_amount (in satoshis) from the common staking UTXOs
    #     to this account's wallet address. Only allowed if claim_amount <= self.pending_rewards.
    #     """
    #     if claim_amount > self.pending_rewards:
    #         raise ValueError("Claim amount exceeds pending rewards.")

    #     # Build transaction inputs:
    #     # (Use your existing helper logic similar to prepareTxIn but filtering UTXOs belonging
    #     # to the staking address and allocated to this user via the off-chain record.)
    #     tx_ins = self.prepareClaimTxIns(claim_amount)
        
    #     # Build the output sending funds to the user's wallet address.
    #     dest_script = Script().p2pkh_script(decode_base58(self.public_addr))
    #     tx_out = TxOut(amount=claim_amount, script_publickey=dest_script)
        
    #     # Create and sign the transaction.
    #     from Blockchain.Backend.core.tx import Tx
    #     claim_tx = Tx(version=1, tx_ins=tx_ins, tx_outs=[tx_out], locktime=0)
    #     claim_tx.TxId = claim_tx.id()
    #     self.sign(claim_tx)
        
    #     # Update the account: reduce pending rewards and increase unspent balance.
    #     self.pending_rewards -= claim_amount
    #     self.unspent += claim_amount
    #     print(f"Created claim rewards tx: {claim_tx.TxId}, deducted {claim_amount/100000000} TDC")
    #     # The claim_tx, once confirmed, will add a UTXO for the user's address.
    #     self.save_to_db()
    #     return claim_tx
    
    def select_utxos(self, amount, utxo_set):
        """
        Select UTXOs from the public address.
        Returns a list of tuples: (txid, index, tx_out)
        """
        h160_public = decode_base58(self.public_addr)
        selected = []
        total = 0
        for (txid, index), tx_out in utxo_set.items():
            cmds = tx_out.script_publickey.cmds
            if len(cmds) >= 3 and cmds[2] == h160_public:
                selected.append((txid, index, tx_out))
                total += tx_out.amount
                if total >= amount:
                    return selected
        raise ValueError(f"Insufficient balance. Found {total}, needed {amount}")


    def sign(self, data):
        """Sign data with private key."""
        if not isinstance(data, bytes):
            raise TypeError("Data to sign must be bytes")
        
        signature_obj = PrivateKey(self.privateKey).sign(int.from_bytes(hashlib.sha256(data).digest(), 'big'))
        return signature_obj.der()
    
    def sign_transaction(self, tx):
        """
        Sign all inputs of the transaction using this account's private key.
        (Assumes you have a working sign_input method on Tx.)
        """
        for i in range(len(tx.tx_ins)):
            tx.sign_input(i, PrivateKey(self.privateKey), self.script_public_key(self.public_addr))

    @classmethod
    def get_account(cls, address):
        """
        Retrieve account data from database and create an account object.
        Values are stored in satoshis in the DB.
        """
        account_data = AccountDB().read_account(address)
        if account_data is None:
            print(f"No account found for address: {address}")
            return None
        
        # Debug the raw data
        # print(f"Raw account data from DB: {account_data}")

        # Try to determine which database file was used
        db_path = getattr(AccountDB(), 'db_path', getattr(AccountDB(), 'filepath', 'unknown_path'))
        print(f"Database path used: {db_path}")
        
        new_acct = cls()
        new_acct.public_addr = account_data.get('public_addr', '')
        
        # Handle the privateKey which might be stored as string or int
        private_key = account_data.get('privateKey', account_data.get('private_key', 0))
        if isinstance(private_key, str) and private_key.isdigit():
            private_key = int(private_key)
        new_acct.privateKey = private_key
        
        # Handle public key that might be stored as hex string
        public_key = account_data.get('public_key', '')
        if isinstance(public_key, str):
            new_acct.public_key = bytes.fromhex(public_key)
        else:
            new_acct.public_key = public_key
        
        # Explicitly convert numeric values to integers
        # The .get() fallbacks handle cases where fields might be missing
        new_acct.staked = int(account_data.get('staked', account_data.get('stake', 0)))
        # new_acct.pending_rewards = int(account_data.get('pending_rewards', 0))
        new_acct.unspent = int(account_data.get('unspent', 0))
        new_acct.locked_until = int(account_data.get('locked_until', 0))
        
        # Load staking history if available
        staking_history = account_data.get('staking_history', '[]')
        try:
            if isinstance(staking_history, str):
                new_acct.staking_history = json.loads(staking_history)
            else:
                new_acct.staking_history = staking_history
        except Exception as e:
            print(f"Error parsing staking history: {e}")
            new_acct.staking_history = []
        
        # Debug the final account object values
        print(f"Account object created: address={new_acct.public_addr}, " 
            f"staked={new_acct.staked} satoshis ({new_acct.staked/100000000} coins), "
            f"unspent={new_acct.unspent} satoshis ({new_acct.unspent/100000000} coins), ")
        
        return new_acct
    
    def script_public_key(self, address):
        # Returns a P2PKH script for the given address.
        return Script().p2pkh_script(decode_base58(address))

    def signStakeTransaction(self, TxObj):
        """
        Sign each input of the stake transaction using the account's private key.
        (Assumes that self.privateKey is already set.)
        """
        # In a real implementation, you would sign each input with the proper previous script.
        for i, txin in enumerate(TxObj.tx_ins):
            # You might need to look up the previous output to get its script.
            # For simplicity, we assume you can pass the sender's public key script.
            TxObj.sign_input(i, PrivateKey(self.privateKey), self.script_public_key(self.public_addr))

    def prepareStakeTxIns(self, utxos, fromAddress, amount):
        """
        Iterate over the global UTXO set (without flattening) to select inputs that belong to the sender.
        Returns (TxIns, total) where total is the sum of the selected outputs.
        """
        TxIns = []
        total = 0
        sender_script = self.script_public_key(fromAddress)
        # Assume the public key hash is at cmds[2] in the script.
        fromPubKeyHash = sender_script.cmds[2]

        for (txid, idx), tx_out in utxos.items():
            if tx_out.script_publickey.cmds[2] == fromPubKeyHash:
                TxIns.append(TxIn(
                    prev_tx=bytes.fromhex(txid),
                    prev_index=idx,
                    script_sig=Script(),
                    sequence=0xFFFFFFFF
                ))
                total += tx_out.amount
                if total >= amount:
                    break
        return TxIns, total
    
    # def prepareStakeTxOut(self, stake_amount, change=0, fromAddress=None):
    #     """
    #     Build the outputs for the stake transaction.
    #     The primary output sends exactly 'stake_amount' to the common staking address.
    #     If change > 0, a second output returns the excess funds to the user's wallet address.
    #     """
    #     outputs = []
    #     # Primary stake output to the common staking address.
    #     user_h160 = decode_base58(self.public_addr)
    #     staking_script = Script().p2pkh_script(user_h160)
    #     outputs.append(TxOut(stake_amount, staking_script))
        
    #     # If there is change, add an output to return it to the user's wallet.
    #     if change > 0:
    #         if not fromAddress:
    #             raise ValueError("fromAddress must be provided for creating change output.")
    #         user_script = self.script_public_key(fromAddress)
    #         outputs.append(TxOut(change, user_script))
        
    #     return outputs

    def prepareStakeTxOut(self, stake_amount, change=0, fromAddress=None, lock_time=None):
        """
        Build the outputs for the stake transaction.
        The primary output sends 'stake_amount' to a staking script (not a standard P2PKH).
        If change > 0, a second output returns the excess funds to the user's wallet address.
        """
        outputs = []
        if lock_time is None:
            raise ValueError("lock_time must be provided for staking output.")
        # Use StakingScript for the staked output
        staking_script = StakingScript(self.public_addr, lock_time)
        outputs.append(TxOut(stake_amount, staking_script))
        # If there is change, add an output to return it to the user's wallet.
        if change > 0:
            if not fromAddress:
                raise ValueError("fromAddress must be provided for creating change output.")
            user_script = self.script_public_key(fromAddress)
            outputs.append(TxOut(change, user_script))
        return outputs

    def signStakeTransaction(self, TxObj):
        """
        Sign each input of the stake transaction using the account's private key.
        (Assumes that self.privateKey is already set.)
        """
        for i, txin in enumerate(TxObj.tx_ins):
            TxObj.sign_input(i, PrivateKey(self.privateKey), self.script_public_key(self.public_addr))

    def prepareStakeTransaction(self, amount, lock_duration, utxos, fromAddress):
        """
        Assemble, sign, and return a new stake transaction if there is sufficient balance;
        otherwise, return False.

        This method now uses prepareStakeTxOut to create the primary stake output
        and, if necessary, a change output.
        """
        amount_satoshis = amount * 100000000  # Convert to satoshis
        
        # Select UTXOs from the global UTXO set that belong to the sender.
        TxIns, total = self.prepareStakeTxIns(utxos, fromAddress, amount)
        if total < amount:
            return False  # Insufficient funds.
        
        change = total - amount
        lock_time = int(time.time()) + lock_duration
        TxOuts = self.prepareStakeTxOut(amount, change, fromAddress,lock_time)
        TxObj = Tx(1, TxIns, TxOuts, lock_time)
        self.signStakeTransaction(TxObj)
        TxObj.TxId = TxObj.id()
        return TxObj
    
    # def create_stake_transaction(self, amount, lock_duration, utxos, fromAddress):
    #     """
    #     Build, sign, and return a new stake transaction, and update off-chain fields.
    #     """
    #     # Select UTXOs and build inputs/outputs
    #     TxIns, total = self.prepareStakeTxIns(utxos, fromAddress, amount)
    #     if total < amount:
    #         return None  # Insufficient balance

    #     change = total - amount
    #     TxOuts = self.prepareStakeTxOut(amount, change, fromAddress)
    #     lock_time = int(time.time()) + lock_duration
    #     TxObj = Tx(1, TxIns, TxOuts, lock_time)
    #     self.signStakeTransaction(TxObj)
    #     TxObj.TxId = TxObj.id()

    #     # Update off-chain account fields
    #     self.staked += amount
    #     self.unspent -= amount
    #     self.locked_until = lock_time
    #     self.staking_history.append({
    #         "action": "stake",
    #         "amount": amount,
    #         "lock_duration": lock_duration,
    #         "timestamp": time.time()
    #     })
    #     self.save_to_db()
    #     return TxObj


    def create_stake_transaction(self, amount, lock_duration, utxos, fromAddress):
        """
        Build, sign, and return a new stake transaction, and update off-chain fields.
        """
        TxIns, total = self.prepareStakeTxIns(utxos, fromAddress, amount)
        if total < amount:
            return None  # Insufficient balance

        change = total - amount
        lock_time = int(time.time()) + lock_duration
        TxOuts = self.prepareStakeTxOut(amount, change, fromAddress, lock_time=lock_time)
        TxObj = Tx(1, TxIns, TxOuts, lock_time)
        self.signStakeTransaction(TxObj)
        TxObj.TxId = TxObj.id()

        # Update off-chain account fields
        self.staked += amount
        self.unspent -= amount
        self.locked_until = lock_time
        self.staking_history.append({
            "action": "stake",
            "amount": amount,
            "lock_duration": lock_duration,
            "timestamp": time.time()
        })
        self.save_to_db()
        return TxObj

    # def prepare_claim_rewards_tx_ins(self, claim_amount, utxo_set):
    #     """
    #     Select inputs from the global UTXO set that are using the user's staking script.
    #     Only UTXOs with the user's pubkey hash are selected.
    #     """
    #     user_h160 = decode_base58(self.public_addr)
    #     selected_ins = []
    #     total = 0
    #     for (txid, idx), tx_out in utxo_set.items():
    #         if tx_out is None:
    #             continue
    #         cmds = tx_out.script_publickey.cmds
    #         # Only select UTXOs with the user's pubkey hash at index 2
    #         if len(cmds) >= 3 and cmds[2] == user_h160:
    #             selected_ins.append((txid, idx, tx_out))
    #             total += tx_out.amount
    #             if total >= claim_amount:
    #                 break
    #     if total < claim_amount:
    #         raise ValueError("Not enough reward funds available for claim.")
    #     return [
    #         TxIn(
    #             prev_tx=bytes.fromhex(txid),
    #             prev_index=idx,
    #             script_sig=Script(),
    #             sequence=0xFFFFFFFF
    #         )
    #         for txid, idx, _ in selected_ins
    #     ]

    def prepare_unstake_tx_ins(self, unstake_amount, utxo_set):
        """
        Select staking UTXOs (with StakingScript) that belong to the user and are unlocked.
        """
        user_h160 = decode_base58(self.public_addr)
        selected_ins = []
        total = 0
        now = int(time.time())
        for (txid, idx), tx_out in utxo_set.items():
            if tx_out is None:
                continue
            cmds = tx_out.script_publickey.cmds
            # StakingScript: cmds[0] == b'\x00', cmds[1] == user_h160, cmds[2] == locktime
            if len(cmds) == 3 and cmds[0] == b'\x00' and cmds[1] == user_h160:
                lock_time = int.from_bytes(cmds[2], 'big')
                if now >= lock_time:
                    selected_ins.append((txid, idx, tx_out))
                    total += tx_out.amount
                    if total >= unstake_amount:
                        break
        if total < unstake_amount:
            raise ValueError("Not enough unlocked staked funds to unstake.")
        return [
            TxIn(
                prev_tx=bytes.fromhex(txid),
                prev_index=idx,
                script_sig=Script(),
                sequence=0xFFFFFFFF
            )
            for txid, idx, _ in selected_ins
        ]

    # def prepare_unstake_tx_ins(self, unstake_amount, utxo_set):
    #     """
    #     Select UTXOs (from the user's staking script) that represent staked funds.
    #     Only UTXOs with the user's pubkey hash are selected.
    #     """
    #     user_h160 = decode_base58(self.public_addr)
    #     selected_ins = []
    #     total = 0
    #     for (txid, idx), tx_out in utxo_set.items():
    #         if tx_out is None:
    #             continue
    #         cmds = tx_out.script_publickey.cmds
    #         if len(cmds) >= 3 and cmds[2] == user_h160:
    #             selected_ins.append((txid, idx, tx_out))
    #             total += tx_out.amount
    #             if total >= unstake_amount:
    #                 break
    #     if total < unstake_amount:
    #         raise ValueError("Not enough staked funds available for unstake.")
    #     return [
    #         TxIn(
    #             prev_tx=bytes.fromhex(txid),
    #             prev_index=idx,
    #             script_sig=Script(),
    #             sequence=0xFFFFFFFF
    #         )
    #         for txid, idx, _ in selected_ins
    #     ]
    

    # def create_claim_rewards_transaction(self, claim_amount, utxo_set):
    #     """
    #     Create a transaction that moves claim_amount (in satoshis) from the user's staking UTXOs
    #     to this account's wallet address. Only allowed if claim_amount <= self.pending_rewards.
    #     """
    #     if claim_amount > self.pending_rewards:
    #         raise ValueError("Claim amount exceeds pending rewards.")
    #     tx_ins = self.prepare_claim_rewards_tx_ins(claim_amount, utxo_set)
    #     dest_script = Script().p2pkh_script(decode_base58(self.public_addr))
    #     tx_out = TxOut(amount=claim_amount, script_publickey=dest_script)
    #     from Blockchain.Backend.core.tx import Tx
    #     claim_tx = Tx(version=1, tx_ins=tx_ins, tx_outs=[tx_out], locktime=0)
    #     claim_tx.TxId = claim_tx.id()
    #     self.sign_transaction(claim_tx)
    #     self.pending_rewards -= claim_amount
    #     self.unspent += claim_amount
    #     print(f"Created claim rewards tx: {claim_tx.TxId}, deducted {claim_amount/100000000} TDC")
    #     self.save_to_db()
    #     return claim_tx

    def create_unstake_transaction(self, unstake_amount, utxo_set):
        """
        Create a transaction to unstake funds. Only allow if unstake_amount is less than
        or equal to self.staked. This transaction moves funds from the user's staking UTXOs
        to the user's wallet address.
        """
        if unstake_amount > self.staked:
            raise ValueError("Unstake amount exceeds staked funds.")
        tx_ins = self.prepare_unstake_tx_ins(unstake_amount, utxo_set)
        dest_script = self.script_public_key(self.public_addr)
        tx_out = TxOut(amount=unstake_amount, script_publickey=dest_script)
        unstake_tx = Tx(version=1, tx_ins=tx_ins, tx_outs=[tx_out], locktime=0)
        unstake_tx.TxId = unstake_tx.id()
        self.sign_transaction(unstake_tx)
        self.staked -= unstake_amount
        self.unspent += unstake_amount
        self.save_to_db()
        return unstake_tx

if __name__ == '__main__':
# 1. Create a new account, generate keys, and save it.
    acct = account()            # Or Account() if that’s your class name.
    acct.createKeys()
    acct.save_to_db()
    print("Account dictionary representation:")
    print(acct.__dict__)
    
    # 2. Create a dummy UTXO set.
    # For testing, we simulate a UTXO with one output belonging to this account.
    dummy_amount = 1000 * 100000000  # For example, 1000 coins (in satoshis)
    # Create a standard P2PKH script for the account's public address.
    dummy_script = Script().p2pkh_script(decode_base58(acct.public_addr))
    dummy_tx_out = TxOut(amount=dummy_amount, script_publickey=dummy_script)
    
    # Create a dummy transaction with the above output.
    dummy_tx = Tx(version=1, tx_ins=[], tx_outs=[dummy_tx_out], locktime=0)
    dummy_tx.TxId = dummy_tx.id()  # Compute and store the TxID.
    
    # Simulate the UTXO set as stored in your system (keyed by txid).
    # utxo_set = {dummy_tx.TxId: dummy_tx}
    utxo_set = {(dummy_tx.TxId, 0): dummy_tx_out}
    
    # 3. Attempt to create a staking transaction.
    try:
        # With the new logic, we call the account's helper that directly works with the UTXO set.
        stake_tx = acct.prepareStakeTransaction(
            amount=50,           # Stake 50 coins (in satoshis, or adjust if your method expects coin units)
            lock_duration=3600,  # Lock duration in seconds (e.g., 1 hour)
            utxos=utxo_set,
            fromAddress=acct.public_addr
        )
        if not stake_tx:
            print("Insufficient funds for staking.")
        else:
            print("Created Stake Transaction:")
            print(stake_tx.__dict__)
            print("Updated account:")
            print(acct.__dict__)
            print("Updated UTXO set:")
            print(utxo_set)
    except ValueError as e:
        print(f"Error creating stake transaction: {e}")
    
    # 4. Test signing of arbitrary data.
    signature = acct.sign(b"Test data to sign")
    print("DER-encoded signature:", signature)