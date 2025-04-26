import json
import sqlite3
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

PROJECT_ROOT = "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain"
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/code_node2')


import signal
import configparser
import copy
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import Sha256Point, PrivateKey, PublicKey, Signature
from Blockchain.Backend.util.util import hash256, merkle_root, decode_base58
from Blockchain.client.account import account
from Blockchain.Backend.core.database.db import BlockchainDB, AccountDB, NodeDB
from Blockchain.Backend.core.tx import Coinbase_tx, Tx, TxIn, TxOut
from Blockchain.Backend.core.script import Script, StakingScript
from multiprocessing import Process, Manager
from validatorNode.main import ValidatorSelector
from Blockchain.Backend.core.network.syncManager import syncManager

# from Blockchain.Frontend.run import main as web_main # Correct import path

import time
import random
import hashlib
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Constants
ZERO_HASH = "0" * 64
VERSION = 1

# PoS Specific Constants
STAKE_WEIGHT = 1  # Can be adjusted based on consensus rules

def signal_handler(sig, frame):
    print("\nShutting down gracefully...")
    sys.exit(0)


def get_validator_account(validator_addr):
    """Find a validator account using multiple lookup methods"""
    print(f"Looking up validator account: {validator_addr}")
    validator_account = None
    
    # First try with account.get_account 
    import sys
    for module_name, module in list(sys.modules.items()):
        if module_name.endswith('account') and hasattr(module, 'get_account'):
            try:
                validator_account = module.get_account(validator_addr)
                if validator_account:
                    print(f"Found validator account using {module_name}.get_account")
                    return validator_account
            except Exception as e:
                print(f"Error with {module_name}.get_account: {e}")
    
    # If that fails, try direct database access
    print("Standard lookup failed, trying direct database access")
    import os
    import re
    import sqlite3
    import json
    
    # Try to detect node ID from cwd
    node_id = 0
    cwd = os.getcwd()
    match = re.search(r'node_(\d+)', cwd)
    if match:
        node_id = int(match.group(1))
        print(f"Detected node_id {node_id}")
    
    # Try different DB paths - now including the /data/ subdirectory
    db_paths = [
        os.path.join("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data", 
                    f"node_{node_id}/data/account.db"),  # CORRECT PATH WITH /data/
        os.path.join("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data", 
                    f"node_{node_id}/account.db"),
        "data/account.db",
        "account.db",
        os.path.join(os.getcwd(), "data/account.db"),
        os.path.join(os.getcwd(), "account.db")
    ]
    
    for db_path in db_paths:
        if os.path.exists(db_path):
            try:
                print(f"Trying database path: {db_path}")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # First try 'value' column in 'account' table
                try:
                    cursor.execute("SELECT value FROM account WHERE public_addr = ?", 
                                  (validator_addr,))
                    row = cursor.fetchone()
                except:
                    row = None
                    
                # If that fails, try 'data' column in 'accounts' table
                if not row:
                    try:
                        cursor.execute("SELECT data FROM accounts WHERE public_addr = ?", 
                                      (validator_addr,))
                        row = cursor.fetchone()
                    except:
                        row = None
                
                conn.close()
                
                if row:
                    print(f"Found account in {db_path}!")
                    account_data = json.loads(row[0])
                    
                    # Create account object with broadcasting capability
                    class SimpleAccount:
                        def __init__(self):
                            self.db_path = db_path
                            
                        def save_to_db(self):
                            print("Saving validator account changes")
                            
                            # Save to the same DB we loaded from with all necessary fields
                            updated_data = {
                                'public_addr': self.public_addr,
                                'privateKey': self.privateKey,
                                'private_key': self.privateKey,
                                'staked': getattr(self, 'staked', 0),
                                # 'pending_rewards': getattr(self, 'pending_rewards', 0),
                                'unspent': getattr(self, 'unspent', 0),
                                'locked_until': getattr(self, 'locked_until', 0),
                                'staking_history': getattr(self, 'staking_history', '[]'),
                                'public_key': self.public_key.hex() 
                                    if hasattr(self, 'public_key') and 
                                       isinstance(self.public_key, bytes) 
                                    else getattr(self, 'public_key', '')
                            }
                            
                            try:
                                # First save locally
                                conn = sqlite3.connect(self.db_path)
                                cursor = conn.cursor()
                                
                                # Check if account table exists
                                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account'")
                                if cursor.fetchone():
                                    # Account table exists, try to update
                                    cursor.execute("UPDATE account SET value = ? WHERE public_addr = ?",
                                                 (json.dumps(updated_data), self.public_addr))
                                else:
                                    # Try accounts table instead
                                    cursor.execute("UPDATE accounts SET data = ? WHERE public_addr = ?",
                                                 (json.dumps(updated_data), self.public_addr))
                                
                                conn.commit()
                                conn.close()
                                print(f"Account updated successfully in {self.db_path}")
                                
                                # BROADCAST THE UPDATE TO OTHER NODES
                                self.broadcast_account_update(updated_data)
                                
                            except Exception as e:
                                print(f"Error saving account: {e}")
                                raise
                        
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
                                    local_port = 9000 + node_id
                                
                                if not local_port:
                                    match = re.search(r'node_(\d+)', self.db_path)
                                    if match:
                                        node_id = int(match.group(1))
                                        local_port = 9000 + node_id
                                    else:
                                        print("Warning: Could not detect local port, using fallback port 9000")
                                        local_port = 9000
                                    
                                # Get list of other nodes
                                node_db = NodeDB()
                                port_list = node_db.read_nodes() if hasattr(node_db, 'read_nodes') else node_db.read()
                                
                                broadcast_count = 0
                                for port in port_list:
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
                    
                    validator_account = SimpleAccount()
                    
                    # Set properties from account_data
                    validator_account.public_addr = account_data.get('public_addr')
                    
                    # Convert privateKey to integer if it's stored as string
                    priv_key = account_data.get('privateKey', account_data.get('private_key'))
                    if isinstance(priv_key, str):
                        try:
                            validator_account.privateKey = int(priv_key)
                            print(f"Converted privateKey from string to int: {validator_account.privateKey}")
                        except ValueError:
                            if priv_key.startswith('0x'):
                                validator_account.privateKey = int(priv_key, 16)
                            else:
                                validator_account.privateKey = priv_key
                    else:
                        validator_account.privateKey = priv_key
                    
                    # print(f"privateKey type: {type(validator_account.privateKey)}")
                    
                    # Get all required fields with fallbacks
                    validator_account.balance = account_data.get('balance', 0)
                    validator_account.staked = account_data.get('staked', account_data.get('stake', 0))
                    # validator_account.pending_rewards = account_data.get('pending_rewards', 0)
                    validator_account.unspent = account_data.get('unspent', 0)
                    validator_account.locked_until = account_data.get('locked_until', 0)
                    
                    # Handle staking history if available
                    if 'staking_history' in account_data:
                        history = account_data['staking_history']
                        if isinstance(history, str):
                            try:
                                validator_account.staking_history = json.loads(history)
                            except:
                                validator_account.staking_history = []
                        else:
                            validator_account.staking_history = history
                    else:
                        validator_account.staking_history = []
                    
                    # Handle public key
                    pub_key = account_data.get('public_key')
                    if isinstance(pub_key, str):
                        validator_account.public_key = bytes.fromhex(pub_key)
                    else:
                        validator_account.public_key = pub_key
                        
                    return validator_account
            except Exception as e:
                print(f"Error accessing database {db_path}: {e}")
                
    # If we get here, we couldn't find the account
    print(f"WARNING: Could not find validator account for {validator_addr}")
    return None

