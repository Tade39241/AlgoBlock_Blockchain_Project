import logging
import sys
sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoWBlockchain/blockchain_code')

import copy
import configparser
from multiprocessing import Lock # Import Lock
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.util.util import hash256, int_to_little_endian, little_endian_to_int, merkle_root, target_to_bits, bits_to_targets
from Blockchain.Backend.core.database.db import BlockchainDB, NodeDB
from Blockchain.Backend.core.Tx import Coinbase_tx, Tx, TxOut
from multiprocessing import Process, Manager
# from Blockchain.Frontend.run import main
from Blockchain.Backend.core.network.syncManager import syncManager
# from Blockchain.client.autoBroadcastTx import autoBroadcast
from Blockchain.Backend.util.reorg_manager import ReorgManager

import time
import json
import base58
import traceback

 
# --- Add this basic configuration near the top ---
# Configure logging for this module/process
log_format = '%(message)s'
# Log INFO level messages and above to standard error
logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stderr)
# You could also configure a FileHandler here if you want logs in a separate file per process
# --- End configuration ---

# Get a logger for this module
logger = logging.getLogger('blockchain')


ZERO_HASH = '0' * 64
VERSION = 1
INITIAL_TARGET = 0x0000FFFF00000000000000000000000000000000000000000000000000000000
MAX_TARGET     = 0x0000ffff00000000000000000000000000000000000000000000000000000000

"""
# Calculate new Target to keep our Block mine time under 5 minutes 
# Reset Block Difficulty after every 10 Blocks
"""
AVERAGE_BLOCK_MINE_TIME = 120
RESET_DIFFICULTY_AFTER_BLOCKS = 10
AVERAGE_MINE_TIME = AVERAGE_BLOCK_MINE_TIME * RESET_DIFFICULTY_AFTER_BLOCKS

