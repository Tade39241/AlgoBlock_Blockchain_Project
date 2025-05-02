import sys
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import Sha256Point, PrivateKey, PublicKey
from Blockchain.Backend.core.database.db import AccountDB
from Blockchain.Backend.util.util import hash160, hash256, decode_base58
from Blockchain.Backend.core.tx import Tx, TxOut, TxIn
from Blockchain.Backend.core.script import Script, StakingScript
import time, secrets, hashlib, json
import traceback
import logging


from Blockchain.Backend.util.logging_config import get_logger # Adjust path if needed

# Get a logger specific to this module/class
logger = get_logger("Account")



class account:
    def __init__(self):
        self.privateKey = None
        self.public_addr = None
        self.public_key = None
        self.unspent = 0           # Calculated from UTXOs owned by the user, stored in satoshis.
        self.staked = 0            # Funds the user has explicitly staked, stored in satoshis.
        # self.pending_rewards = 0   # Rewards allocated to the user, awaiting claim, stored in satoshis.
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
                'staking_history': json.dumps(self.staking_history) if isinstance(self.staking_history, list) else self.staking_history
            }
            
            # First save locally
            AccountDB().update_account(self.public_addr, data_to_store)
            # print(f"Account {self.public_addr} saved to local DB.")
            
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
            # print(f"NodeDB path: {node_db.filepath}")
            port_list = node_db.read_nodes() if hasattr(node_db, 'read_nodes') else node_db.read()
            # print(port_list)
            
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
            
            # print(f"Account update broadcast to {broadcast_count} nodes")
            return broadcast_count > 0
        except Exception as e:
            print(f"Error in broadcast_account_update: {e}")
            return False

    # def get_balance(self, utxo_set):
    #     spendable = 0
    #     staked = 0
    #     h160_user = decode_base58(self.public_addr)
    #     for (txid, index), tx_out in utxo_set.items():
    #         cmds = tx_out.script_publickey.cmds
    #         print(f"[DEBUG][get_balance] {txid}:{index} cmds={cmds} h160_user={h160_user.hex()}")
    #         # Standard spendable output (P2PKH)
    #         if len(cmds) >= 3 and cmds[2] == h160_user and cmds[0] == 0x76:
    #             print(f"[DEBUG][get_balance] MATCH P2PKH for {txid}:{index}")
    #             print(f"[DEBUG][MATCH] cmds[2]={cmds[2].hex()} h160_user={h160_user.hex()}")

    #             spendable += tx_out.amount
    #         # Staked output (StakingScript)
    #         elif len(cmds) == 3 and cmds[0] == b'\x00' and cmds[1] == h160_user:
    #             print(f"[DEBUG][get_balance] MATCH StakingScript for {txid}:{index}")
    #             staked += tx_out.amount
    #         else:
    #             print(f"[DEBUG][get_balance] NO MATCH for {txid}:{index}")
    #     print(f"[DEBUG][get_balance] FINAL spendable={spendable} staked={staked}")
    #     return spendable, staked

    def get_balance(self, utxo_set):
        spendable = 0
        staked = 0
        h160_user = decode_base58(self.public_addr)

        if not isinstance(utxo_set, dict):
            # Handle cases where utxo_set might be a Manager proxy dict
            if hasattr(utxo_set, '_getvalue'):
                 utxo_set = utxo_set._getvalue() # Try to get the underlying dict
            else:
                logger.error(f"Cannot calculate balance: UTXO set is not a dictionary or proxy (type: {type(utxo_set)})")
                return 0, 0

        for (txid, index), tx_out in utxo_set.items():
            cmds = tx_out.script_publickey.cmds
            if len(cmds) >= 3:
                pass
                # print(f"[DEBUG][MATCH] cmds[2]={cmds[2].hex()} h160_user={h160_user.hex()}")
            else:
                print(f"[DEBUG][MATCH] cmds too short: {cmds}")
            # print(f"[DEBUG][get_balance] {txid}:{index} cmds={cmds} h160_user={h160_user.hex()}")
            # Standard spendable output (P2PKH)
            if len(cmds) >= 3 and cmds[2] == h160_user and cmds[0] == 0x76:
                # print(f"[DEBUG][get_balance] MATCH P2PKH for {txid}:{index}")
                spendable += tx_out.amount
            # Staked output (StakingScript)
            elif len(cmds) == 3 and cmds[0] == b'\x00' and cmds[1] == h160_user:
                # print(f"[DEBUG][get_balance] MATCH StakingScript for {txid}:{index}")
                staked += tx_out.amount
            else:
                print(f"[DEBUG][get_balance] NO MATCH for {txid}:{index}")
        # print(f"[DEBUG][get_balance] FINAL spendable={spendable} staked={staked}")
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
        # print(f"Account object created: address={new_acct.public_addr}, " 
        #     f"staked={new_acct.staked} satoshis ({new_acct.staked/100000000} coins), "
        #     f"unspent={new_acct.unspent} satoshis ({new_acct.unspent/100000000} coins), ")
        
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
        """Selects sufficient UTXOs (P2PKH only) for staking the given amount."""
        TxIns = []
        total = 0
        try: # Protect against errors getting script/hash
             script_pubkey = Script().p2pkh_script(decode_base58(fromAddress))
             fromPubKeyHash = script_pubkey.cmds[2]
        except Exception as e:
             print(f"[prepareStakeTxIns] Error getting script/hash for {fromAddress}: {e}")
             return [], 0 # Return empty if cannot determine sender hash

        # print(f"[prepareStakeTxIns] fromAddress={fromAddress} fromPubKeyHash={fromPubKeyHash.hex()}")
        # print(f"[prepareStakeTxIns] Required amount for stake source: {amount}")
        # print(f"[prepareStakeTxIns] Checking {len(utxos)} UTXOs provided.")

        for (txid, index), tx_out in utxos.items():
            # --- Add Detailed Logging ---
            # print(f"--- Checking UTXO ({txid}, {index}) ---")
            if not (hasattr(tx_out, 'amount') and hasattr(tx_out, 'script_publickey') and hasattr(tx_out.script_publickey, 'cmds')):
                #  print(f"  Invalid structure. Skipping.")
                 continue

            cmds = tx_out.script_publickey.cmds
            utxo_amount = getattr(tx_out, 'amount', 0)
            if not isinstance(utxo_amount, int):
                #  print(f"  Non-integer amount ({type(utxo_amount)}). Skipping.")
                 continue

            # print(f"  Amount: {utxo_amount}, Script Cmds: {cmds}")
            # Check if it's a P2PKH output matching the sender
            is_p2pkh_match = (len(cmds) == 5 and cmds[0] == 0x76 and cmds[1] == 0xa9 and isinstance(cmds[2], bytes) and cmds[2] == fromPubKeyHash)
            # print(f"  Is P2PKH match for sender?: {is_p2pkh_match}")

            if is_p2pkh_match:
                if total < amount:
                    total += utxo_amount
                    TxIns.append(TxIn(
                        prev_tx=bytes.fromhex(txid),
                        prev_index=index,
                        script_sig=Script(), # Empty script_sig
                        sequence=0xFFFFFFFF
                    ))
                    # print(f"  --> SELECTED P2PKH UTXO as input. Current Total: {total}")
                else:
                    # print(f"  Sufficient total found ({total} >= {amount}). Breaking loop.")
                    break # Stop when enough is gathered
            # else: print("  Not a matching P2PKH. Skipping.")
            # --- End Detailed Logging ---

        # print(f"[prepareStakeTxIns] Finished loop. Total selected amount={total}. Number of inputs={len(TxIns)}")
        return TxIns, total
    


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
        # print(f"[DEBUG][StakeTxOut] StakingScript cmds={staking_script.cmds} amount={stake_amount}")
        outputs.append(TxOut(stake_amount, staking_script))
        # If there is change, add an output to return it to the user's wallet.
        if change > 0:
            if not fromAddress:
                raise ValueError("fromAddress must be provided for creating change output.")
            user_script = self.script_public_key(fromAddress)
            # print(f"[DEBUG][StakeTxOut] ChangeScript cmds={user_script.cmds} amount={change}")
            outputs.append(TxOut(change, user_script))
        return outputs

    def signStakeTransaction(self, TxObj):
        """
        Sign each input of the stake transaction using the account's private key.
        (Assumes that self.privateKey is already set.)
        """
        for i, txin in enumerate(TxObj.tx_ins):
            TxObj.sign_input(i, PrivateKey(self.privateKey), self.script_public_key(self.public_addr))

    # def prepareStakeTransaction(self, amount, lock_duration, utxos, fromAddress):
    #     """
    #     Assemble, sign, and return a new stake transaction if there is sufficient balance;
    #     otherwise, return False.

    #     This method now uses prepareStakeTxOut to create the primary stake output
    #     and, if necessary, a change output.
    #     """
    #     # Select UTXOs from the global UTXO set that belong to the sender.
    #     TxIns, total = self.prepareStakeTxIns(utxos, fromAddress, amount)
    #     if total < amount:
    #         return False  # Insufficient funds.
        
    #     change = total - amount
    #     lock_time = int(time.time()) + lock_duration
    #     TxOuts = self.prepareStakeTxOut(amount, change, fromAddress,lock_time)
    #     TxObj = Tx(1, TxIns, TxOuts, lock_time)
    #     self.signStakeTransaction(TxObj)
    #     TxObj.TxId = TxObj.id()
    #     return TxObj

    def create_stake_transaction(self, amount_satoshis, lock_duration_days, utxos_snapshot, fromAddress):
        """Builds and signs a stake transaction."""
        print(f"Creating stake transaction for {fromAddress}: Amount={amount_satoshis}, Duration={lock_duration_days} days")
        if amount_satoshis <= 0: raise ValueError("Stake amount must be positive.")
        if lock_duration_days <= 0: raise ValueError("Lock duration must be positive.")

        if not isinstance(utxos_snapshot, dict):
            # Handle cases where utxo_set might be a Manager proxy dict
            if hasattr(utxos_snapshot, '_getvalue'):
                 utxos_snapshot = utxos_snapshot._getvalue() # Try to get the underlying dict
            else:
                logger.error(f"Cannot calculate balance: UTXO set is not a dictionary or proxy (type: {type(utxo_set)})")
                return 0, 0

        # --- Use prepareStakeTxIns to find SPENDABLE inputs ---
        TxIns, total_in = self.prepareStakeTxIns(utxos_snapshot, fromAddress, amount_satoshis)
        # print(f"[create_stake_transaction] Inputs found: {len(TxIns)}, Total Input Value: {total_in}")

        # Check if enough spendable funds were found
        if total_in < amount_satoshis:
            # print(f"Insufficient SPENDABLE funds for stake: Required={amount_satoshis}, Found={total_in}")
            return None # Return None for insufficient balance

        # --- Prepare Outputs ---
        change_amount = total_in - amount_satoshis # Calculate change
        lock_time_seconds = lock_duration_days * 24 * 60 * 60 # Convert days to seconds
        absolute_lock_time = int(time.time()) + lock_time_seconds # Calculate absolute timestamp

        TxOuts = []
        # 1. Staking Output (using StakingScript)
        try:
            staking_script = StakingScript(fromAddress, absolute_lock_time) # Assuming StakingScript helper exists
            TxOuts.append(TxOut(amount=amount_satoshis, script_publickey=staking_script))
            # print(f"Prepared Staking Output: Amount={amount_satoshis}, LockUntil={absolute_lock_time}")
        except Exception as e:
             print(f"Failed to create staking script/output: {e}")
             return None

        # 2. Change Output (if any, back to standard P2PKH)
        if change_amount > 0:
            try:
                change_script = Script().p2pkh_script(decode_base58(fromAddress))
                TxOuts.append(TxOut(amount=int(change_amount), script_publickey=change_script)) # Ensure int
                # print(f"Prepared Change Output: Amount={int(change_amount)}")
            except Exception as e:
                #  print(f"Failed to create change script/output: {e}")
                 return None
        elif change_amount < 0 :
            #  print(f"Negative change amount {change_amount} calculated during staking tx creation.")
             return None # Should be caught by insufficient funds check, but safety first

        # Create and Sign Transaction
        try:
            TxObj = Tx(version=1, tx_ins=TxIns, tx_outs=TxOuts, locktime=0) # Use standard locktime for tx itself
            if not self.sign_transaction(TxObj): # Assuming sign_transaction signs all inputs
                #  print("Failed to sign stake transaction.")
                 return None
            TxObj.TxId = TxObj.id() # Assign ID after signing
            # print(f"Stake transaction created and signed: {TxObj.TxId}")
            # Update off-chain account fields (consider if this is the right place)
            # self.staked += amount_satoshis # This might be better handled by get_balance from UTXOs
            # self.unspent -= amount_satoshis
            # self.save_to_db() # Saving here might be premature before confirmation
            return TxObj
        except Exception as e:
            print(f"Error creating/signing final stake transaction: {e}")
            return None

    def create_unstake_transaction(self, unstake_amount_satoshis, utxos_snapshot):
        """Builds and signs an unstake transaction."""
        print(f"Creating unstake transaction for {self.public_addr}: Amount={unstake_amount_satoshis}")
        if unstake_amount_satoshis <= 0: raise ValueError("Unstake amount must be positive.")

        TxIns = []
        total_staked_found = 0
        staked_utxos_to_spend = [] # Keep track of UTXOs selected
        current_time = int(time.time())
        h160_user = decode_base58(self.public_addr)

        # print(f"[create_unstake] Checking {len(utxos_snapshot)} UTXOs provided.")
        # --- Find available STAKED and UNLOCKED UTXOs ---
        for (txid, index), tx_out in utxos_snapshot.items():
            if not (hasattr(tx_out, 'amount') and hasattr(tx_out, 'script_publickey') and hasattr(tx_out.script_publickey, 'cmds')): continue
            cmds = tx_out.script_publickey.cmds
            utxo_amount = getattr(tx_out, 'amount', 0)
            if not isinstance(utxo_amount, int): continue

            # Check if it's a Staking output for this user
            is_staked_match = (len(cmds) == 3 and cmds[0] == b'\x00' and isinstance(cmds[1], bytes) and cmds[1] == h160_user and isinstance(cmds[2], bytes))

            if is_staked_match:
                 stake_lock_time = int.from_bytes(cmds[2], 'big')
                 is_locked = current_time < stake_lock_time
                #  print(f"  Checking Staked UTXO ({txid},{index}): Amount={utxo_amount}, LockTime={stake_lock_time}, Locked={is_locked}")
                 # Select if it belongs to user AND is UNLOCKED
                 if not is_locked:
                    #   print(f"  -> Unlocked Staked UTXO found.")
                      if total_staked_found < unstake_amount_satoshis:
                           total_staked_found += utxo_amount
                           staked_utxos_to_spend.append(((txid, index), tx_out)) # Store key and value
                           print(f"  --> SELECTED unlocked staked UTXO as input. Current Total Found: {total_staked_found}")
                      else:pass
                           # Optimization: Stop if enough found? Or gather all unlocked?
                           # Let's gather all available unlocked stake first for simplicity of change calc
                        #    print("  Sufficient amount found, but continuing to gather all unlocked stake...")
                           # Keep iterating to find all unlockable stake if needed later for change
                 else:pass
                    #   print("  -> Staked UTXO is still locked.")
            # else: print(f"  UTXO ({txid}, {index}) is not a matching stake script.")


        print(f"[create_unstake] Total available unlocked stake found: {total_staked_found}")
        # --- Check if FOUND unlocked stake is sufficient ---
        if total_staked_found < unstake_amount_satoshis:
            logger.error(f"Cannot unstake {unstake_amount_satoshis}: Only {total_staked_found} available unlocked staked funds found.")
            # Raise the specific error your simulator received
            raise ValueError("Unstake amount exceeds available unlocked staked funds.")
            # return None # Or return None

        # --- Create Inputs from selected UTXOs ---
        # We might need more inputs than strictly necessary if individual UTXOs are small
        # Select enough UTXOs from staked_utxos_to_spend to cover unstake_amount_satoshis
        # For simplicity now, assume we use all selected ones if their total >= required amount
        # (A more complex selection algorithm could minimize inputs)
        actual_input_total = 0
        for (txid, index), tx_out in staked_utxos_to_spend:
             TxIns.append(TxIn(prev_tx=bytes.fromhex(txid), prev_index=index, script_sig=Script()))
             actual_input_total += tx_out.amount
             # Stop adding inputs once we've covered the amount (could optimize further)
             if actual_input_total >= unstake_amount_satoshis:
                  break

        print(f"[create_unstake] Using {len(TxIns)} inputs with total value {actual_input_total}")
        if actual_input_total < unstake_amount_satoshis:
             # Should not happen if previous check passed, but safety check
             logger.error("Internal Error: Selected input total less than required unstake amount.")
             return None

        # --- Prepare Outputs ---
        TxOuts = []
        # 1. Output back to user's standard P2PKH address
        try:
             p2pkh_script = Script().p2pkh_script(h160_user)
             TxOuts.append(TxOut(amount=unstake_amount_satoshis, script_publickey=p2pkh_script))
            #  print(f"Prepared Unstake Output (P2PKH): Amount={unstake_amount_satoshis}")
        except Exception as e:
             logger.error(f"Failed to create P2PKH script/output for unstake: {e}")
             return None

        # 2. Change Output (if any, back to *staked* address with original locktime?) - Tricky!
        #    OR Change back to standard P2PKH? Let's do P2PKH for simplicity.
        change_amount = actual_input_total - unstake_amount_satoshis
        if change_amount > 0:
             try:
                  # Change goes back to standard spendable address
                  change_script = Script().p2pkh_script(h160_user)
                  TxOuts.append(TxOut(amount=int(change_amount), script_publickey=change_script))
                #   print(f"Prepared Change Output (P2PKH): Amount={int(change_amount)}")
             except Exception as e:
                  logger.error(f"Failed to create change script/output for unstake: {e}")
                  return None
        elif change_amount < 0:
             logger.error(f"Negative change amount {change_amount} calculated during unstake tx creation.")
             return None

        # Create and Sign Transaction
        try:
            TxObj = Tx(version=1, tx_ins=TxIns, tx_outs=TxOuts, locktime=0)
            # Signing unstake inputs requires the original StakingScript as the script_pubkey
            # We need to reconstruct it or pass it correctly. Let's assume sign_transaction handles this.
            if not self.sign_transaction(TxObj): # You might need a specific sign_stake_input method
                 logger.error("Failed to sign unstake transaction.")
                 return None
            TxObj.TxId = TxObj.id()
            print(f"Unstake transaction created and signed: {TxObj.TxId}")
            # Update off-chain state if needed (careful here)
            # self.staked -= unstake_amount_satoshis
            # self.unspent += unstake_amount_satoshis # Or maybe just the change? Depends on how balance is tracked
            # self.save_to_db()
            return TxObj
        except Exception as e:
             logger.error(f"Error creating/signing final unstake transaction: {e}")
             return None
    
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
        # print(f"[DEBUG][create_stake_transaction] TxIns={TxIns} total={total} required={amount}")
        if total < amount:
            # print(f"[DEBUG][create_stake_transaction] Insufficient funds: total={total} required={amount}")
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

    # def prepare_unstake_tx_ins(self, unstake_amount, utxo_set):
    #     """
    #     Select staking UTXOs (with StakingScript) that belong to the user and are unlocked.
    #     """
    #     h160_user = decode_base58(self.public_addr)
    #     selected_ins = []
    #     total = 0
    #     now = int(time.time())
    #     for (txid, idx), tx_out in utxo_set.items():
    #         if tx_out is None:
    #             continue
    #         cmds = tx_out.script_publickey.cmds
    #         # StakingScript: cmds[0] == b'\x00', cmds[1] == user_h160, cmds[2] == locktime
    #         if len(cmds) >= 3 and cmds[2] == h160_user and (cmds[0] == 0x76 or cmds[0] == b'\x76'):
    #             lock_time = int.from_bytes(cmds[2], 'big')
    #             if now >= lock_time:
    #                 selected_ins.append((txid, idx, tx_out))
    #                 total += tx_out.amount
    #                 if total >= unstake_amount:
    #                     break
    #     if total < unstake_amount:
    #         raise ValueError("Not enough unlocked staked funds to unstake.")
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
        h160_user = decode_base58(self.public_addr)
        selected_ins = []
        total = 0
        now = int(time.time())
        # print(f"[DEBUG][UnstakeTxIns] unstake_amount={unstake_amount} h160_user={h160_user.hex()} now={now}")
        for (txid, idx), tx_out in utxo_set.items():
            if tx_out is None:
                print(f"[DEBUG][UnstakeTxIns] Skipping None tx_out for {txid}:{idx}")
                continue
            cmds = tx_out.script_publickey.cmds
            # print(f"[DEBUG][UnstakeTxIns] {txid}:{idx} cmds={cmds}")
            # StakingScript: cmds[0] == b'\x00', cmds[1] == user_h160, cmds[2] == locktime
            if len(cmds) == 3 and cmds[0] == b'\x00' and cmds[1] == h160_user:
                lock_time = int.from_bytes(cmds[2], 'big')
                # print(f"[DEBUG][UnstakeTxIns] MATCH staking UTXO lock_time={lock_time} now={now}")
                if now >= lock_time:
                    # print(f"[DEBUG][UnstakeTxIns] UTXO {txid}:{idx} is unlocked, amount={tx_out.amount}")
                    selected_ins.append((txid, idx, tx_out))
                    total += tx_out.amount
                    if total >= unstake_amount:
                        # print(f"[DEBUG][UnstakeTxIns] Selected enough UTXOs, total={total}")
                        break
                else:pass
                    # print(f"[DEBUG][UnstakeTxIns] UTXO {txid}:{idx} is still locked (lock_time={lock_time})")
            else:pass
                # print(f"[DEBUG][UnstakeTxIns] NOT SELECTED {txid}:{idx} cmds={cmds}")
        # print(f"[DEBUG][UnstakeTxIns] TOTAL selected amount={total} (needed={unstake_amount})")
        if total < unstake_amount:
            # print(f"[DEBUG][UnstakeTxIns] Not enough unlocked staked funds to unstake.")
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