def blockheader_to_dict_for_db(blockheader):
    """Convert a BlockHeader object to a dict with all fields as hex strings for DB storage."""
    return {
        'version': blockheader.version,
        'prevBlockHash': blockheader.prevBlockHash.hex() if isinstance(blockheader.prevBlockHash, bytes) else blockheader.prevBlockHash,
        'merkleRoot': blockheader.merkleRoot.hex() if isinstance(blockheader.merkleRoot, bytes) else blockheader.merkleRoot,
        'timestamp': blockheader.timestamp,
        'validator_pubkey': blockheader.validator_pubkey.hex() if isinstance(blockheader.validator_pubkey, bytes) else blockheader.validator_pubkey,
        'signature': blockheader.signature.der().hex() if hasattr(blockheader.signature, 'der') else (blockheader.signature.hex() if isinstance(blockheader.signature, bytes) else blockheader.signature),
        'blockHash': blockheader.blockHash
    }

class Blockchain:
    def __init__(self, utxos, mem_pool,newBlockAvailable,secondaryChain,localHostPort, host):
        self.utxos = utxos
        self.mem_pool = mem_pool
        self.account_db = AccountDB()
        self.newBlockAvailable = newBlockAvailable
        self.secondaryChain = secondaryChain
        self.localHostPort = localHostPort
        self.host = host

    def write_on_disk(self,block):
        blockchainDB = BlockchainDB()
        blockchainDB.write(block)
        print(f"[DEBUG] Block written to DB: Height={block[0]['Height']} Hash={block[0]['BlockHeader']['blockHash']}")
        # Print the current chain for this node
        all_blocks = blockchainDB.read_all_blocks()
        print("[DEBUG] Current chain in DB:")
        for blk in all_blocks:
            print(f"  Height={blk['Height']} Hash={blk['BlockHeader']['blockHash']}")

    def fetch_last_block(self):
        blockchainDB = BlockchainDB()
        return blockchainDB.lastBlock()
    
    # def GenesisBlock(self):
    #     BlockHeight = 0
    #     prevBlockHash = ZERO_HASH
    #     self.addBlock(BlockHeight, prevBlockHash)
    #     self.buildUTXOS()

    # def GenesisBlock(self):
    #     BlockHeight = 0
    #     prevBlockHash = ZERO_HASH

    #     # Build initial UTXOs for each account
    #     from reset_accounts import ACCOUNTS
    #     tx_outs = []
    #     for addr, acc_data in ACCOUNTS.items():
    #         # Give as staked (StakingScript)
    #         script = StakingScript(addr, lock_time=0)  # lock_time=0 means immediately available for PoS
    #         tx_outs.append(TxOut(amount=acc_data['staked'], script_publickey=script))

    #     # Create a single genesis transaction with all outputs
    #     genesis_tx = Tx(version=1, tx_ins=[], tx_outs=tx_outs, locktime=0)
    #     genesis_tx.TxId = genesis_tx.id()

    #     # Create the genesis block with this transaction
    #     coinbaseTx = genesis_tx
    #     self.TxIds = [bytes.fromhex(coinbaseTx.id())]
    #     self.add_trans_in_block = [coinbaseTx]
    #     self.remove_spent_transactions = []



    
    def GenesisBlock(self):
        BlockHeight = 0
        prevBlockHash = ZERO_HASH
        self.Blocksize = 0
    
        # 1. Build initial UTXOs for each account, sorted by address
        from reset_accounts import ACCOUNTS
        tx_outs = []
        for addr in sorted(ACCOUNTS.keys()):
            acc_data = ACCOUNTS[addr]
            script = StakingScript(addr, lock_time=0)
            tx_outs.append(TxOut(amount=acc_data['staked'], script_publickey=script))
            h160 = decode_base58(addr)
            p2pkh_script = Script().p2pkh_script(h160)
            tx_outs.append(TxOut(amount=acc_data['unspent'], script_publickey=p2pkh_script))
    
        # 2. Create the genesis transaction
        genesis_tx = Tx(version=1, tx_ins=[], tx_outs=tx_outs, locktime=0)
        genesis_tx.TxId = genesis_tx.id()
        self.Blocksize += len(genesis_tx.serialise())
    
        # 3. Set up block transaction lists
        self.TxIds = [bytes.fromhex(genesis_tx.id())]
        self.add_trans_in_block = [genesis_tx]
        self.remove_spent_transactions = []
    
        # 4. Compute Merkle root
        merkle_root_bytes = merkle_root(self.TxIds)[::-1]
        merkleRoot_hex = merkle_root_bytes.hex()
    
        # 5. Use a fixed validator account and fixed timestamp
        validator_addr = sorted(ACCOUNTS.keys())[0]
        validator_account = account.get_account(validator_addr)
        if validator_account is None:
            raise Exception("No validator account found for genesis block.")
    
        fixed_timestamp = 0
    
        # 6. Create BlockHeader
        blockheader = BlockHeader(
            VERSION,
            prevBlockHash=bytes.fromhex(prevBlockHash),
            merkleRoot=bytes.fromhex(merkleRoot_hex),
            timestamp=fixed_timestamp,
            validator_pubkey=validator_account.public_key,
            signature=None
        )

        # (Re-assign validator_pubkey if needed after signing, to ensure it's not overwritten)
        blockheader.validator_pubkey = validator_account.public_key

        # 7. Sign the block header
        block_data = blockheader.serialise_without_signature()


        block_signature = self.sign_block(block_data, validator_account.privateKey)
        print(f"Block signature GENESIS BLOCK: {block_signature} of type {type(block_signature)}")
        blockheader.signature = bytes.fromhex(block_signature)
        blockheader.signature = Signature.parse(blockheader.signature) 
        print(f"Block signature: {block_signature} of type {type(block_signature)}")
    
        # 8. Verify signature
        public_key_hex = validator_account.public_key.hex()
        if not self.verify_block_signature(blockheader.to_dict(), bytes.fromhex(public_key_hex)):
            raise Exception("Invalid block signature. Genesis block rejected.")
    
        # 9. Compute blockHash
        blockheader.blockHash = hash256(blockheader.serialise_with_signature()).hex()
    
        # 10. Create the block (for broadcast)
        genesis_block = Block(
            Height=BlockHeight,
            Blocksize=self.Blocksize,
            BlockHeader=blockheader,
            TxCount=len(self.add_trans_in_block),
            Txs=self.add_trans_in_block,
        )

        serialized_header = blockheader.serialise_with_signature()

        # print("[DEBUG] Genesis block fields:")
        # print(f"  validator_addr: {validator_addr}")
        # print(f"  timestamp: {fixed_timestamp}")
        # print(f"  tx_outs: {[str(tx_out.__dict__) for tx_out in tx_outs]}")
        # print(f"  serialized header: {blockheader.serialise_with_signature().hex()}")

        new_block = Block.to_obj(genesis_block)
        self.BroadcastBlock(new_block)
        blockheader.to_hex()
        self.remove_spent_Transactions()
        self.remove_trans_from_mempool()
        self.store_uxtos_in_cache()
        self.convert_to_json()
        print(f"Block {BlockHeight} created successfully by Validator {validator_addr} with Signature {block_signature} with BlockHash {blockheader.blockHash}")
    
        new_block = Block(BlockHeight, self.Blocksize, blockheader.__dict__, len(self.TxJson), self.TxJson)
        self.write_on_disk([new_block.__dict__])
        time.sleep(5)
        self.buildUTXOS()
        print("[Node Setup] Genesis Block created and written to disk.")
        self.clean_mempool_against_chain(self.mem_pool)

    def get_all_blocks(self):
        """
        Return all blocks in the blockchain as Block objects.
        """
        db = BlockchainDB()
        blocks = db.read_all_blocks()  # This should return a list of blocks from the DB
        # If your db.read_all_blocks() returns a list of tuples/lists, extract the block dict/object
        return [Block.to_obj(block[0]) if isinstance(block, (list, tuple)) else Block.to_obj(block) for block in blocks]
    
    
    def startSync(self, block=None):
        from Blockchain.Backend.core.network.syncManager import syncManager

        """ start the sync node """
        try:
            node = NodeDB()
            portList = node.read_nodes()
            
            for port in portList:
                if self.localHostPort != port:
                    sync = syncManager(
                        host=self.host, 
                        port=port, 
                        blockchain=self, 
                        localHostPort=self.localHostPort, 
                        newBlockAvailable=self.newBlockAvailable, 
                        MemoryPool=self.mem_pool
                    )
                    try:
                        if block:
                            print(f"[Sender] Sending Block: {block.__dict__} to {port}")
                            sync.publishBlock(self.localHostPort-1000, port, block)
                        else:
                            sync.startDownload(self.localHostPort - 1000, port,True)                    
                    except Exception as err:
                        print(f"Error while downloading or uploading the Blockchain \n{err}")
                    
        except Exception as err:
            print(f"Error while downloading the Blockchain \n{err}")

    
    # def store_uxtos_in_cache(self):
    #     for tx in self.add_trans_in_block:
    #         self.utxos[tx.TxId] = tx

    def store_uxtos_in_cache(self):
        for tx in self.add_trans_in_block:
            for idx, tx_out in enumerate(tx.tx_outs):
                self.utxos[(tx.TxId, idx)] = tx_out
    
    def get_utxos(self):
        """Return the current UTXOs."""
        return dict(self.utxos)

    # def remove_spent_Transactions(self):
    #     for txId_index in self.remove_spent_transactions:
    #         if txId_index[0].hex() in self.utxos:

    #             if len(self.utxos[txId_index[0].hex()].tx_outs) < 2:
    #                 print(f" Spent Transaction removed {txId_index[0].hex()} ")
    #                 del self.utxos[txId_index[0].hex()]
    #             else:
    #                 prev_trans = self.utxos[txId_index[0].hex()]
    #                 self.utxos[txId_index[0].hex()] = prev_trans.tx_outs.pop(
    #                     txId_index[1]
    #                 )

    def remove_spent_Transactions(self):
        for txId_index in self.remove_spent_transactions:
            key = (txId_index[0].hex(), txId_index[1])
            if key in self.utxos:
                print(f"Spent Transaction removed {key}")
            del self.utxos[key]

    def doubleSpendingAttempt(self, tx):
        for txin in tx.tx_ins:
            key = (txin.prev_tx.hex(), txin.prev_index)
            if txin.prev_tx not in self.prevTxs and key in self.utxos:
                self.prevTxs.append(txin.prev_tx)
            else:
                return True
            
    
    def read_trans_from_mempool(self):
        """Read transactions from mem pool"""
        self.Blocksize = 80
        self.TxIds = []
        self.add_trans_in_block = []
        self.remove_spent_transactions = []
        self.prevTxs = []
        deleteTxs = []

        tempMemPool = dict(self.mem_pool)

        for tx_key, tx in tempMemPool.items():
            # print(f"Checking tx {tx_key} for inclusion in block...")
            if not hasattr(tx, 'tx_ins'):
                try:
                    tx = Tx.to_obj(tx)
                except Exception as e:
                    # print(f"Skipping invalid transaction from mem_pool: {e}")
                    deleteTxs.append(tx_key)
                    continue

            # print(f"  Inputs: {[ (txin.prev_tx.hex(), txin.prev_index) for txin in tx.tx_ins ]}")
            # print(f"  UTXO set keys: {list(self.utxos.keys())[:5]} ...")  # Print first 5 for brevity

            if not self.doubleSpendingAttempt(tx):
                print(f"  -> Adding tx {tx_key} to block")
                tx.TxId = tx_key
                self.TxIds.append(bytes.fromhex(tx_key))
                self.add_trans_in_block.append(tx)
                self.Blocksize += len(tx.serialise())
                for spent in tx.tx_ins:
                    self.remove_spent_transactions.append([spent.prev_tx, spent.prev_index])
            else:
                print(f"  -> Skipping tx {tx_key} due to double spending attempt or missing UTXO.")
                deleteTxs.append(tx_key)
                    
                for txId in deleteTxs:
                    if txId in self.mem_pool:
                        del self.mem_pool[txId]
        print(f"Transactions added to block: {self.TxIds}")
        print(f"Transactions removed from mempool: {deleteTxs}")

    def buildUTXOS(self):
        print("DEBUG: Starting new UTXO set construction (with missing reference logging).")
        allTxs = {}
        spent_outpoints = set()
        blocks = BlockchainDB().read()
        missing_references = []
    
        # Gather all transactions
        for block in blocks:
            for tx in block[0]['Txs']:
                allTxs[tx['TxId']] = tx
                print(f"DEBUG: Added transaction {tx['TxId']} to allTxs.")
    
        # Gather all spent outpoints, log missing references
        for block in blocks:
            for tx in block[0]['Txs']:
                for txin in tx['tx_ins']:
                    prev_txid = txin['prev_tx']
                    prev_index = txin['prev_index']
                    # Skip coinbase
                    if prev_txid == "0000000000000000000000000000000000000000000000000000000000000000":
                        continue
                    if prev_txid not in allTxs:
                        print(f"ERROR: Referenced transaction {prev_txid} is missing. Skipping input processing for transaction {tx['TxId']}.")
                        missing_references.append((tx['TxId'], prev_txid))
                        continue
                    spent_outpoints.add((prev_txid, prev_index))
                    print(f"DEBUG: Marked spent outpoint ({prev_txid}, {prev_index})")
    
        # Build UTXO set: only outputs not spent
        self.utxos = {}
        for txid, tx in allTxs.items():
            try:
                tx_obj = Tx.to_obj(tx)
                for idx, tx_out in enumerate(tx_obj.tx_outs):
                    if (txid, idx) not in spent_outpoints:
                        self.utxos[(txid, idx)] = tx_out
                        print(f"DEBUG: UTXO added: ({txid}, {idx}) amount={tx_out.amount}")
                    else:
                        print(f"DEBUG: Output ({txid}, {idx}) is spent, skipping.")
            except Exception as e:
                print(f"ERROR: Failed to process tx {txid}: {e}")
    
        # Log missing transactions
        if missing_references:
            print("WARNING: The following transactions reference missing inputs:")
            for missing_tx, missing_ref in missing_references:
                print(f"  Transaction {missing_tx} references missing transaction {missing_ref}.")
    
        # print("DEBUG: UTXO set construction complete. Final UTXO set:")
        # for k, v in self.utxos.items():
        #     print(f"  {k}: cmds={v.script_publickey.cmds} amount={v.amount}")
    
    # def buildUTXOS(self):
    #     allTxs = {}
    #     blocks = BlockchainDB().read()
    #     missing_references = []

    #     # Populate allTxs
    #     for block in blocks:
    #         for tx in block[0]['Txs']:
    #             allTxs[tx['TxId']] = tx
    #             # print(f"DEBUG: Added transaction {tx['TxId']} to allTxs.")

    #     print("DEBUG: Starting UTXO set construction.")
    #     for block in blocks:
    #         for tx in block[0]['Txs']:
    #             # print(f"DEBUG: Processing transaction {tx['TxId']}")
    #             for txin in tx['tx_ins']:
    #                 prev_txid = txin['prev_tx']

    #                 # Skip coinbase transactions
    #                 if prev_txid == "0000000000000000000000000000000000000000000000000000000000000000":
    #                     # print("DEBUG: Skipping coinbase transaction input.")
    #                     continue

    #                 # Check for referenced transaction
    #                 if prev_txid not in allTxs:
    #                     print(f"ERROR: Referenced transaction {prev_txid} is missing. Skipping input processing for transaction {tx['TxId']}.")
    #                     missing_references.append((tx['TxId'], prev_txid))
    #                     continue
                    
    #                 prev_tx = allTxs[prev_txid]
    #                 if len(prev_tx['tx_outs']) > txin['prev_index']:
    #                     # print(f"DEBUG: Spending output at index {txin['prev_index']} of transaction {prev_txid}.")
    #                     prev_tx['tx_outs'].pop(txin['prev_index'])
    #                     if not prev_tx['tx_outs']:
    #                         # print(f"DEBUG: All outputs spent for transaction {prev_txid}. Removing from allTxs.")
    #                         del allTxs[prev_txid]
    #                 else:
    #                     print(f"ERROR: Invalid prev_index {txin['prev_index']} for transaction {prev_txid}.")

    #     # Finalise UTXO set
    #     for txid, tx in allTxs.items():
    #         for idx, tx_out in enumerate(Tx.to_obj(tx).tx_outs):
    #             self.utxos[(txid, idx)] = tx_out
    #         # print(f"DEBUG: Added transaction {txid} to UTXO set.")

    #     # Log missing transactions
    #     if missing_references:
    #         print("WARNING: The following transactions reference missing inputs:")
    #         for missing_tx, missing_ref in missing_references:
    #             print(f"  Transaction {missing_tx} references missing transaction {missing_ref}.")

    #     print("DEBUG: UTXO set construction complete.")

    
    def doubleSpendingAttempt(self, tx):
        for txin in tx.tx_ins:
            key = (txin.prev_tx.hex(), txin.prev_index)
            if txin.prev_tx not in self.prevTxs and key in self.utxos:
                self.prevTxs.append(txin.prev_tx)
            else:
                print(f"[DoubleSpend] txin.prev_tx: {txin.prev_tx.hex()}, prev_index: {txin.prev_index}, key in utxos: {key in self.utxos}, prevTxs: {self.prevTxs}")
                return True
        return False

    
    "Read transactions from mem pool"
    def remove_trans_from_mempool(self):
        for tx in self.TxIds:
            if tx.hex() in self.mem_pool:
                del self.mem_pool[tx.hex()]

            
    def convert_to_json(self):
        self.TxJson = []
        for tx in self.add_trans_in_block:
            self.TxJson.append(tx.to_dict())

    def calculate_fee(self):
        self.input_amount = 0
        self.output_amount = 0

        for TxId_index in self.remove_spent_transactions:
            key = (TxId_index[0].hex(), TxId_index[1])
            if key in self.utxos:
                self.input_amount += self.utxos[key].amount
        
        for tx in self.add_trans_in_block:
            for tx_out in tx.tx_outs:
                self.output_amount += tx_out.amount
        
        self.fee = self.input_amount - self.output_amount
    

    # def select_validator(self):
    #     """Select a validator based on their stake using weighted random selection."""
    #     # Directly connect to the account DB file used by this AccountDB instance

    #     VALIDATOR_ADDRESS = '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh'

    #     try:
    #         connection = sqlite3.connect(self.account_db.filepath)
    #         cursor = connection.cursor()
    #         cursor.execute("SELECT data FROM account")
    #         rows = cursor.fetchall()
    #         connection.close()
    #     except Exception as e:
    #         raise Exception(f"Error reading account DB: {e}")

    #     validators = []
    #     for row in rows:
    #         try:
    #             # Expect row[0] to be a JSON string
    #             account_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    #             if (account_data.get('staked', 0) > 0 
    #                 and account_data.get('public_addr') != VALIDATOR_ADDRESS):
    #                 validators.append(account_data)
    #         except Exception as e:
    #             print(f"Error parsing account data: {e}")
    #             continue

    #     if not validators:
    #         raise Exception("No validators available. Ensure at least one account has a stake.")

    #     total_stake = sum(acc['staked'] for acc in validators)
    #     rand = random.uniform(0, total_stake)
    #     cumulative = 0
    #     for acc in validators:
    #         cumulative += acc['staked']
    #         if rand <= cumulative:
    #             return acc
    #     return validators[-1]

    
    
    def sign_block(self, block_data, private_key_int):
        """Sign the block data using the validator's private key."""
        # Convert private_key_int to integer if it's a string
        if isinstance(private_key_int, str):
            try:
                private_key_int = int(private_key_int)
                print(f"Converted private key to int in sign_block")
            except ValueError:
                # Try hex conversion if it starts with 0x
                if private_key_int.startswith('0x'):
                    private_key_int = int(private_key_int, 16)
                    print(f"Converted hex private key to int in sign_block")
                else:
                    print(f"ERROR: Cannot convert privateKey to int: {private_key_int}")
                    raise ValueError("Private key must be an integer or convertible to integer")
        
        priv_key = PrivateKey(private_key_int)
        # Hash the block data
        hashed_data = hashlib.sha256(block_data).digest()
        # Convert to integer
        z = int.from_bytes(hashed_data, 'big')
        # Sign
        signature_obj = priv_key.sign(z)
        return signature_obj.der().hex()  # return hex string
    
    def BroadcastBlock(self, block):
            # self.startSync(block)
            """Broadcast a block to all nodes in the network."""
            from Blockchain.Backend.core.network.syncManager import syncManager
            
            # Get the ports from NodeDB
            nodeDB = NodeDB()
            portList = nodeDB.read_nodes()
            
            if not portList:
                print("No nodes found to broadcast to")
                return
            
            for port in portList:
                if port == self.localHostPort:
                    continue
                try:
                    # Convert port if it's a DictProxy
                    port_value = dict(port) if hasattr(port, '__getitem__') else port
                    
                    # If port is still not an integer, try to extract it
                    if not isinstance(port_value, int):
                        if isinstance(port_value, dict) and 'port' in port_value:
                            port_value = port_value['port']
                        elif hasattr(port_value, '__iter__'):
                            # If it's some kind of collection, get the first item
                            port_value = next(iter(port_value))
                            
                    # Ensure we have an integer port number before proceeding
                    if not isinstance(port_value, int):
                        print(f"Skipping invalid port: {port_value} (type: {type(port_value)})")
                        continue
                        
                    print(f"[Sender] Sending Block: {block} to {port_value}")
                    sync = syncManager(host="127.0.0.1", port=port_value, MemoryPool={})
                    sync.publishBlock(self.localHostPort, port_value, block)
                    
                except Exception as e:
                    print(f"Error while downloading or uploading the Blockchain \n {e}")
            
    
    def verify_block_signature(self, blockheader_dict, validator_pubkey_bytes):
        """Verify the block's signature using the validator's public key."""
        blockheader = BlockHeader(
            version=blockheader_dict['version'],
            prevBlockHash=bytes.fromhex(blockheader_dict['prevBlockHash']),
            merkleRoot=bytes.fromhex(blockheader_dict['merkleRoot']),
            timestamp=blockheader_dict['timestamp'],
            validator_pubkey=validator_pubkey_bytes,
            signature=bytes.fromhex(blockheader_dict['signature']) if blockheader_dict['signature'] else None
        )
        # Reconstruct block data as bytes
        block_data = blockheader.serialise_without_signature()
        # print(f"Serialized Block Header for Verification: {block_data}")
        signature_obj = Signature.parse(blockheader.signature)
        # Use your PublicKey.parse(...) or appropriate method to get a PublicKey object
        pub_key = PublicKey.parse(validator_pubkey_bytes)
        # print(f"Public Key Bytes: {validator_pubkey_bytes}")
        
        # pub_key.verify(...) presumably wants (signature=..., z=...) or (signature=..., hashed_data=...)
        hashed_data = hashlib.sha256(block_data).digest()  # 32 bytes
        z = int.from_bytes(hashed_data, 'big')
        # print(f"Bytes Signature: {blockheader.signature}")
        return pub_key.verify(signature_obj, z)
    
    def clean_mempool_against_chain(self, mem_pool, blockchain=None):
        if blockchain is None:
            blockchain = self
        """
        Remove transactions from mem_pool that are already confirmed in the blockchain.
        Should be called after processing new blocks and before block creation.
        """
        confirmed_txids = set()
        try:
            for block in blockchain.get_all_blocks():
                for tx in getattr(block, 'Txs', []):
                    txid = None
                    # Try to extract TxId from object or dict
                    if hasattr(tx, "TxId") and tx.TxId:
                        txid = str(tx.TxId)
                    elif hasattr(tx, "id"):
                        try:
                            txid = str(tx.id())
                        except Exception:
                            pass
                    elif isinstance(tx, dict) and "TxId" in tx:
                        txid = str(tx["TxId"])
                    if txid:
                        confirmed_txids.add(txid)
                    else:
                        print(f"[Mempool Cleanup] Warning: Could not extract TxId from tx: {tx}")
        except Exception as e:
            print(f"[Mempool Cleanup] Error while collecting confirmed txids: {e}")

        removed = []
        for txid in list(mem_pool.keys()):
            if str(txid) in confirmed_txids:
                del mem_pool[txid]
                removed.append(txid)
        if removed:
            print(f"[Mempool Cleanup] Removed confirmed transactions from mempool: {removed}")
        else:
            print("[Mempool Cleanup] No confirmed transactions found in mempool.")
    
    def addBlock(self, BlockHeight, prevBlockHash,selected_validator=None):
        """Create and add a new block to the blockchain using PoS."""
        validator_addr = selected_validator  # Always a string
        print(f"Selected Validator: {validator_addr} PRINTED FROM ADD BLOCK")

        # Force reinitialization of the AccountDB connection in this thread.
        self.account_db.conn = None 
        
        # 1. Read transactions from memory pool
        self.read_trans_from_mempool()
        self.calculate_fee()
        timestamp = int(time.time())

        # 2. Use the provided validator data if available; otherwise, select one.
        # if selected_validator is None:
        #     validator = self.select_validator()
        # else:

        # Retrieve the validator's account so we can use their public address.
        validator_account = get_validator_account(validator_addr)
        if validator_account is None:
            raise Exception(f"Validator account {validator_addr} not found.")

        # 3. Create Coinbase Transaction
        coinbaseInstance = Coinbase_tx(BlockHeight, validator_addr)
        coinbaseTx = coinbaseInstance.coinbase_transaction()
        self.Blocksize += len(coinbaseTx.serialise())

        # 4. Adjust Coinbase Transaction with staking reward
        coinbaseTx.tx_outs[0].amount += self.fee  # Assuming fee is added to coinbase

         # 4a. Credit only the selected validator's account.
        total_reward = coinbaseTx.tx_outs[0].amount
        # Re-fetch the account to get the latest pending_rewards:
        validator_account = get_validator_account(validator_addr)
        # validator_account.pending_rewards += total_reward
        print(f"Validator {validator_addr} credited with {total_reward} TDC.")
        # print("New pending rewards:", validator_account.pending_rewards)
        validator_account.save_to_db()

        # 5. Insert the coinbase Tx at index 0
        self.TxIds.insert(0, bytes.fromhex(coinbaseTx.id()))
        self.add_trans_in_block.insert(0, coinbaseTx)

        # 6. Compute Merkle Root, already bytes (reversed), then .hex() -> is a hex string
        # So we get merkleRoot in hex form:
        merkle_root_bytes = merkle_root(self.TxIds)[::-1]  # merkle_root returns bytes, reversed => still bytes
        merkleRoot_hex = merkle_root_bytes.hex()           # Now is hex string

        # 7. Create the BlockHeader
        #    - prevBlockHash might be a hex string, so convert to bytes
        #    - merkleRoot_hex is a hex string, so convert to bytes
        blockheader = BlockHeader(
            VERSION,
            bytes.fromhex(prevBlockHash),         # convert hex str to bytes
            bytes.fromhex(merkleRoot_hex),        # convert hex str to bytes
            timestamp,
            validator_account.public_key,         # should already be bytes
            signature=None
        )
        
        # Instead of mining, have the validator sign the block

        # (Re-assign validator_pubkey if needed after signing, to ensure it's not overwritten)
        blockheader.validator_pubkey = validator_account.public_key

        # 8. Serialize the blockheader to get block_data (bytes)
        block_data = blockheader.serialise_without_signature()  # This must be bytes
        # print(f"Serialized Block Header for Signing: {block_data}")

        # 9. Sign the block_data
        block_signature = self.sign_block(block_data, validator_account.privateKey)
        blockheader.signature = bytes.fromhex(block_signature)
        blockheader.signature = Signature.parse(blockheader.signature)  # <--- ADD THIS LINE
        print(f"Block signature: {block_signature} of type {type(block_signature)}")

        # 10. Verify the block signature before adding to the blockchain
        public_key_hex = validator_account.public_key.hex()
        if not self.verify_block_signature(blockheader.to_dict(), bytes.fromhex(public_key_hex)):
            raise Exception("Invalid block signature. Block rejected.")
        
        # 11. Compute blockHash in hex
        blockheader.blockHash = hash256(blockheader.serialise_with_signature()).hex()

        # No need to mine; assume the block is valid if signed
        new_block = Block(BlockHeight, self.Blocksize, blockheader, len(self.add_trans_in_block),self.add_trans_in_block)
        # blockheader.to_bytes()

        serialized_header = blockheader.serialise_with_signature()
        # print(f"[Sender] Serialized BlockHeader: {serialized_header.hex()}")
        # print(f"[Sender] Block Signature: {blockheader.signature.hex()}")
        # computed_hash_sender = hash256(serialized_header).hex()
        # print(f"[Sender] Computed BlockHash: {computed_hash_sender}")

        new_block = Block.to_obj(new_block)
        self.BroadcastBlock(new_block)
        blockheader.to_hex()
        self.remove_spent_Transactions()
        # print(f"[DEBUG] MEMPOOL CONTENTS AT BLOCK CREATION: {list(self.mem_pool.keys())}")
        self.remove_trans_from_mempool()
        self.store_uxtos_in_cache()
        self.convert_to_json()
        print(f"Block {BlockHeight} created successfully by Validator {validator_addr} with Signature {block_signature} with BlockHash {blockheader.blockHash}")
        new_block = Block(BlockHeight, self.Blocksize, blockheader.__dict__, len(self.TxJson), self.TxJson)
        # Ensure all tx_outs are TxOut objects before serialization
        self.write_on_disk([new_block.__dict__])
        time.sleep(5)
        self.buildUTXOS()

        # print("[DEBUG] UTXO set rebuilt.")
        # print("[DEBUG][UTXO SET AFTER BLOCK]")
        for k, v in self.utxos.items():
            print(f"  {k}: cmds={v.script_publickey.cmds} amount={v.amount}")
        self.clean_mempool_against_chain(self.mem_pool)
        print("[DEBUG] Mempool cleaned against chain.")

    def setup_node(self):
        """
        Initialize the node by:
        - Checking if the blockchain exists
        - If no blockchain exists, wait for validator selection or genesis block from network
        - Building the UTXO set from the stored blockchain (if any)
        """
        last_block = self.fetch_last_block()
        if last_block is None:
            print("[Node Setup] No existing blockchain found. Waiting for validator selection or genesis block from network...")
            # Do NOT call self.GenesisBlock() here!
            # Just start syncManager to listen for blocks and valselect messages
            # (syncManager will call GenesisBlock if this node is selected)
        else:
            print(f"[Node Setup] Last block height is: {last_block[0]['Height']}")
            self.buildUTXOS()
            print("[Node Setup] UTXO set constructed.")

   
    # def setup_node(self):
    #     """
    #     Initialize the node by:
    #     - Checking if the blockchain exists
    #     - If no blockchain exists, setting a flag to indicate Genesis Block needs to be created later
    #     - Building the UTXO set from the stored blockchain (if any)
    #     - Starting the synchronization service to listen for incoming blocks and messages
    #     """
    #     # Check if there is an existing blockchain
    #     last_block = self.fetch_last_block()
    #     if last_block is None:
    #         print("[Node Setup] No existing blockchain found.")
    #         # Instead of creating Genesis Block now, set a flag
    #         self.needs_genesis = True
    #         print("[Node Setup] Genesis Block creation deferred until validator is selected.")
    #     else:
    #         print(f"[Node Setup] Last block height is: {last_block[0]['Height']}")
    #         # Set this to False since we already have a blockchain
    #         self.needs_genesis = False
            
    #         # Build the current UTXO set from the stored blockchain
    #         self.buildUTXOS()
    #         print("[Node Setup] UTXO set constructed.")
        
        # Start the sync process so the node can listen for incoming blocks and transactions
        # self.startSync()
        # print("[Node Setup] Sync service started. Node is now ready and waiting for validator selection.")
            