class Blockchain:
    def __init__(self,utxos, mem_pool, newBlockAvailable, secondaryChain,localHostPort=None, localHost=None,
                 node_id=None,db_path=None, my_public_addr=None):
        self.mem_pool = mem_pool
        self.utxos = utxos
        self.newBlockAvailable = newBlockAvailable
        self.secondaryChain = secondaryChain # Stores potential fork blocks {hash: BlockObject}
        self.current_target = INITIAL_TARGET
        self.bits = target_to_bits(INITIAL_TARGET)
        self.localHostPort = localHostPort  # Add this line
        self.host = localHost  # Add this line
        self.my_public_addr = None  # Initialize with None
        self.node_id = node_id
        self.my_public_addr = my_public_addr
        self.db_path = db_path
        self.db = BlockchainDB(db_path=db_path,node_id=self.node_id) # Create DB instance per node 
        self.state_lock = Lock()
        

        self.reorg_manager = ReorgManager(
                utxos=self.utxos,
                mem_pool=self.mem_pool,
                secondaryChain=self.secondaryChain,
                db=self.db,
                node_id=self.node_id,
                lock = self.state_lock
            )

    def write_on_disk(self,block):
        try:
            # Assuming block is a dict here based on addBlock usage
            self.db.write(block)
        except Exception as e:
             logger.error(f"[WriteOnDisk] Error: {e}", exc_info=True)

    def fetch_last_block(self):
        return self.db.lastBlock()
    
    def get_utxos(self):
        """Return the current UTXOs."""
        return dict(self.utxos)
    
    def get_last_block_hash(self):
        """Returns the hash of the last block as bytes, or ZERO_HASH bytes."""
        last_block_dict = self.fetch_last_block()
        if last_block_dict:
            # Handle potential list wrapping from DB read
            block_data = last_block_dict[0] if isinstance(last_block_dict, list) and len(last_block_dict) == 1 else last_block_dict
            if isinstance(block_data, dict) and 'BlockHeader' in block_data:
                block_hash_hex = block_data['BlockHeader'].get('blockHash')
                if block_hash_hex:
                    try:
                        return bytes.fromhex(block_hash_hex)
                    except (TypeError, ValueError):
                        logger.error(f"[get_last_block_hash] Error converting hash hex '{block_hash_hex}' to bytes.")
                        # Fall through to return ZERO_HASH bytes
                else:
                    logger.warning("[get_last_block_hash] 'blockHash' key missing in BlockHeader.")
            else:
                logger.warning(f"[get_last_block_hash] Unexpected last block format: {type(block_data)}")
        # Return ZERO_HASH as bytes if no block found or error occurred
        try:
            # Ensure ZERO_HASH exists and is a hex string
            zero_hash_hex = getattr(self, 'ZERO_HASH', '0' * 64)
            return bytes.fromhex(zero_hash_hex)
        except (TypeError, ValueError):
            logger.error("[get_last_block_hash] Error converting ZERO_HASH to bytes. Returning default.")
            return bytes.fromhex('0' * 64) # Default fallback

    # """ start the sync node """
    # def startSync(self, block=None):
    #     try:
    #         print(f"[startSync] Starting sync with block: {block.BlockHeader.blockHash if block else 'None'}")
    #         node_db_instance = NodeDB(node_id=self.node_id) # NEW - Relies on BaseDB path logic
    #         portList = node_db_instance.read_nodes()
    #         print(f"[startSync DEBUG]: Port list for sync: {portList}")

    #         for port in portList:
    #             if self.localHostPort != port:
    #                 sync = syncManager(
    #                     host=self.host, 
    #                     port=port, 
    #                     blockchain=self, 
    #                     db_path=self.db_path,
    #                     localHostPort=self.localHostPort, 
    #                     newBlockAvailable=self.newBlockAvailable, 
    #                     MemoryPool=self.mem_pool
    #                 )
    #                 try:
    #                     if block:
    #                         sync.publishBlock(self.localHostPort-1000, port, block)
    #                     else:
    #                         sync.startDownload(self.localHostPort-1000, port)                    
    #                 except Exception as err:
    #                     print(f"Error while downloading or uploading the Blockchain \n{err}")
                    
    #     except Exception as err:
    #         print(f"Error while downloading the Blockchain \n{err}")

    def startSync(self, block=None):
        """
        Initiates synchronization or block publishing with known peers.
        If 'block' is provided, it publishes that block.
        Otherwise, it attempts to download missing blocks from peers.
        """
        try:
            action = f"Publishing block {block.BlockHeader.blockHash}" if block else "Downloading missing blocks"
            print(f"[startSync Node {self.node_id}] Starting sync action: {action}")

            node_db_instance = NodeDB(node_id=self.node_id)
            portList = node_db_instance.read_nodes()
            print(f"[startSync Node {self.node_id} DEBUG]: Port list for sync: {portList}")

            for port in portList:
                # Don't connect to self
                if port == self.localHostPort:
                    print(f"[startSync Node {self.node_id}] Skipping self ({self.host}:{port})")
                    continue

                # Determine target host - assuming localhost for now
                target_host = self.host
                target_port = port

                print(f"[startSync Node {self.node_id}] Processing peer {target_host}:{target_port}")

                # Create a syncManager instance specifically for this peer interaction
                sync = syncManager(
                    host=target_host, # Host of the PEER
                    port=target_port, # Port of the PEER
                    blockchain=self,
                    db_path=self.db_path,
                    localHostPort=self.localHostPort, # This node's listening port
                    newBlockAvailable=self.newBlockAvailable,
                    MemoryPool=self.mem_pool,
                    node_id=self.node_id,
                    my_public_addr=self.my_public_addr
                )

                try:
                    if block:
                        # Assuming publishBlock handles its own connection/sending logic
                        print(f"[startSync Node {self.node_id}] Calling publishBlock to {target_host}:{target_port}")
                        # Pass target_host and target_port to publishBlock
                        sync.publishBlock(block, target_host, target_port) # Corrected arguments for publishBlock
                    else:
                        # --- MODIFICATION ---
                        # Call startDownload with target_host and target_port
                        print(f"[startSync Node {self.node_id}] Calling startDownload from {target_host}:{target_port}")
                        sync.startDownload(target_host, target_port) # Pass the required arguments
                        # --- END MODIFICATION ---

                except ConnectionRefusedError:
                     print(f"[startSync Node {self.node_id}] Connection refused by {target_host}:{target_port}. Skipping.")
                except Exception as err:
                    print(f"[startSync Node {self.node_id}] Error during sync operation with {target_host}:{target_port}: {err}")
                    # traceback.print_exc() # Uncomment for detailed errors

        except Exception as err:
            print(f"[startSync Node {self.node_id}] Error fetching node list or during sync setup: {err}")
            # traceback.print_exc() # Uncomment for detailed errors


    # def store_uxtos_in_cache(self):
    #     for tx in self.add_trans_in_block:
    #         self.utxos[tx.TxId] = tx

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
    
    def doubleSpendingAttempt(self, tx):
        for txin in tx.tx_ins:
            if txin.prev_tx not in self.prevTxs and txin.prev_tx.hex() in self.utxos:
                self.prevTxs.append(txin.prev_tx)
            else:
                return True

    "Read transactions from mem pool"
    def read_trans_from_mempool(self):
        selected_txs_objs = []
        selected_tx_ids_bytes = []
        current_block_inputs = set() # Track inputs spent in this block: {(tx_hash, index)}
        block_size = 80
        max_block_size = 1000000 # Example max size

        # --- ADDED: Log entry point ---
        logger.debug(f"[Node {self.node_id} ReadMempool] Starting transaction selection.")

        with self.state_lock:
            # --- ADDED: Log mempool state before selection ---
            try:
                # Create a copy for safe iteration and logging
                tempMemPool = dict(self.mem_pool)
                logger.debug(f"[Node {self.node_id} ReadMempool] Mempool size before selection: {len(tempMemPool)}")
                if tempMemPool: # Log content only if not empty
                    logger.debug(f"[Node {self.node_id} ReadMempool] Mempool content keys: {list(tempMemPool.keys())}")
                # Also log UTXO set size for context
                logger.debug(f"[Node {self.node_id} ReadMempool] Current UTXO set size: {len(self.utxos)}")
            except Exception as log_e:
                logger.error(f"[Node {self.node_id} ReadMempool] Error logging initial mempool state: {log_e}")
                tempMemPool = {} # Ensure tempMemPool is defined

            # --- Iterate through a copy of the mempool ---
            for tx_id, tx_obj in tempMemPool.items():
                # --- ADDED: Log which tx is being considered ---
                logger.debug(f"[Node {self.node_id} ReadMempool] Considering Tx: {tx_id[:8]}...")

                # Ensure tx_obj is a Tx object if mempool might store dicts
                if not isinstance(tx_obj, Tx):
                     # Assuming Tx.to_obj exists and works on mempool data
                     try:
                         tx_obj = Tx.to_obj(tx_obj)
                     except Exception as e:
                         logger.warning(f"[Node {self.node_id} ReadMempool] Failed to convert mempool entry {tx_id[:8]} to Tx object: {e}. Skipping.")
                         continue

                # --- Calculate Tx Size ---
                try:
                    tx_size = len(tx_obj.serialise()) # Assuming serialise method exists
                except Exception as ser_e:
                    logger.warning(f"[Node {self.node_id} ReadMempool] Failed to serialize Tx {tx_id[:8]}: {ser_e}. Skipping.")
                    continue

                # --- Check Block Size Limit ---
                if block_size + tx_size > max_block_size:
                    # --- ADDED: Log reason for skipping ---
                    logger.debug(f"[Node {self.node_id} ReadMempool] Skipping Tx {tx_id[:8]}: Exceeds block size limit (Current: {block_size}, Tx: {tx_size}, Max: {max_block_size}).")
                    continue # Skip if block gets too large

                # --- Validate Inputs and Check Double Spending ---
                is_double_spend = False
                inputs_valid = True
                inputs_for_this_tx = [] # Store inputs to add to current_block_inputs if valid

                if not hasattr(tx_obj, 'tx_ins') or not tx_obj.tx_ins:
                     logger.warning(f"[Node {self.node_id} ReadMempool] Skipping Tx {tx_id[:8]}: Transaction has no inputs.")
                     continue

                for i, txin in enumerate(tx_obj.tx_ins):
                    # --- ADDED: Log input being checked ---
                    input_key = (txin.prev_tx.hex(), txin.prev_index)
                    logger.debug(f"[Node {self.node_id} ReadMempool]   Checking input {i}: {input_key}")

                    # Check double spend within block
                    if input_key in current_block_inputs:
                        is_double_spend = True
                        # --- ADDED: Log reason for skipping ---
                        logger.warning(f"[Node {self.node_id} ReadMempool] Skipping Tx {tx_id[:8]}: Input {input_key} double spent within this block.")
                        break # Stop checking inputs for this tx

                    # Check if input exists in current UTXO set (under lock)
                    if input_key not in self.utxos:
                        inputs_valid = False
                        # --- ADDED: Log reason for skipping ---
                        logger.warning(f"[Node {self.node_id} ReadMempool] Skipping Tx {tx_id[:8]}: Input {input_key} not found in UTXO set.")
                        break # Input not found (already spent or invalid)

                    # --- ADDED: Log input validity ---
                    logger.debug(f"[Node {self.node_id} ReadMempool]   Input {input_key} is valid and available.")
                    inputs_for_this_tx.append(input_key) # Add to temp list

                # --- Check results of validation ---
                if is_double_spend or not inputs_valid:
                    # Logs for skipping are now inside the loop
                    continue

                # --- If valid, add to block lists ---
                # --- ADDED: Log selection ---
                logger.info(f"[Node {self.node_id} ReadMempool] Selecting Tx: {tx_id[:8]}")
                selected_txs_objs.append(tx_obj)
                try:
                    selected_tx_ids_bytes.append(bytes.fromhex(tx_id))
                except ValueError:
                    logger.error(f"[Node {self.node_id} ReadMempool] Failed to convert selected TxID '{tx_id}' to bytes. Skipping.")
                    selected_txs_objs.pop() # Remove the object if ID conversion failed
                    continue

                block_size += tx_size
                # Add inputs to tracking set
                current_block_inputs.update(inputs_for_this_tx)
                logger.debug(f"[Node {self.node_id} ReadMempool]   Added inputs {inputs_for_this_tx} to block's spent set.")
                logger.debug(f"[Node {self.node_id} ReadMempool]   Block size now: {block_size}")

             # --- Lock Released ---
        # --- ADDED: Log final selection result ---
        logger.info(f"[Node {self.node_id} ReadMempool] Finished selection. Selected {len(selected_txs_objs)} transactions for block.")
        return selected_txs_objs, selected_tx_ids_bytes, block_size




        #         if not self.doubleSpendingAttempt(tempMemPool[tx]):
        #             tempMemPool[tx].TxId = tx
        #             self.TxIds.append(bytes.fromhex(tx))
        #             self.add_trans_in_block.append(tempMemPool[tx])
        #             self.Blocksize += len(tempMemPool[tx].serialise())

        #             for spent in tempMemPool[tx].tx_ins:
        #                 self.remove_spent_transactions.append([spent.prev_tx, spent.prev_index])
        #         else:
        #             deleteTxs.append(tx)
        
        # for txId in deleteTxs:
        #     del self.mem_pool[txId]

    
    # "Read transactions from mem pool"
    # def remove_trans_from_mempool(self):
    #     for tx in self.TxIds:
    #         if tx.hex() in self.mem_pool:
    #             del self.mem_pool[tx.hex()]

            
    # def convert_to_json(self):
    #     self.TxJson = []
    #     for tx in self.add_trans_in_block:
    #         self.TxJson.append(tx.to_dict())

    def calculate_fee(self,tx_objs_in_block=None):
        """Calculate the fee for a block based on its transactions"""
        if not tx_objs_in_block:
            # logger.info("[CalculateFee] No transactions selected for block. Fee is 0.")
            print("[CalculateFee DEBUG] No transactions selected, returning 0.", flush=True)
            return 0

        total_input_amount = 0
        total_output_amount = 0


        # --- Acquire Lock to read UTXOs safely ---
        with self.state_lock:
            for tx in tx_objs_in_block:
                # Calculate output amount for this tx
                for tx_out in tx.tx_outs:
                    total_output_amount += tx_out.amount
                
                for tx_in in tx.tx_ins:
                    # Skip coinbase input if accidentally included
                    if tx_in.prev_tx.hex() == ZERO_HASH or tx_in.prev_tx.hex() == '0'*64: continue

                    utxo_lookup_key = (tx_in.prev_tx.hex(), tx_in.prev_index)
                    if utxo_lookup_key in self.utxos:
                        # This depends heavily on what self.utxos stores!
                        # If it stores the TxOutput dict:
                        spent_output = self.utxos[utxo_lookup_key]
                        # Need to handle cases where UTXO key maps to multiple outputs if key is just TxId
                        amount = 0
                        if hasattr(spent_output, 'amount'): # If TxOutput object
                             amount = spent_output.amount
                        elif isinstance(spent_output, dict) and 'amount' in spent_output: # If dict
                             amount = spent_output['amount']
                        else:
                             logger.error(f"[CalculateFee] Invalid UTXO data format for key {utxo_lookup_key}. Cannot get amount.")

                        total_input_amount += amount
                    else:
                        logger.error(f"[CalculateFee] Input UTXO {utxo_lookup_key} not found! Fee calculation inaccurate.")

        # --- Lock Released ---

        fee = total_input_amount - total_output_amount
        if fee < 0:
             logger.warning(f"[CalculateFee] Calculated negative fee ({fee}). Inputs: {total_input_amount}, Outputs: {total_output_amount}. Setting fee to 0.")
             fee = 0
        # logger.info(f"[CalculateFee] Total fee for block: {fee}")
        return fee

        # for TxId_index in self.remove_spent_transactions:
        #     if TxId_index[0].hex() in self.utxos:
        #         self.input_amount += self.utxos[TxId_index[0].hex()].tx_outs[TxId_index[1]].amount
        
        # for tx in self.add_trans_in_block:
        #     for tx_out in tx.tx_outs:
        #         self.output_amount += tx_out.amount
        
        # self.fee = self.input_amount - self.output_amount

    def buildUTXOS(self):
        """Build UTXO set by parsing the blockchain"""
        # logger.info(f"[Node {self.node_id}] Building UTXO set from scratch...")
        with self.state_lock:
            self.utxos.clear() # Clear existing UTXOs
            all_tx_outputs = {} # Store all outputs: {(tx_hash, index): output_dict}
            spent_outputs = set() # Store spent outputs: {(tx_hash, index)}

            try:
                blocks_data = self.db.read_all_blocks() # Read all blocks (list of dicts)
                # logger.info(f"[BuildUTXO] Read {len(blocks_data)} blocks from DB.")

                for block_dict in blocks_data:
                    # Ensure block_dict is a dictionary
                    if isinstance(block_dict, list) and len(block_dict) == 1:
                         block_dict = block_dict[0]
                    if not isinstance(block_dict, dict):
                         logger.warning(f"[BuildUTXO] Skipping non-dict block data: {type(block_dict)}")
                         continue
                    
                    # block_height = block_dict.get('Height', -1)
                    for tx_dict in block_dict.get('Txs', []):
                        tx_id = tx_dict.get('TxId')
                        if not tx_id: continue

                        # Track spent outputs
                        for tx_in in tx_dict.get('tx_ins', []):
                            prev_tx_hash = tx_in.get('prev_tx')
                            prev_index = tx_in.get('prev_index')
                            if prev_tx_hash != ZERO_HASH and prev_tx_hash != '0'*64:
                                spent_outputs.add((prev_tx_hash, prev_index))

                        # Store all outputs from this transaction
                        for i, tx_out_dict in enumerate(tx_dict.get('tx_outs', [])):
                            try:
                                # Use TxOut.from_dict to create the object
                                tx_out_obj = TxOut.from_dict(tx_out_dict)
                                # Store the TxOut OBJECT in all_tx_outputs
                                all_tx_outputs[(tx_id, i)] = tx_out_obj
                            except Exception as e:
                                logger.error(f"[BuildUTXO] Failed to create TxOut object from dict for {tx_id}:{i}: {e}")
                                continue # Skip this output if conversion fails
    

                # Populate UTXO set with unspent outputs
                for utxo_key, output_obj in all_tx_outputs.items():
                    if utxo_key not in spent_outputs:
                        self.utxos[utxo_key] = output_obj # Store TxOutput dict/obj

                # logger.info(f"[Node {self.node_id}] UTXO set built with {len(self.utxos)} entries.") # Count might be misleading if key is just TxId

            except Exception as e:
                logger.error(f"[Node {self.node_id}] Error building UTXO set: {e}", exc_info=True)
        # --- Lock Released ---

    def settargetWhileBooting(self):
        bits, timestamp = self.getTargetDifficultyAndTimestamp()
        self.bits = bytes.fromhex(bits)
        self.current_target = bits_to_targets(self.bits)
        
    # def getTargetDifficultyAndTimestamp(self, BlockHeight = None):
    #     try:
    #         if BlockHeight:
    #             blocks = BlockchainDB().read()
    #             bits = blocks[BlockHeight][0]['BlockHeader']['bits']
    #             timestamp = blocks[BlockHeight][0]['BlockHeader']['timestamp']
    #         else:
    #             block = BlockchainDB().lastBlock()
    #             bits = block[0]['BlockHeader']['bits']
    #             timestamp = block[0]['BlockHeader']['timestamp']
    #         return (bits,timestamp)
    #     except Exception as err:
    #         print(f"Error while fetching the target difficulty and timestamp \n{err}")
    #         return ('ffff001f',1737222175)

    def getTargetDifficultyAndTimestamp(self, BlockHeight = None):
        """ Fetch the target difficulty and timestamp of the last block """
        try:
            if BlockHeight is not None: # Explicit check for BlockHeight presence
                # This part might still be problematic if BlockHeight doesn't exist
                # Consider adding error handling here too
                blocks = self.db.read_all_blocks() # Use self.db instance
                if BlockHeight < len(blocks):
                    block_data = blocks[BlockHeight]
                    # Handle potential list wrapping
                    if isinstance(block_data, list) and len(block_data) > 0:
                        block_data = block_data[0]

                    if isinstance(block_data, dict) and 'BlockHeader' in block_data:
                        bits_hex = block_data['BlockHeader'].get('bits')
                        timestamp = block_data['BlockHeader'].get('timestamp')
                        if bits_hex is not None and timestamp is not None:
                            #  logger.info(f"[getTargetDifficultyAndTimestamp] Fetched specific block {BlockHeight}. Bits: {bits_hex}, Timestamp: {timestamp}")
                             return (bits_hex, timestamp)
                        else:
                             logger.error(f"Block {BlockHeight} header missing bits or timestamp.")
                    else:
                         logger.error(f"Invalid block data format for height {BlockHeight}.")

                else:
                     logger.error(f"Requested BlockHeight {BlockHeight} out of range (Chain length: {len(blocks)}).")
                # Fall through to default if specific block fetch failed

            else: # Fetch the last block
                lastBlock = self.fetch_last_block() # Use the instance method

                if lastBlock is None:
                    # Handle genesis block case: No previous block exists
                    logger.warning("[getTargetDifficultyAndTimestamp] No last block found (genesis?), using initial target and timestamp 0.")
                    # Use the initial target defined in the class/constants
                    initial_bits = target_to_bits(INITIAL_TARGET)
                    bits_hex = initial_bits.hex() # Convert initial bits to hex string
                    timestamp = 0 # Default timestamp for genesis calculation
                    return (bits_hex, timestamp)
                else:
                    # Existing logic for when a last block is found
                    # Ensure lastBlock is the dictionary, not the list containing it
                    if isinstance(lastBlock, list) and len(lastBlock) > 0:
                        block_data = lastBlock[0]
                    elif isinstance(lastBlock, dict):
                        block_data = lastBlock
                    else:
                        logger.error(f"Unexpected lastBlock format: {type(lastBlock)}")
                        # Fall through to default return

                    if isinstance(block_data, dict) and 'BlockHeader' in block_data:
                        bits_hex = block_data['BlockHeader'].get('bits')
                        timestamp = block_data['BlockHeader'].get('timestamp')

                        if bits_hex is not None and timestamp is not None:
                            # logger.info(f"[getTargetDifficultyAndTimestamp] Fetched last block. Bits: {bits_hex}, Timestamp: {timestamp}")
                            return (bits_hex, timestamp)
                        else:
                            logger.error("Last block header missing bits or timestamp.")
                    else:
                         logger.error("Invalid last block data format.")
                    # Fall through to default if extraction failed

            # Default return if specific block fetch or last block extraction failed
            logger.error("[getTargetDifficultyAndTimestamp] Failed to get valid bits/timestamp, returning default.")
            default_bits_hex = target_to_bits(INITIAL_TARGET).hex()
            default_timestamp = int(time.time()) # Or a fixed genesis timestamp
            return (default_bits_hex, default_timestamp) # Return default values

        except Exception as e:
            # Log the specific error that occurred
            logger.error(f"Error in getTargetDifficultyAndTimestamp: {e}", exc_info=True)
            # Return default values as a fallback
            default_bits_hex = target_to_bits(INITIAL_TARGET).hex()
            default_timestamp = int(time.time()) # Or a fixed genesis timestamp
            return (default_bits_hex, default_timestamp)



    def adjustTarget(self, BlockHeight):
        if BlockHeight % 10 == 0:
            bits, timestamp = self.getTargetDifficultyAndTimestamp(BlockHeight - 10)
            Lastbits, lastTimestamp = self.getTargetDifficultyAndTimestamp()

            lastTarget = bits_to_targets(bytes.fromhex(bits))
            AverageBlockMineTime = lastTimestamp - timestamp
            timeRatio =  AverageBlockMineTime / AVERAGE_MINE_TIME

            NEW_TARGET = int(format(int(lastTarget * timeRatio)))

            if NEW_TARGET > MAX_TARGET:
                NEW_TARGET = MAX_TARGET
            
            self.bits = target_to_bits(NEW_TARGET)
            self.current_target = NEW_TARGET


    def BroadcastBlock(self, block):
        """Broadcasts the block to other nodes in the network."""
        print(f"[BroadcastBlock] Broadcasting block {block.BlockHeader.blockHash} to network.")
        self.startSync(block)

    # def LostCompetition(self):
    #     print(f"[LostCompetition] newBlockAvailable: {self.newBlockAvailable!r}")
    #     # ── ADD DEBUG LINES HERE ────────────────────────────────────────────────
    #     print(f"[LostCompetition DEBUG] keys in newBlockAvailable: {list(self.newBlockAvailable.keys())}")
    #     # pull the on‑disk chain so we can inspect its size
    #     chain = BlockchainDB(node_id=getattr(self, 'node_id', None)).read_all_blocks()
    #     print(f"[LostCompetition DEBUG] on-disk chain length: {len(chain)}")
    #     # ── end DEBUG ───────────────────────────────────────────────────────────
    #     deleteBlock = []
    #     tempBlocks = dict(self.newBlockAvailable)

    #     for newblock in tempBlocks:
    #         block = tempBlocks[newblock]
    #         deleteBlock.append(newblock)

    #         BlockHeaderObj = BlockHeader(block.BlockHeader.version,
    #                     block.BlockHeader.prevBlockHash,
    #                     block.BlockHeader.merkleRoot,
    #                     block.BlockHeader.timestamp,
    #                     block.BlockHeader.bits,
    #                     block.BlockHeader.nonce)
            
    #         if BlockHeaderObj.validateBlock():
    #             #print("DEBUG: Number of Txs in block:", len(block.Txs))
    #             for idx,tx in enumerate(block.Txs):
    #                 self.utxos[tx.id()] = tx.serialise()
    #                 block.Txs[idx].TxId = tx.id()
                    
    #                 """ Remove spent transactions """
    #                 for txin in tx.tx_ins:
    #                     if txin.prev_tx.hex() in self.utxos:
    #                         del self.utxos[txin.prev_tx.hex()]
                    
    #                 if tx.id() in self.mem_pool:
    #                     del self.mem_pool[tx.id()]

    #                 block.Txs[idx] = tx.to_dict()
            
    #             block.BlockHeader.to_hex()
    #             BlockchainDB().write([block.to_dict()])
    #         else:
    #             orphanTxs = {}
    #             validTxs = {}

    #             if self.secondaryChain:
    #                 addBlocks = []
    #                 addBlocks.append(block)
    #                 prevBlockhash = block.BlockHeader.prevBlockHash.hex()
    #                 count = 0

    #                 while count != len(self.secondaryChain):
    #                     if prevBlockhash in self.secondaryChain:
    #                         addBlocks.append(self.secondaryChain[prevBlockhash])
    #                         prevBlockhash = self.secondaryChain[prevBlockhash].BlockHeader.prevBlockHash.hex()
    #                     count += 1
                    
    #                 blockchain =  BlockchainDB().read()
    #                 lastValidBlock = blockchain[-len(addBlocks)][0]

    #                 if lastValidBlock['BlockHeader']['blockHash'] == prevBlockhash:
    #                     for i in range(len(addBlocks)-1):
    #                         orphanBlock = blockchain.pop()

    #                         for tx in orphanBlock[0]['Txs']:
    #                             if tx['TxId'] in self.utxos:
    #                                 del self.utxos[tx['TxId']]

    #                                 if tx['tx_ins'][0]['prev_tx'] != "0000000000000000000000000000000000000000000000000000000000000000":
    #                                     orphanTxs[tx['TxId']] = tx
                        
    #                     print(f"[LostCompetition] about to call update(...) with: {repr(blockchain)[:200]}")
    #                     BlockchainDB().update(blockchain)

    #                     for BObj in addBlocks[::-1]:
    #                         validBlock = copy.deepcopy(BObj)
    #                         validBlock.BlockHeader.to_hex()

    #                         for index,tx in enumerate(validBlock.Txs):
    #                             validBlock.Txs[index].TxId = tx.id()
    #                             # self.utxos[tx.id()] = tx
    #                             self.utxos[tx.id()] = tx.serialise()
                            
    #                         """ Remove spent transactions """
    #                         for txin in tx.tx_ins:
    #                             if txin.prev_tx.hex() in self.utxos:
    #                                 del self.utxos[txin.prev_tx.hex()]
                                
    #                             if tx.tx_ins[0].prev_tx.hex() != "0000000000000000000000000000000000000000000000000000000000000000":
    #                                     # validTxs[tx['TxId']] = tx
    #                                     validTxs[tx.id()] = tx.to_dict()

    #                             validBlock.Txs[index] = tx.to_dict()

    #                     BlockchainDB().write([validBlock.to_dict()])
                        
    #                     for TxId in orphanTxs:
    #                         if TxId not in validTxs:
    #                             self.mem_pool[TxId] = Tx.to_obj(orphanTxs[TxId])

    #             self.secondaryChain[newblock] = block
            
    #     for blockHash in deleteBlock:
    #         del self.newBlockAvailable[blockHash]

    def LostCompetition(self):
        """Handles newly received blocks from the network using ReorgManager."""
        # logger.info(f"[Node {self.node_id} LostCompetition] Checking newBlockAvailable...")
        """Handles newly received blocks from the network using ReorgManager."""
        # --- ADD DEBUG LOGGING ---
        print(f"[Node {self.node_id} LostCompetition DEBUG] Entered. newBlockAvailable: {dict(self.newBlockAvailable)}")
        # logger.info(f"[Node {self.node_id} LostCompetition DEBUG] Entered. newBlockAvailable: {dict(self.newBlockAvailable)}")
        # --- END DEBUG LOGGING ---

        # logger.info(f"[Node {self.node_id} LostCompetition] Checking newBlockAvailable...")
        hashes_to_process = list(self.newBlockAvailable.keys())
        processed_in_this_run = set() # Track hashes processed in this call

        for newblock_hash in hashes_to_process:
            # --- Acquire Lock for each block processing ---
            # This ensures atomicity for each block's handling
            with self.state_lock:
                # Re-check if block still exists and wasn't processed yet
                if newblock_hash not in self.newBlockAvailable or newblock_hash in processed_in_this_run:
                    continue

                block = self.newBlockAvailable[newblock_hash] # Get the Block object

                # Basic validation of the received block object
                if not isinstance(block, Block) or not isinstance(block.BlockHeader, BlockHeader):
                    logger.error(f"[Node {self.node_id} LostCompetition] ERROR: Invalid block structure received for hash {newblock_hash}. Discarding.")
                    del self.newBlockAvailable[newblock_hash] # Remove invalid block
                    processed_in_this_run.add(newblock_hash)
                    continue

                logger.info(f"[Node {self.node_id} LostCompetition] Processing block {block.Height} ({newblock_hash[:8]}...) under lock.")
                BlockHeaderObj = block.BlockHeader # Use the existing header object

                BlockHeaderObj.blockHash = BlockHeaderObj.generateBlockHash()

                # Validate PoW and block structure (e.g., Merkle root if needed)
                # --- MERKLE ROOT VALIDATION ---
                try:
                    # Ensure Txs are Tx objects if needed (might already be)
                    tx_objs = []
                    for tx_data in block.Txs:
                        if isinstance(tx_data, Tx):
                            tx_objs.append(tx_data)
                        elif isinstance(tx_data, dict):
                             try:
                                 tx_objs.append(Tx.from_dict(tx_data)) # Assuming Tx.from_dict exists
                             except Exception as tx_e:
                                 logger.error(f"Failed to convert tx dict to obj in Merkle validation: {tx_e}")
                                 raise ValueError("Invalid transaction data in block") # Raise to trigger outer catch
                        else:
                             raise ValueError("Unknown transaction data type in block")

                    tx_ids_bytes = [bytes.fromhex(tx.id()) for tx in tx_objs]

                    # --- FIX: Calculate Merkle root as BYTES ---
                    # Remove the [::-1].hex() part
                    calculated_merkle_root_bytes = merkle_root(tx_ids_bytes)[::-1] # Assuming merkle_root returns bytes

                    # --- FIX: Get header Merkle root as BYTES ---
                    # Assuming BlockHeaderObj.merkleRoot is stored as a HEX STRING
                    header_merkle_root_bytes = BlockHeaderObj.merkleRoot

                    # --- FIX: Compare BYTES to BYTES ---
                    if calculated_merkle_root_bytes != header_merkle_root_bytes:
                         logger.warning(f"[Node {self.node_id} LostCompetition] Block {block.Height} ({newblock_hash[:8]}) failed Merkle root validation.")
                         # Log both in hex for easier comparison in logs
                         logger.warning(f"  Header MR (bytes): {header_merkle_root_bytes.hex()}")
                         logger.warning(f"  Calc. MR (bytes): {calculated_merkle_root_bytes.hex()}")
                         del self.newBlockAvailable[newblock_hash]
                         processed_in_this_run.add(newblock_hash)
                         continue # Skip to next block
                    else:
                         # Optional: Log success if needed for debugging
                         logger.debug(f"[Node {self.node_id} LostCompetition] Block {block.Height} Merkle root VALID.")

                except Exception as e:
                     logger.error(f"[Node {self.node_id} LostCompetition] Error during Merkle root validation for block {block.Height}: {e}. Discarding.", exc_info=True)
                     del self.newBlockAvailable[newblock_hash]
                     processed_in_this_run.add(newblock_hash)
                     continue
                # --- END MERKLE ROOT VALIDATION ---
                if BlockHeaderObj.check_pow(): # Assuming validateBlock checks PoW
                    current_height = self.reorg_manager._get_current_height_unsafe()
                    tip_hash = self.reorg_manager._get_tip_hash_unsafe()

                    # --- Use deepcopy before to_dict if storing original block ---
                    block_copy_for_dict = copy.deepcopy(block)
                    block_dict = block_copy_for_dict.to_dict() # Convert copy to dict

                    # Case 1: Block is the next sequential block
                    if block.Height == current_height + 1 and BlockHeaderObj.prevBlockHash.hex() == tip_hash:
                        logger.info(f"[Node {self.node_id} LostCompetition] Appending valid next block {block.Height} ({newblock_hash[:8]}...)")
                        # --- Delegate state update and DB write to ReorgManager ---
                        # (apply_state_for_block handles UTXO/mempool, then we write DB)
                        if self.reorg_manager.apply_state_for_block(block_dict): # Pass dict
                            try:
                                self.write_on_disk(block_dict) # Write the block dict to DB
                                # logger.info(f"[Node {self.node_id} LostCompetition] Block {block.Height} appended successfully.")
                                # Block added, remove from processing queue
                                del self.newBlockAvailable[newblock_hash]
                                processed_in_this_run.add(newblock_hash)
                                # Check if any forks are now better (unlikely, but for consistency)
                                self.reorg_manager.check_for_reorg(block.Height) # Pass new height
                            except Exception as e:
                                logger.error(f"[Node {self.node_id} LostCompetition] ERROR writing block {block.Height} to DB after state apply: {e}. State inconsistent!", exc_info=True)
                                # CRITICAL: State applied but DB write failed.
                                # Attempt rewind:
                                self.reorg_manager.rewind_state_for_block(block_dict)
                        else:
                            logger.error(f"[Node {self.node_id} LostCompetition] ERROR applying state for next block {block.Height}. Keeping in newBlockAvailable.")
                            # Don't remove from newBlockAvailable if state apply failed

                    # Case 2: Block is valid but creates/extends a fork
                    # Check height and if prev block is known (in DB or secondaryChain)
                    elif block.Height > current_height - 50: # Allow slightly older forks, adjust window as needed
                         # Check if previous block exists in DB or memory
                         prev_block_exists = self.db.read_block_by_hash(block.BlockHeader.prevBlockHash.hex()) or \
                                             block.BlockHeader.prevBlockHash.hex() in self.secondaryChain

                         if prev_block_exists:
                             logger.info(f"[Node {self.node_id} LostCompetition] Storing valid fork block {block.Height} ({newblock_hash[:8]}...)")
                             # --- Store the ORIGINAL block object in secondaryChain ---
                             self.secondaryChain[newblock_hash] = block # Store the Block object
                             del self.newBlockAvailable[newblock_hash] # Remove from processing queue
                             processed_in_this_run.add(newblock_hash)
                             # --- Trigger reorg check ---
                             self.reorg_manager.check_for_reorg(current_height) # Check based on current main height
                         else:
                             # Orphan block - prev hash unknown
                             logger.warning(f"[Node {self.node_id} LostCompetition] Block {block.Height} ({newblock_hash[:8]}) is orphan (prev hash unknown). Storing/Ignoring.")
                             # Optionally store orphans temporarily elsewhere if needed for later connection
                             # For now, just remove it from processing queue
                             del self.newBlockAvailable[newblock_hash]
                             processed_in_this_run.add(newblock_hash)

                    # Case 3: Block is valid but too old or irrelevant
                    else:
                        #  logger.info(f"[Node {self.node_id} LostCompetition] Ignoring valid but old/irrelevant block {block.Height} ({newblock_hash[:8]}...)")
                         del self.newBlockAvailable[newblock_hash] # Remove from processing queue
                         processed_in_this_run.add(newblock_hash)

                # Case 4: Block has invalid PoW or structure
                else:
                    logger.warning(f"[Node {self.node_id} LostCompetition] Block {block.Height} ({newblock_hash[:8]}...) failed validation. Discarding.")
                    del self.newBlockAvailable[newblock_hash] # Remove invalid block
                    processed_in_this_run.add(newblock_hash)

            # --- Lock Released for this block ---

        logger.info(f"[Node {self.node_id} LostCompetition] Finished checking newBlockAvailable.")


    def addBlock(self, BlockHeight, prevBlockHash):
        """Mines and adds a new block to the chain."""
        print(f"[Node {self.node_id} AddBlock] Starting to build block {BlockHeight}...")
        # --- Select Transactions (Needs lock if accessing shared mempool/utxos directly) ---
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Reading mempool...", flush=True)
        selected_txs, selected_tx_ids, block_size_so_far = self.read_trans_from_mempool()
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Mempool read. Selected {len(selected_txs)} txs. Size so far: {block_size_so_far}", flush=True)
        # fee = self.calculate_fee(selected_txs)

        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Calculating fee...", flush=True)
        fee = self.calculate_fee(selected_txs) # Pass selected_txs
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Calculated fee: {fee}", flush=True)
        
        timestamp = int(time.time())
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Creating coinbase tx...", flush=True)
        coinbase_instance = Coinbase_tx(BlockHeight,self.my_public_addr)
        coinbaseTx = coinbase_instance.coinbase_transaction()
        # --- ADD LOGGING HERE ---
        if coinbaseTx:
            # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Coinbase Tx created successfully. ID: {coinbaseTx.id()}")
            # Now try adding it to the list
            try:
                final_tx_objs = [coinbaseTx] # Start list with coinbase
                # ... (add mempool txs to final_tx_objs if any) ...
                # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Coinbase added to tx list. List size: {len(final_tx_objs)}")
                # ... (continue with block creation, size calculation etc.) ...
            except Exception as e_list:
                print(f"ERROR [Node {self.node_id} AddBlock {BlockHeight}] Failed handling created coinbaseTx: {e_list}")
                traceback.print_exc()
                # Potentially return or raise here
        else:
            print(f"ERROR [Node {self.node_id} AddBlock {BlockHeight}] Coinbase transaction creation failed!")
            # Handle failure - maybe return?
            return # Stop block creation if coinbase failed
        # --- END ADDED LOGGING ---
        coinbase_size = len(coinbaseTx.serialise())
        block_size_so_far += len(coinbaseTx.serialise())
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Coinbase created. Size: {coinbase_size}. Total size: {block_size_so_far}", flush=True)

        coinbaseTx.tx_outs[0].amount = coinbaseTx.tx_outs[0].amount + fee
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Coinbase amount updated with fee.", flush=True)

        # Combine transactions
        final_tx_objs = [coinbaseTx] + selected_txs
        final_tx_ids_bytes = [bytes.fromhex(coinbaseTx.id())] + selected_tx_ids
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Combined {len(final_tx_objs)} transactions.", flush=True)

        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Calculating Merkle root...", flush=True)
        merkleRoot = merkle_root(final_tx_ids_bytes)[::-1].hex()
        # --- Adjust Target (Needs lock if modifying self.bits/self.current_target shared state) ---
        # Assuming adjustTarget handles its own locking or is safe
        
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Adjusting target...", flush=True)
        self.adjustTarget(BlockHeight)
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Target adjusted. New bits: {self.bits.hex()}", flush=True)

        # --- Create BlockHeader ---
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Creating block header...", flush=True)
        blockheader = BlockHeader(VERSION, bytes.fromhex(prevBlockHash), merkleRoot, timestamp, self.bits, nonce = 0) # Ensure prevBlockHash is bytes
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Block header created.", flush=True)

        # logger.info(f"[Node {self.node_id} AddBlock] Mining block {BlockHeight} with target {self.current_target:064x}...")
        print(f"[Node {self.node_id} AddBlock {BlockHeight}] Calling blockheader.mine()...", flush=True)
        
        # --- Mine the block ---
        # Pass the lock to mine if it needs to check newBlockAvailable safely
        competitionOver = blockheader.mine(self.current_target, self.newBlockAvailable)
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] blockheader.mine() returned. competitionOver = {competitionOver}", flush=True)
        
        if competitionOver:
            self.LostCompetition()
            # logger.info(f"[Node {self.node_id} AddBlock] Lost competition while mining block {BlockHeight}.")
            print(f"[Node {self.node_id} AddBlock {BlockHeight}] Competition lost. Returning.", flush=True)
            # LostCompetition will be called by the mining loop or network listener
            # No need to call it explicitly here if mine() handles the trigger
            return # Stop processing this block
        
        # --- If we won (found nonce) ---
        # logger.info(f"[Node {self.node_id} AddBlock] Mined block {BlockHeight} successfully with nonce {blockheader.nonce}.")
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Mining successful. Nonce: {blockheader.nonce}", flush=True)

        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Acquiring state lock to add block...", flush=True)
        # --- Acquire Lock to add the block ---
        with self.state_lock:
            # print(f"[Node {self.node_id} AddBlock {BlockHeight}] State lock acquired.", flush=True)
            # Double-check we didn't lose competition *just* before acquiring lock
            # This requires mine() to signal reliably or checking newBlockAvailable again
            # For simplicity, assume mine() handles this or check tip again:
            # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Double-checking chain tip...", flush=True)
            current_height = self.reorg_manager._get_current_height_unsafe()
            tip_hash = self.reorg_manager._get_tip_hash_unsafe()
            print(f"[Node {self.node_id} AddBlock {BlockHeight}] Current tip: Height={current_height}, Hash={tip_hash[:8]}...", flush=True)
            if BlockHeight != current_height + 1 or prevBlockHash != tip_hash:
                 logger.warning(f"[Node {self.node_id} AddBlock] Chain tip changed before block {BlockHeight} could be added. Discarding.")
                 return # Chain changed, discard mined block
                        
            # --- Create Block object ---
            # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Creating Block object...", flush=True)
            newBlock = Block(BlockHeight, block_size_so_far, blockheader, len(final_tx_objs), final_tx_objs)
            # --- Use deepcopy before to_dict for applying/writing ---
            # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Creating block dict...", flush=True)
            try:
                # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Creating block dict...", flush=True)
                newBlock_copy_for_dict = copy.deepcopy(newBlock)
                # This call should ideally convert Txs to dicts and header fields appropriately.
                # We will manually ensure consistency below based on syncManager's logic.
                newBlockDict = newBlock_copy_for_dict.to_dict()
                # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Block dict created.", flush=True)

                # --- START: Manual Consistency Adjustment (Mirror syncManager) ---
                # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Adjusting block dict for DB consistency...", flush=True)

                # 1. Ensure Txs are dictionaries
                # Check if Block.to_dict already converted Txs. If not, convert them.
                if newBlockDict.get('Txs') and isinstance(newBlockDict['Txs'][0], Tx):
                    # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Converting Tx objects in dict to dicts...", flush=True)
                    newBlockDict['Txs'] = [tx.to_dict() for tx in newBlockDict['Txs']]

                # 2. Ensure BlockHeader fields are in the correct format (hex/int)
                header_dict = newBlockDict.get('BlockHeader')
                if header_dict:
                    # Convert bytes to hex if needed (assuming to_dict might leave them as bytes)
                    if isinstance(header_dict.get('prevBlockHash'), bytes):
                        header_dict['prevBlockHash'] = header_dict['prevBlockHash'].hex()
                        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Converted prevBlockHash to hex.", flush=True)
                    # Merkle root should already be hex from creation, but check just in case
                    if isinstance(header_dict.get('merkleRoot'), bytes):
                            header_dict['merkleRoot'] = header_dict['merkleRoot'].hex()
                            # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Converted merkleRoot to hex.", flush=True)
                    if isinstance(header_dict.get('bits'), bytes):
                        header_dict['bits'] = header_dict['bits'].hex()
                        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Converted bits to hex.", flush=True)

                    # Ensure nonce is an integer (it should be after mining, but check)
                    if isinstance(header_dict.get('nonce'), bytes):
                        header_dict['nonce'] = little_endian_to_int(header_dict['nonce'])
                        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Converted nonce bytes to int.", flush=True)
                    elif not isinstance(header_dict.get('nonce'), int):
                            # If it's neither bytes nor int, try converting (e.g., from string if somehow corrupted)
                            try:
                                header_dict['nonce'] = int(header_dict.get('nonce', 0))
                                # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Converted nonce to int from other type.", flush=True)
                            except (ValueError, TypeError):
                                logger.error(f"[Node {self.node_id} AddBlock {BlockHeight}] Could not convert nonce '{header_dict.get('nonce')}' to int. Setting to 0.")
                                header_dict['nonce'] = 0 # Fallback

                    # blockHash should already be hex after mining/generateBlockHash
                    if isinstance(header_dict.get('blockHash'), bytes):
                            header_dict['blockHash'] = header_dict['blockHash'].hex()
                            # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Converted blockHash to hex.", flush=True)

                print(f"[Node {self.node_id} AddBlock {BlockHeight}] Block dict adjustment complete.", flush=True)
                # --- END: Manual Consistency Adjustment ---

            except Exception as e:
                print(f"[Node {self.node_id} AddBlock {BlockHeight}] FAILED during deepcopy, to_dict, or consistency adjustment!")
                print(f"[Node {self.node_id} AddBlock {BlockHeight}] Exception type: {type(e).__name__}, Message: {e}")
                print(traceback.format_exc()) # Log the full traceback
                # If conversion fails, we shouldn't proceed
                return

            # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Block dict created.", flush=True) # Redundant log line

            # logger.info(f"[Node {self.node_id} AddBlock] Applying state and writing block {BlockHeight}...")
            # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Calling apply_state_for_block...", flush=True)
            # Pass the *adjusted* newBlockDict to apply_state and write
            if self.reorg_manager.apply_state_for_block(newBlockDict):
                # print(f"[Node {self.node_id} AddBlock {BlockHeight}] apply_state_for_block successful.", flush=True)
                try:
                    # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Writing block to DB...", flush=True)
                    # --- Write the *adjusted* block dict to DB ---
                    self.write_on_disk(newBlockDict) # Use the adjusted dict
                    # logger.info(f"[Node {self.node_id} AddBlock] Block {BlockHeight} added successfully.")
                    print(f"[Node {self.node_id} AddBlock {BlockHeight}] DB write successful.", flush=True)

                    # Broadcast the new block AFTER adding it locally
                    # --- Broadcast the ORIGINAL block object ---
                    # print(f"[Node {self.node_id} AddBlock {BlockHeight}] Broadcasting block...", flush=True)
                    self.BroadcastBlock(newBlock) # Pass the original Block object for network serialization
                    print(f"[Node {self.node_id} AddBlock {BlockHeight}] Broadcast initiated.", flush=True)
                    # Check for reorgs (unlikely right after adding own block, but for consistency)
                    self.reorg_manager.check_for_reorg(BlockHeight)
                except Exception as e:
                    logger.error(f"[Node {self.node_id} AddBlock] ERROR writing block {BlockHeight} to DB after state apply: {e}. State inconsistent!", exc_info=True)
                    print(f"[Node {self.node_id} AddBlock {BlockHeight}] ERROR writing to DB: {e}", flush=True)
                    # CRITICAL: State applied but DB write failed. Need robust recovery/rollback.
                    # For now, log error. A simple rollback might involve rewinding the state:
                    self.reorg_manager.rewind_state_for_block(newBlockDict) # Attempt rewind
            else:
                logger.error(f"[Node {self.node_id} AddBlock] ERROR applying state for mined block {BlockHeight}. Discarding.")
                print(f"[Node {self.node_id} AddBlock {BlockHeight}] ERROR applying state. Discarding block.", flush=True)
        # --- Lock Released ---
        print(f"[Node {self.node_id} AddBlock {BlockHeight}] State lock released.", flush=True)
        print(f"[Node {self.node_id} AddBlock {BlockHeight}] END", flush=True)

        #     print(f"[Node {self.node_id} AddBlock {BlockHeight}] Creating Block object...", flush=True)
        #     newBlock = Block(BlockHeight, block_size_so_far, blockheader, len(final_tx_objs), final_tx_objs)
        #     # --- Use deepcopy before to_dict for applying/writing ---
        #     print(f"[Node {self.node_id} AddBlock {BlockHeight}] Creating block dict...", flush=True)
        #     try:
        #         print(f"[Node {self.node_id} AddBlock {BlockHeight}] Creating block dict...", flush=True)
        #         newBlock_copy_for_dict = copy.deepcopy(newBlock)
        #         newBlockDict = newBlock_copy_for_dict.to_dict()
        #         print(f"[Node {self.node_id} AddBlock {BlockHeight}] Block dict created.", flush=True)
        #     except Exception as e:
        #         print(f"[Node {self.node_id} AddBlock {BlockHeight}] FAILED during deepcopy or to_dict!")
        #         print(f"[Node {self.node_id} AddBlock {BlockHeight}] Exception type: {type(e).__name__}, Message: {e}")
        #         print(traceback.format_exc()) # Log the full traceback

        #     print(f"[Node {self.node_id} AddBlock {BlockHeight}] Block dict created.", flush=True)

            # logger.info(f"[Node {self.node_id} AddBlock] Applying state and writing block {BlockHeight}...")
        #     print(f"[Node {self.node_id} AddBlock {BlockHeight}] Calling apply_state_for_block...", flush=True)
        #     if self.reorg_manager.apply_state_for_block(newBlockDict):
        #         print(f"[Node {self.node_id} AddBlock {BlockHeight}] apply_state_for_block successful.", flush=True)
        #         try: 
        #             print(f"[Node {self.node_id} AddBlock {BlockHeight}] Writing block to DB...", flush=True)
        #             # --- Write block dict to DB ---
        #             self.db.write(newBlockDict)
                    # logger.info(f"[Node {self.node_id} AddBlock] Block {BlockHeight} added successfully.")
        #             print(f"[Node {self.node_id} AddBlock {BlockHeight}] DB write successful.", flush=True)

        #             # Broadcast the new block AFTER adding it locally
        #             # --- Broadcast the ORIGINAL block object ---
        #             print(f"[Node {self.node_id} AddBlock {BlockHeight}] Broadcasting block...", flush=True)
        #             self.BroadcastBlock(newBlock) # Pass the Block object
        #             print(f"[Node {self.node_id} AddBlock {BlockHeight}] Broadcast initiated.", flush=True)
        #             # Check for reorgs (unlikely right after adding own block, but for consistency)
        #             # self.reorg_manager.check_for_reorg(BlockHeight)
        #         except Exception as e:
        #             logger.error(f"[Node {self.node_id} AddBlock] ERROR writing block {BlockHeight} to DB after state apply: {e}. State inconsistent!", exc_info=True)
        #             print(f"[Node {self.node_id} AddBlock {BlockHeight}] ERROR writing to DB: {e}", flush=True)
        #             # CRITICAL: State applied but DB write failed. Need robust recovery/rollback.
        #             # For now, log error. A simple rollback might involve rewinding the state:
        #             # self.reorg_manager.rewind_state_for_block(newBlockDict) # Attempt rewind
        #     else:
        #         logger.error(f"[Node {self.node_id} AddBlock] ERROR applying state for mined block {BlockHeight}. Discarding.")
        #         print(f"[Node {self.node_id} AddBlock {BlockHeight}] ERROR applying state. Discarding block.", flush=True)
        # # --- Lock Released ---
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] State lock released.", flush=True)
        # print(f"[Node {self.node_id} AddBlock {BlockHeight}] END", flush=True)
            

        # else
        #     newBlock =  Block(BlockHeight, self.Blocksize, blockheader, len(self.add_trans_in_block),
        #                     self.add_trans_in_block)
        #     blockheader.to_bytes()
        #     self.BroadcastBlock(newBlock)
        #     blockheader.to_hex()
        #     self.remove_spent_Transactions()
        #     self.remove_trans_from_mempool()
        #     self.store_uxtos_in_cache()
        #     self.convert_to_json()

        #     print(f"Block {BlockHeight} was mined successfully with a nonce value of {blockheader.nonce}")
        #     self.write_on_disk([Block(BlockHeight, self.Blocksize, blockheader.__dict__, len(self.TxJson), self.TxJson).__dict__])
            

    def main(self):
        """Main blockchain process"""
        print(f"Mining process for node {getattr(self, 'node_id', 'unknown')} starting")
        # logger.info(f"Mining process for node {self.node_id} starting")
        # print(f"Building UTXO set within mining process for node {getattr(self, 'node_id', 'unknown')}")

        try:
            self.buildUTXOS()
            print("UTXO set built successfully")
        except Exception as e:
            print(f"Error building UTXO set: {e}")
            traceback.print_exc()

         # --- Add check for genesis block visibility ---
        initial_check_attempts = 0
        while initial_check_attempts < 5: # Try a few times
            last_block_initial = self.fetch_last_block()
            if last_block_initial is not None:
                # logger.info("Initial check found last block, proceeding.")
                break
            else:
                logger.warning(f"Initial check: Last block not found (attempt {initial_check_attempts + 1}). Waiting briefly...")
                time.sleep(0.5) # Wait 500ms
                initial_check_attempts += 1
        else: # If loop finishes without break
            logger.error("Initial check failed: Could not find last block after multiple attempts. There might be a DB issue.")
            # Decide how to handle this - maybe exit, maybe try setting target anyway?
            # For now, let's try setting target, the error handling there might catch it.
            pass
        # --- End check ---

        # print(f"Mining process using node_id: {self.node_id}")
            # Continue anyway - we'll rebuild as needed

        try:
            self.settargetWhileBooting()
            # print("Target set successfully")
        except Exception as e:
            print(f"Error setting target: {e}")
            traceback.print_exc()
            # Continue anyway - we'll rebuild as needed

        while True:
            try:
                 # --- ADD DEBUG LOGGING ---
                # print(f"[Node {self.node_id} MainLoop DEBUG] Before main loop - newBlockAvailable: {dict(self.newBlockAvailable)}")
                # logger.info(f"[Node {self.node_id} MainLoop DEBUG] Before main loop - newBlockAvailable: {dict(self.newBlockAvailable)}")
                # --- END DEBUG LOGGING ---

                lastBlockDict = self.fetch_last_block()
                if lastBlockDict is None:
                    # This check is now more critical if the initial check failed
                    print("Cannot build next block: last block is None even after initial checks.")
                    time.sleep(10) # Wait before retrying
                    continue
                # --- Acquire Lock briefly to get current state ---
                with self.state_lock:
                    current_height = self.reorg_manager._get_current_height_unsafe()
                    print(f"[Node {self.node_id} MainLoop] Current height: {current_height}")
                    tip_hash = self.reorg_manager._get_tip_hash_unsafe()
                    print(f"[Node {self.node_id} MainLoop] Current tip hash: {tip_hash[:8]}...")
                # --- Lock Released ---

                next_height = current_height + 1
                print(f"Attempting to mine block {next_height} (Prev: {tip_hash[:8]}...)")
                self.addBlock(next_height, tip_hash)

                # Add a small delay to prevent busy-looping if mining fails instantly
                time.sleep(0.1)

            except Exception as e:
                 logger.error(f"[Node {self.node_id} MainLoop] Unexpected error: {e}", exc_info=True)
                 time.sleep(5) # Wait longer after an error


         # Check if we have a genesis block
        # lastBlock = self.fetch_last_block()
        # if lastBlock is None:
        #     print("No blockchain found - creating genesis block")
        #     self.GenesisBlock()

        # Build UTXOs directly in this process where database path works correctly
        

        
            
        # while True:
        #     lastBlock = self.fetch_last_block()
        #     print(f"[DEBUG main] lastBlock() returned = {lastBlock!r} (len={len(lastBlock) if lastBlock else None})")
        #     if lastBlock:
        #         print(f"[DEBUG main] last[0] = {lastBlock[0]!r} (type={type(lastBlock[0])})")
        #     BlockHeight = lastBlock[0]['Height'] + 1
        #     prevBlockHash = lastBlock[0]['BlockHeader']['blockHash']
        #     self.addBlock(BlockHeight, prevBlockHash)
        #     time.sleep(1) 

# if __name__ == '__main__':
#     """ read configuration file"""

#     config = configparser.ConfigParser()
#     config.read('config.ini')
#     localHost = config['DEFAULT']['host']
#     localHostPort = int(config['MINER']['port'])
#     simulateBTC = bool(config['MINER']['simulateBTC'])
#     webport = int(config['Webhost']['port'])

#     with Manager() as manager:
#         mem_pool = manager.dict()
#         utxos = manager.dict()
#         newBlockAvailable = manager.dict()
#         secondaryChain = manager.dict()

#         webapp = Process(target=main, args=(utxos, mem_pool, webport, localHostPort))
#         webapp.start()
#         """Start server and listen for miner/user requests"""

#         sync = syncManager(localHost,localHostPort, newBlockAvailable, secondaryChain, mem_pool)
#         startServer = Process(target=sync.spinUpServer)
#         startServer.start()

#         blockchain = Blockchain(utxos, mem_pool, newBlockAvailable, secondaryChain)
#         blockchain.startSync()
#         blockchain.buildUTXOS()
        
#         if simulateBTC:
#             autoBroadcastTxs = Process(target=autoBroadcast)
#             autoBroadcastTxs.start()

#         blockchain.settargetWhileBooting()
#         blockchain.main()