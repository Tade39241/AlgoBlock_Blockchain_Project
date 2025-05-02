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
from threading import Lock # Or from multiprocessing import Lock if Processes need it
from multiprocessing import Lock

# from Blockchain.Frontend.run import main as web_main # Correct import path

import time
import random
import hashlib
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__) # Use logger

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
    def __init__(self, utxos, mem_pool,newBlockAvailable,secondaryChain,localHostPort, host,shared_lock):
        # --- CONFIGURE LOGGING HERE ---
        log_format = '%(asctime)s %(levelname)s: [PID %(process)d] %(message)s'
        # Ensure logging is configured in this process
        # Use force=True to override any existing config if necessary
        logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stderr, force=True)
        logging.info("Blockchain object __init__ called.")
        # --- END LOGGING CONFIG ---
        self.utxos = utxos
        self.mem_pool = mem_pool
        self.account_db = AccountDB()
        self.newBlockAvailable = newBlockAvailable
        self.secondaryChain = secondaryChain
        self.localHostPort = localHostPort
        self.host = host
        self.state_lock = shared_lock
        logging.info(f"Blockchain initialized for port {localHostPort}. Lock object received: {type(self.state_lock)}")

    def write_on_disk(self,block):
        db_instance = BlockchainDB()
        db_instance.write(block)
        print(f"[DEBUG] Block written to DB: Height={block[0]['Height']} Hash={block[0]['BlockHeader']['blockHash']}")
        # Print the current chain for this node
        all_blocks = db_instance.read_all_blocks()
        print("[DEBUG] Current chain in DB:")
        for blk in all_blocks:
            print(f"  Height={blk[0]['Height']} Hash={blk[0]['BlockHeader']['blockHash']}")

    def fetch_last_block(self):
        db_instance = BlockchainDB()
        return db_instance.lastBlock()
    
    def get_tip_hash(self):
        """
        Retrieves the block hash of the latest block in the local database.

        Returns:
            str: The hex string of the latest block's hash,
                 or ZERO_HASH if the blockchain is empty,
                 or None if an error occurs.
        """
        db = None # Use local instance for safety
        try:
            # Create a DB instance specific to this method call
            db = BlockchainDB() # Assumes patched __init__ sets correct path
            last_block_data = db.lastBlock() # Fetch the last block data

            if last_block_data:
                # Ensure consistent handling if lastBlock returns list or dict
                last_block_dict = last_block_data[0] if isinstance(last_block_data, list) else last_block_data

                # Navigate the dictionary structure safely using .get()
                tip_hash = last_block_dict.get('BlockHeader', {}).get('blockHash')

                if tip_hash and isinstance(tip_hash, str) and len(tip_hash) == 64:
                    # Found a valid-looking hash
                    # logger.debug(f"get_tip_hash: Found hash {tip_hash[:8]}...") # Optional debug
                    return tip_hash
                else:
                    # Found block data but hash is missing or invalid format
                    logger.error(f"get_tip_hash: Invalid or missing blockHash in last block data: {last_block_dict}")
                    return None # Indicate error reading hash
            else:
                # No blocks found in the database
                logger.info("get_tip_hash: No blocks found, returning ZERO_HASH.")
                return ZERO_HASH # Return the defined ZERO_HASH constant

        except Exception as e:
            logger.error(f"Error getting tip hash via Blockchain class: {e}", exc_info=True)
            return None # Indicate error
        finally:
            # Ensure connection is closed
            if db and db.conn:
                try:
                    db.conn.close()
                except Exception as e_close:
                     logger.warning(f"Ignoring error closing DB connection in get_tip_hash: {e_close}")

    def get_height(self):
        """Returns the current height of the blockchain by querying the database."""
        db_instance = None
        try:
            # Create a local instance to query the height
            db_instance = BlockchainDB()
            height = db_instance.get_height() # Call the method from db.py
            return height
        except Exception as e:
            logger.error(f"Error getting height via Blockchain class: {e}", exc_info=True)
            return -3 # Return a distinct error code for issues in this layer
        finally:
            # Ensure the connection created by the local db_instance is closed
            # (Assuming BlockchainDB's connect/methods handle this, otherwise add explicit close)
             if db_instance and db_instance.conn:
                  try:
                      db_instance.conn.close()
                      logger.debug("Closed DB connection in Blockchain.get_height")
                  except Exception as e_close:
                       logger.warning(f"Error closing DB connection in Blockchain.get_height: {e_close}")
    
    def update_utxo_set(self, block):
        """
        Incrementally updates the UTXO set based on the transactions
        within the given block. MUST be called with self.state_lock held.
        """
        if not isinstance(block, Block):
            try: block = Block.to_obj(block)
            except Exception as e:
                logger.error(f"Could not convert block data in update_utxo_set: {e}", exc_info=True)
                return

        logger.info(f"[UTXO Update] Updating for block {block.Height}") # Use block.Height
        outputs_to_remove = set()
        outputs_to_add = {}
        for tx in block.Txs:
            try: tx_id_hex = tx.id()
            except Exception: continue
            if not tx.is_coinbase():
                for tx_in in tx.tx_ins:
                    prev_tx_hex = tx_in.prev_tx.hex() if isinstance(tx_in.prev_tx, bytes) else str(tx_in.prev_tx)
                    outputs_to_remove.add((prev_tx_hex, tx_in.prev_index))
            for idx, tx_out in enumerate(tx.tx_outs):
                outputs_to_add[(tx_id_hex, idx)] = tx_out # Store TxOut object

        removed_count = 0
        for key in outputs_to_remove:
            if key in self.utxos:
                del self.utxos[key]; removed_count += 1
            # else: logger.warning(f"[UTXO Update] Remove failed: UTXO {key} not found.")

        added_count = 0
        for key, value in outputs_to_add.items():
            if key not in outputs_to_remove: # Handle same-block spend
                 self.utxos[key] = value; added_count += 1

        logger.info(f"[UTXO Update] Block {block.Height} complete. Added: {added_count}, Removed: {removed_count}. New size: {len(self.utxos)}")

    def clean_mempool(self, block):
        """
        Removes transactions included in the given block from the mempool.
        MUST be called with self.state_lock held.
        """
        if not isinstance(block, Block):
            try: block = Block.to_obj(block)
            except Exception as e:
                logger.error(f"Could not convert block data in clean_mempool: {e}", exc_info=True)
                return

        logger.info(f"[Mempool Clean] Cleaning for block {block.Height}")
        removed_count = 0
        for tx in block.Txs:
            try:
                tx_id_hex = tx.id()
                if tx_id_hex in self.mem_pool:
                    del self.mem_pool[tx_id_hex]
                    removed_count += 1
            except Exception: continue

        if removed_count > 0:
             logger.info(f"[Mempool Clean] Removed {removed_count} txs. New mempool size: {len(self.mem_pool)}")

    
    def GenesisBlock(self):
        BlockHeight = 0
        prevBlockHash = ZERO_HASH
        self.Blocksize = 0
    
        # 1. Build initial UTXOs for each account, sorted by address
        from reset_accounts import ACCOUNTS
        num_active = len(NodeDB().read_nodes())
        accounts = dict(list(ACCOUNTS.items())[:num_active])
        tx_outs = []
        for addr in sorted(accounts.keys()):
            acc_data = accounts[addr]
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
        validator_addr = sorted(accounts.keys())[0]
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
        genesis_block_obj = Block(
            Height=BlockHeight,
            Blocksize=self.Blocksize,
            BlockHeader=blockheader,
            TxCount=len(self.add_trans_in_block),
            Txs=self.add_trans_in_block,
        )
        print(f"Genesis block object initially: {genesis_block_obj.__dict__}")

        serialized_header = blockheader.serialise_with_signature()

        # print("[DEBUG] Genesis block fields:")
        # print(f"  validator_addr: {validator_addr}")
        # print(f"  timestamp: {fixed_timestamp}")
        # print(f"  tx_outs: {[str(tx_out.__dict__) for tx_out in tx_outs]}")
        # print(f"  serialized header: {blockheader.serialise_with_signature().hex()}")

        with self.state_lock:

            # new_block = Block.to_obj(genesis_block_obj)
            # print(f"Genesis block after calling to obj {new_block.__dict__}")
            block_dict_for_db = genesis_block_obj.to_dict() # Ensure this converts Tx/Header correctly
            block_dict_for_db['BlockHeader'] = blockheader_to_dict_for_db(blockheader)
            # Ensure Txs are dicts inside
            if block_dict_for_db['Txs'] and isinstance(block_dict_for_db['Txs'][0], Tx):
                    block_dict_for_db['Txs'] = [tx.to_dict() for tx in block_dict_for_db['Txs']]
            # Ensure Header is dict
            if isinstance(block_dict_for_db['BlockHeader'], BlockHeader):
                    block_dict_for_db['BlockHeader'] = block_dict_for_db['BlockHeader'].to_dict()

            # 11. Write to DB
            self.write_on_disk([block_dict_for_db])
            print(f"[DEBUG] Genesis block written to DB: Height={BlockHeight} Hash={blockheader.blockHash}")

            self.update_utxo_set(genesis_block_obj) # INSERT THIS
            self.clean_mempool(genesis_block_obj) # INSERT THIS (cleans genesis tx if somehow in mempool)

        logger.info("[Node Setup] Genesis Block created and state updated.")
        self.BroadcastBlock(genesis_block_obj)
        print(f"[DEBUG] Genesis block broadcasted: Height={BlockHeight} Hash={blockheader.blockHash}")

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
        node_id = self.localHostPort - 9000 if self.localHostPort and self.localHostPort >= 9000 else 'Unknown'
        logger.info(f"[Startup] Node {node_id} initiating sync with peers...")

        try:
            node = NodeDB()
            portList = node.read_nodes()
            print(f"DEBUG: startSync: self.localHostPort = {self.localHostPort} (type: {type(self.localHostPort)})")
            print(f"DEBUG: startSync: portList from read_nodes = {portList} (types: {[type(p) for p in portList]})")

            for port in portList:
                print(f"DEBUG: startSync loop: Checking port {port} (type: {type(port)}) against {self.localHostPort}")
                # --- Primary Check: Skip Self ---
                if port == self.localHostPort:
                    print(f"DEBUG: startSync loop: *** SKIPPING self port {port} ***")
                    logger.debug(f"[Startup] Skipping sync with self (port {port}).")
                    continue

                # --- Code past here ONLY runs for other peers ---
                print(f"DEBUG: startSync loop: *** PROCEEDING with peer port {port} ***")

                # --- REMOVE REDUNDANT IF ---
                # if self.localHostPort != port:  <-- DELETE THIS LINE

                # --- Keep the indented code ---
                sync = syncManager(
                    host=self.host,
                    port=port,
                    blockchain=self,
                    localHostPort=self.localHostPort,
                    newBlockAvailable=self.newBlockAvailable,
                    MemoryPool=self.mem_pool,
                    shared_lock=self.state_lock
                )
                try:
                    local_bind_port = 8000 + node_id # Use node-specific bind port
                    if block:
                        logger.info(f"[Sender] Sending Block height {getattr(block, 'Height', 'N/A')} to {port}")
                        sync.publishBlock(self.localHostPort, port, block) # publishBlock doesn't need bind port arg here
                    else:
                        logger.info(f"[Startup] Starting download from peer {port} (binding local {local_bind_port})...")
                        sync.startDownload(local_bind_port, port, False) # Pass correct args
                except ConnectionRefusedError:
                    logger.warning(f"[Startup] Connection refused by peer {port}.")
                except Exception as err:
                    logger.error(f"Error during sync with peer {port}: {err}", exc_info=True)
                # --- END REMOVE REDUNDANT IF --- # <-- DELETE THIS LINE (or the block it closes)

        except Exception as err:
            logger.error(f"Error during startSync setup: {err}", exc_info=True)
        finally:
            logger.info(f"[Startup] Node {node_id} initial sync process finished.")


    
    # def store_uxtos_in_cache(self):
    #     for tx in self.add_trans_in_block:
    #         self.utxos[tx.TxId] = tx

    def store_uxtos_in_cache(self):
        for tx in self.add_trans_in_block:
            for idx, tx_out in enumerate(tx.tx_outs):
                self.utxos[(tx.TxId, idx)] = tx_out

    def get_utxos(self):
            """
            Return a copy of the current UTXO set.
            Acquires the shared lock to ensure a consistent snapshot.
            """
            # --- Acquire Lock ---
            with self.state_lock:
                # --- Create and return a regular dictionary copy ---
                utxo_copy = dict(self.utxos)
                # Optional: Add logging to confirm size
                logger.debug(f"get_utxos: Returning UTXO copy with {len(utxo_copy)} items.")
            # --- Release Lock ---
            return utxo_copy

    def remove_spent_Transactions(self):
        for txId_index in self.remove_spent_transactions:
            key = (txId_index[0].hex(), txId_index[1])
            if key in self.utxos:
                print(f"Spent Transaction removed {key}")
            del self.utxos[key]

    def read_trans_from_mempool(self,mempool_copy,utxo_snapshot):
        """Reads valid transactions from mempool for block creation."""
        logger.info("Reading transactions from mempool...")
        selected_txs = []
        block_data_size = 0
        max_block_size = 4_000_000
        inputs_spent_in_block = set() # Track inputs spent IN THIS BLOCK

        # --- Acquire Lock (Caller Responsibility) ---
        # with self.state_lock: # Assuming lock is held by addBlock

        logger.debug(f"Mempool size: {len(mempool_copy)}, UTXO snapshot size: {len(utxo_snapshot)}")

        for tx_id, tx_obj_or_dict in mempool_copy.items():
            # Ensure tx_obj is a Tx object
            if not isinstance(tx_obj_or_dict, Tx):
                 try: tx_obj = Tx.to_obj(tx_obj_or_dict)
                 except Exception as e:
                     logger.warning(f"Skipping invalid mempool entry {tx_id[:8]}: {e}")
                     continue
            else:
                tx_obj = tx_obj_or_dict

            # Check size first
            try: tx_size = len(tx_obj.serialise())
            except: continue
            if block_data_size + tx_size > max_block_size: continue

            # --- Use the new validation method ---
            is_valid, tx_inputs_used = self.doubleSpendingAttempt(tx_obj, utxo_snapshot, inputs_spent_in_block)
            # --- End Use new method ---

            if is_valid:
                selected_txs.append(tx_obj)
                inputs_spent_in_block.update(tx_inputs_used) # Add used inputs to the set
                block_data_size += tx_size
                logger.debug(f"Selected Tx: {tx_id[:8]}, Block data size: {block_data_size}")

        # --- Lock released by caller ---
        logger.info(f"Selected {len(selected_txs)} transactions. Data size: {block_data_size}")
        return selected_txs, block_data_size

    def buildUTXOS(self):
        """
        Rebuilds the UTXO set by scanning the entire blockchain stored in the database.
        This version assumes the DB read method returns a list of lists, e.g., [[block_dict_0], [block_dict_1], ...].
        It correctly updates the shared self.utxos dictionary proxy.
        """
        logger.info("Rebuilding UTXO set from blockchain data...")
        allTxs = {}             # { txid_hex: tx_dict }
        spent_outpoints = set() # { (txid_hex, output_index_int) }
        blocks_data = []        # Holds data read from DB
        db = None               # DB connection object
        new_utxos_temp = {}     # { (txid_hex, output_index_int): TxOut_object }
        missing_references = [] # Track missing parent transactions

        try:
            # --- Step 1: Read all blocks from Database ---
            db = BlockchainDB() # Assumes this gets the correct DB path for the node
            # Use the DB method that returns list of lists: [[block_dict]]
            # If you have both read() and read_all_blocks(), choose the one returning [[dict]]
            blocks_data = db.read_all_blocks()
            # If read_all_blocks() returns [[dict]], use that instead:
            # blocks_data = db.read_all_blocks()

            if not blocks_data:
                 logger.warning("buildUTXOS: No blocks found in database. Clearing UTXO set.")
                 if hasattr(self, 'utxos') and self.utxos is not None and hasattr(self.utxos, 'clear'):
                     try:
                         self.utxos.clear()
                     except Exception as e_clear:
                         logger.error(f"buildUTXOS: Failed to clear shared UTXO dict: {e_clear}")
                 return # Nothing more to do

            logger.debug(f"buildUTXOS: Read {len(blocks_data)} block items from DB.")

            # --- Step 2: Gather all transactions ---
            logger.debug("buildUTXOS: Phase 1 - Gathering all transactions...")
            for block_item in blocks_data:
                # Validate block_item structure: must be a non-empty list containing a dict
                if not isinstance(block_item, list) or not block_item:
                    logger.warning(f"buildUTXOS: Skipping block item with unexpected format: {type(block_item)}")
                    continue
                block_data = block_item[0] # Extract the dictionary
                if not isinstance(block_data, dict):
                    logger.warning(f"buildUTXOS: Inner block data is not a dictionary: {type(block_data)}")
                    continue

                # Process transactions within the block dictionary
                for tx_data in block_data.get('Txs', []):
                    if isinstance(tx_data, dict) and 'TxId' in tx_data:
                        txid = tx_data['TxId']
                        allTxs[txid] = tx_data # Store the transaction dictionary
                    else:
                         logger.warning(f"buildUTXOS: Skipping tx with unexpected format or missing TxId: {type(tx_data)}")
            logger.debug(f"buildUTXOS: Gathered {len(allTxs)} total transactions.")


            # --- Step 3: Identify all spent outputs ---
            logger.debug("buildUTXOS: Phase 2 - Identifying spent outputs...")
            for block_item in blocks_data:
                 # Same validation as above
                 if not isinstance(block_item, list) or not block_item: continue
                 block_data = block_item[0]
                 if not isinstance(block_data, dict): continue

                 # Process transactions to find inputs
                 for tx_data in block_data.get('Txs', []):
                     if not isinstance(tx_data, dict): continue
                     tx_id_current = tx_data.get('TxId', 'N/A') # For logging context

                     for txin_data in tx_data.get('tx_ins', []):
                          if not isinstance(txin_data, dict):
                              logger.warning(f"buildUTXOS: Tx {tx_id_current} has invalid tx_in format: {type(txin_data)}")
                              continue

                          prev_txid = txin_data.get('prev_tx')
                          prev_index = txin_data.get('prev_index')

                          # Skip coinbase input (prev_txid is all zeros)
                          if prev_txid == ZERO_HASH or prev_txid == "0000000000000000000000000000000000000000000000000000000000000000":
                              continue

                          # Check if essential data is present
                          if prev_txid and prev_index is not None:
                              # Check if the transaction referenced by the input actually exists
                              if prev_txid not in allTxs:
                                   logger.error(f"ERROR: Referenced transaction {prev_txid} (needed by tx {tx_id_current}) is missing!")
                                   missing_references.append((tx_id_current, prev_txid))
                                   # Do not mark as spent if the parent transaction is missing
                              else:
                                   # Mark this output as spent
                                   spent_outpoints.add((prev_txid, prev_index))
                                   # logger.debug(f"DEBUG: Marked spent outpoint ({prev_txid}, {prev_index}) by tx {tx_id_current}")
                          else:
                               logger.warning(f"buildUTXOS: Tx {tx_id_current} has tx_in with missing prev_tx or prev_index: {txin_data}")

            logger.debug(f"buildUTXOS: Identified {len(spent_outpoints)} spent outpoints.")
            if missing_references:
                 logger.warning("buildUTXOS: Found references to missing transactions.")
                 # Log details if needed for debugging deeper issues
                 # for missing_tx, missing_ref in missing_references:
                 #     logger.warning(f"  Tx {missing_tx} references missing Tx {missing_ref}.")


            # --- Step 4: Build the new UTXO set (in a temporary dictionary) ---
            logger.debug("buildUTXOS: Phase 3 - Building new UTXO set from unspent outputs...")
            count_added = 0
            for txid, tx_data in allTxs.items():
                try:
                    # Convert transaction dictionary back to Tx object to access TxOut objects easily
                    # Ensure Tx.to_obj can handle the dictionary format stored in the DB
                    tx_obj = Tx.to_obj(tx_data)
                    for idx, tx_out in enumerate(tx_obj.tx_outs):
                        # Check if this specific output (txid, idx) was marked as spent
                        if (txid, idx) not in spent_outpoints:
                            # If not spent, add the TxOut OBJECT to the temporary dictionary
                            new_utxos_temp[(txid, idx)] = tx_out
                            count_added += 1
                        # else:
                            # logger.debug(f"DEBUG: Output ({txid}, {idx}) is spent, skipping.")
                except Exception as e:
                    # Log error converting/processing specific transaction but continue with others
                    logger.error(f"ERROR: Failed to process tx {txid} for UTXO build: {e}", exc_info=True)

            logger.debug(f"buildUTXOS: Added {count_added} UTXOs to temporary set.")


            # --- Step 5: Update the shared UTXO dictionary proxy ---
            # This is the crucial part for multi-processing
            if hasattr(self, 'utxos') and self.utxos is not None:
                # Check if it's a proxy supporting clear/update (basic check)
                with self.state_lock:
                        # --- Start of locked section ---
                    logger.info(f"buildUTXOS: Acquiring lock and updating shared UTXO proxy (size before: {len(self.utxos)})...")
                    if hasattr(self.utxos, 'clear') and hasattr(self.utxos, 'update'):
                        logger.info(f"buildUTXOS: Clearing and updating shared UTXO dictionary proxy (size before clear: {len(self.utxos)})...")
                        self.utxos.clear()          # Clear the existing shared dictionary
                        self.utxos.update(new_utxos_temp) # Update with items from the temporary dict
                        logger.info(f"buildUTXOS: Shared UTXO dictionary proxy updated. New size: {len(self.utxos)}")
                    else:
                        # This case should ideally not happen if initialized correctly with a Manager.dict()
                        logger.error("buildUTXOS CRITICAL ERROR: self.utxos object does not support clear/update (it's not the expected dict proxy?). Cannot update shared state.")
                        # If this happens, state will be inconsistent between processes.
            else:
                logger.error("buildUTXOS CRITICAL ERROR: self.utxos attribute not found or is None. Cannot update shared state.")

        except Exception as e_main:
             # Catch any unexpected errors during the whole process
             logger.error(f"Major error during buildUTXOS execution: {e_main}", exc_info=True)

        logger.info("buildUTXOS method finished.")
 
    def doubleSpendingAttempt(self, tx_obj, utxo_snapshot, inputs_in_this_block):
        """
        Checks if a transaction is valid for inclusion in the current block.
        Verifies that:
          1. All inputs exist in the provided UTXO snapshot.
          2. No input has already been spent within the current block construction.

        Args:
            tx_obj (Tx): The transaction object to validate.
            utxo_snapshot (dict): A snapshot of the current UTXO set {(tx_hash, index): TxOut}.
            inputs_in_this_block (set): A set of UTXO keys {(tx_hash, index)} already
                                        spent by prior transactions in the block being built.

        Returns:
            bool: True if the transaction is valid for the block, False otherwise.
            set: A set containing the input keys {(tx_hash, index)} used by this transaction
                 (empty set if invalid).
        """
        if not hasattr(tx_obj, 'tx_ins') or not tx_obj.tx_ins:
             logger.warning(f"Transaction {tx_obj.id()[:8]} has no inputs.")
             return False, set() # Invalid if no inputs

        tx_inputs_keys = set()
        for tx_in in tx_obj.tx_ins:
            # Ensure prev_tx is bytes before calling .hex()
            prev_tx_hex = tx_in.prev_tx.hex() if isinstance(tx_in.prev_tx, bytes) else str(tx_in.prev_tx)
            input_key = (prev_tx_hex, tx_in.prev_index)

            # Check 1: Already spent within THIS block?
            if input_key in inputs_in_this_block:
                logger.debug(f"Tx {tx_obj.id()[:8]} invalid: Input {input_key} double spent within this block.")
                return False, set()

            # Check 2: Exists in the provided UTXO snapshot?
            if input_key not in utxo_snapshot:
                logger.debug(f"Tx {tx_obj.id()[:8]} invalid: Input {input_key} not found in UTXO snapshot.")
                return False, set()

            # If valid so far, add to the set for this transaction
            tx_inputs_keys.add(input_key)

        # If all inputs passed checks
        return True, tx_inputs_keys

    
    "Read transactions from mem pool"
    def remove_trans_from_mempool(self):
        for tx in self.TxIds:
            if tx.hex() in self.mem_pool:
                del self.mem_pool[tx.hex()]

            
    def convert_to_json(self):
        self.TxJson = []
        for tx in self.add_trans_in_block:
            self.TxJson.append(tx.to_dict())

    def calculate_fee(self, tx_objs_in_block, utxo_snapshot):
        """Calculates total fee for a list of transactions.
           MUST be called with self.state_lock held.
        """
        total_input = 0
        total_output = 0
        # --- Acquire Lock (Caller Responsibility) ---
        for tx in tx_objs_in_block:
            for tx_out in tx.tx_outs:
                total_output += tx_out.amount
            if not tx.is_coinbase(): # Should not be called on coinbase anyway
                for tx_in in tx.tx_ins:
                    prev_tx_hex = tx_in.prev_tx.hex() if isinstance(tx_in.prev_tx, bytes) else str(tx_in.prev_tx)
                    input_key = (prev_tx_hex, tx_in.prev_index)
                    if input_key in utxo_snapshot:
                         input_tx_out = utxo_snapshot[input_key]
                         if hasattr(input_tx_out, 'amount'): total_input += input_tx_out.amount
                         else: raise ValueError(f"Invalid UTXO data (no amount) for {input_key}")
                    else: raise ValueError(f"UTXO not found for fee calc: {input_key}")

        fee = total_input - total_output
        if fee < 0: fee = 0
        logger.info(f"Calculated block fee: {fee}")
        return fee
    
    
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
    
    
    def addBlock(self, BlockHeight, prevBlockHash, selected_validator=None):
        """Creates, validates, applies, and broadcasts a new PoS block."""
        logger.info(f"Attempting to add block {BlockHeight} (Prev: {prevBlockHash[:8]})")
        validator_addr = selected_validator

        mempool_snapshot = {}
        utxo_snapshot = {}

        # --- Acquire Lock for reading mempool/utxos and later state update ---
        with self.state_lock:
            mempool_snapshot = dict(self.mem_pool)
            utxo_snapshot = dict(self.utxos)
        # --- Release Lock Temporarily for slower ops ---

        try:
            # 1. Read transactions & Calculate fee (under lock)
            selected_txs, block_data_size = self.read_trans_from_mempool(mempool_snapshot, utxo_snapshot)
            fee = self.calculate_fee(selected_txs, utxo_snapshot)
        except ValueError as e: # Catch UTXO not found during fee calculation
                logger.error(f"Cannot create block {BlockHeight}: {e}")
                return # Exit block creation (lock is released)
        except Exception as e:
                logger.error(f"Error reading mempool or calculating fee for block {BlockHeight}: {e}", exc_info=True)
                return # Exit block creation (lock is released)
 

        timestamp = int(time.time())

        # --- Get Validator Info (outside lock) ---
        validator_account = get_validator_account(validator_addr)
        if not validator_account: logger.error(f"Validator account {validator_addr} not found."); return

        # --- Create Coinbase Tx (outside lock) ---
        coinbaseInstance = Coinbase_tx(BlockHeight, validator_addr)
        coinbaseTx = coinbaseInstance.coinbase_transaction()
        if not coinbaseTx: logger.error(f"Coinbase creation failed for block {BlockHeight}."); return
        coinbase_size = len(coinbaseTx.serialise())
        # Adjust coinbase amount
        coinbaseTx.tx_outs[0].amount += fee
        logger.info(f"Coinbase created for block {BlockHeight}. Fee added: {fee}")
        coinbase_id_hex = coinbaseTx.id()

        # --- Combine Txs & Calculate Merkle Root ---
        final_tx_objs = [coinbaseTx] + selected_txs

        tx_ids_for_merkle_hex = []
        tx_ids_for_merkle_bytes = []
        try:
            for tx in final_tx_objs:
                tx_id_hex = tx.id()
                tx_ids_for_merkle_hex.append(tx_id_hex)
                tx_ids_for_merkle_bytes.append(bytes.fromhex(tx_id_hex))
            logger.debug(f"[PID {os.getpid()}] [MerkleCalc Send] TxIDs for Block {BlockHeight}: {tx_ids_for_merkle_hex}")
        except Exception as e_id:
            logger.error(f"[PID {os.getpid()}] Error getting TxIDs for Merkle calculation: {e_id}", exc_info=True)
            return None

        # Calculate Merkle Root using the derived bytes list
        merkle_root_bytes = merkle_root(tx_ids_for_merkle_bytes)[::-1]
        print(f"[PID {os.getpid()}] Merkle Root for Block {BlockHeight}: {merkle_root_bytes.hex()}",flush=True)

        # --- Final Block Size ---
        # Approx header size + coinbase + selected txs data size
        # Note: BlockHeader.serialise_with_signature() includes sig length byte + sig
        approx_header_size = 4 + 32 + 32 + 4 + 33 + 1 + 75 # Rough estimate (version, prev, merkle, time, pubkey, siglen, max_sig_len)
        final_block_size = approx_header_size + coinbase_size + block_data_size

        # --- Create Block Header ---
        blockheader = BlockHeader(
            VERSION,
            bytes.fromhex(prevBlockHash), # Ensure prevBlockHash is bytes
            merkle_root_bytes,
            timestamp,
            validator_account.public_key, # Should be bytes
            signature=None
        )

        # --- Sign Block Header ---
        try:
            block_data_to_sign = blockheader.serialise_without_signature()
            block_signature_hex = self.sign_block(block_data_to_sign, validator_account.privateKey)
            blockheader.signature = Signature.parse(bytes.fromhex(block_signature_hex))
        except Exception as e: logger.error(f"Signing block {BlockHeight} failed: {e}"); return

        # --- Compute Final Block Hash ---
        blockheader.blockHash = blockheader.generateBlockHash() # Uses serialise_with_signature()
        logger.info(f"Block {BlockHeight} signed. Hash: {blockheader.blockHash[:8]}")


        # --- Create Final Block Object ---
        new_block_obj = Block(
            BlockHeight,
            final_block_size, # Use calculated size
            blockheader,      # Header OBJECT
            len(final_tx_objs),
            final_tx_objs     # List of Tx OBJECTS
        )

         # 1. Double-check chain tip
        db_instance = BlockchainDB() # Local instance for check
        last_block = db_instance.lastBlock()
        if db_instance.conn: db_instance.conn.close() # Close connection
        current_height = -1; tip_hash = ZERO_HASH
        if last_block:
                last_block = last_block[0] if isinstance(last_block, list) else last_block
                current_height = last_block.get('Height', -1)
                tip_hash = last_block.get('BlockHeader', {}).get('blockHash', ZERO_HASH)

        if BlockHeight != current_height + 1 or prevBlockHash != tip_hash:
            logger.warning(f"Chain tip changed before block {BlockHeight} could be added. Discarding.")
            return # Discard block
        
        # 2. Write to DB
        try:
            block_dict_for_db = new_block_obj.to_dict() # Convert OBJECT to DICT for DB
            # Ensure nested parts are dicts/serializable
            if block_dict_for_db.get('Txs') and isinstance(block_dict_for_db['Txs'][0], Tx): block_dict_for_db['Txs'] = [tx.to_dict() for tx in block_dict_for_db['Txs']]
            if isinstance(block_dict_for_db.get('BlockHeader'), BlockHeader): block_dict_for_db['BlockHeader'] = block_dict_for_db['BlockHeader'].to_dict()
            self.write_on_disk([block_dict_for_db]) # Write DICT
        except Exception as e:
                logger.error(f"CRITICAL: Failed DB write for block {BlockHeight}: {e}. State inconsistent!", exc_info=True)
                return # Stop

        # --- Acquire Lock for Final Check, DB Write, State Update ---
        with self.state_lock:

            if BlockHeight != current_height + 1 or prevBlockHash != tip_hash:
                logger.warning(f"Chain tip changed before block {BlockHeight} state could be updated (Block was already written!). Potential orphan.")
                # Decide recovery strategy - maybe mark block as orphan? For now, just return.
                return # Discard state update, block is already in DB but won't be part of main chain state *yet*.
        
            try:
                self.update_utxo_set(new_block_obj) # Update shared memory
                self.clean_mempool(new_block_obj)   # Update shared memory
                logger.info(f"Block {BlockHeight} state (UTXO/Mempool) updated.")
            except Exception as e_state:
                    # This is tricky - DB write succeeded, but state update failed. State is now INCONSISTENT!
                    logger.critical(f"CRITICAL ERROR: DB write for block {BlockHeight} succeeded, but state update FAILED: {e_state}. STATE INCONSISTENT!", exc_info=True)
                    # Need robust error handling / recovery / node shutdown here.
                    # For now, just log and potentially exit.
                    # raise e_state # Or sys.exit()
                    return
           
        # --- Release Lock ---

        try:
            # Apply reward logic here if not done elsewhere, e.g., update balance
            validator_account.save_to_db()
            logger.info(f"Updated validator account {validator_addr} state post-block.")
        except Exception as e:
            logger.warning(f"Failed to save validator account {validator_addr} state post-block: {e}")

        # --- Update Validator Account State (After block confirmed locally) ---

        # 4. Broadcast the Block OBJECT
        self.BroadcastBlock(new_block_obj)
        logger.info(f"Block {BlockHeight} with hash {new_block_obj.BlockHeader.blockHash} broadcasted.")

    def setup_node(self):
        """
        Initialize the node by:
        - Checking if the blockchain exists
        - If no blockchain exists, wait for validator selection or genesis block from network
        - Building the UTXO set from the stored blockchain (if any)
        """
        logging.info("Entering setup_node()") # Log entry to setup_node
        try:
            last_block = self.fetch_last_block()
            if last_block is None:
                print("[Node Setup] No existing blockchain found. Waiting for validator selection or genesis block from network...")
                logging.info("[Node Setup] No existing blockchain found. Waiting...")
            else:
                print(f"[Node Setup] Last block height is: {last_block[0]['Height']}")
                self.buildUTXOS()
                print("[Node Setup] UTXO set constructed.")
        except Exception as e:
            print(f"[Node Setup] Error during setup: {e}")
            logging.error(f"Error during setup_node: {e}")
