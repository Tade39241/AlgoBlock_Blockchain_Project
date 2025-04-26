import copy
import logging
import sys
import traceback
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.core.Tx import Tx, TxIn, TxOut

# --- Add this basic configuration near the top ---
# Configure logging for this module/process
log_format = '%(message)s'
# Log INFO level messages and above to standard error
logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stderr)
# You could also configure a FileHandler here if you want logs in a separate file per process
# --- End configuration ---

# Get a logger for this module
logger = logging.getLogger('reorg_manager')

ZERO_HASH = '0' * 64

class ReorgManager:
    def __init__(self, utxos, mem_pool, secondaryChain, db, node_id, lock):
        """
        Initializes the ReorgManager.

        Args:
            utxos: The shared UTXO dictionary (Manager.dict).
            mem_pool: The shared mempool dictionary (Manager.dict).
            secondaryChain: The shared secondary chain dictionary (Manager.dict).
            db: An instance of BlockchainDB for the current node.
            node_id: The ID of the current node (for logging).
        """
        self.utxos = utxos
        self.mem_pool = mem_pool
        self.secondaryChain = secondaryChain
        self.db = db
        self.node_id = node_id
        self.lock = lock
        logger.info(f"[Node {self.node_id} ReorgManager] Initialised.")
        # Note: The lock is managed by the Blockchain class which calls these methods.

    def apply_state_for_block(self, block_dict):
        """Applies state changes for a block. Assumes lock is held by caller."""
        logger.info(f"[Node {self.node_id} ApplyState] Applying state for block {block_dict.get('Height')}")
        try:
            for tx_dict in block_dict.get('Txs', []):
                tx_id = tx_dict.get('TxId')
                if not tx_id: continue

                # Remove spent UTXOs (Inputs) using tuple key
                for tx_in_dict in tx_dict.get('tx_ins', []):
                    prev_tx_hash = tx_in_dict.get('prev_tx')
                    prev_index = tx_in_dict.get('prev_index')
                    if prev_tx_hash == ZERO_HASH or prev_tx_hash == '0'*64: continue

                    utxo_key = (prev_tx_hash, prev_index) # Use tuple key
                    if utxo_key in self.utxos:
                        del self.utxos[utxo_key]
                    else:
                        # This might happen if the block is invalid, log warning
                        print(f"[ApplyState] UTXO {utxo_key} not found to spend for block {block_dict.get('Height')}.")

                # Add new UTXOs (Outputs) using tuple key
                for i, tx_out_dict in enumerate(tx_dict.get('tx_outs', [])):
                    utxo_key = (tx_id, i) # Use tuple key
                    try: # Inner try
                        print(f"[ApplyState] Attempting TxOut.from_dict for {utxo_key} with data: {tx_out_dict}")
                        tx_out_obj = TxOut.from_dict(tx_out_dict)
                        self.utxos[utxo_key] = tx_out_obj
                        print(f"[ApplyState] Successfully added UTXO {utxo_key}")
                    except Exception as e: # Inner except
                         print(f"[ApplyState Inner] FAILED TxOut.from_dict for {utxo_key}. Data was: {tx_out_dict}")
                         print(f"[ApplyState Inner] Exception type: {type(e).__name__}, Message: {e}")
                         print(traceback.format_exc()) # Make sure this is here
                         return False

                # Remove from Mempool
                if tx_id in self.mem_pool:
                    del self.mem_pool[tx_id]
            return True
        except Exception as e:
            print(f"[Node {self.node_id} ApplyState] ERROR applying state for block {block_dict.get('Height')}: {e}")
            return False

    def rewind_state_for_block(self, block_dict):
        """Reverses state changes for a block. Assumes lock is held by caller."""
        logger.info(f"[Node {self.node_id} RewindState] Rewinding state for block {block_dict.get('Height')}")
        try:
            # Process Txs in reverse order to handle dependencies correctly? Maybe not necessary for UTXO.
            for tx_dict in reversed(block_dict.get('Txs', [])):
                tx_id = tx_dict.get('TxId')
                if not tx_id: continue

                # --- Add back spent UTXOs (Inputs) ---
                # This requires finding the output that was spent.
                for tx_in_dict in tx_dict.get('tx_ins', []):
                    prev_tx_hash = tx_in_dict.get('prev_tx')
                    prev_index = tx_in_dict.get('prev_index')
                    if prev_tx_hash == ZERO_HASH or prev_tx_hash == '0'*64: continue

                    utxo_key_to_restore = (prev_tx_hash, prev_index) # Tuple key

                    # How to find the spent output? Requires fetching the original transaction.
                    # Option 1: Query DB for the block containing prev_tx_hash, then find the tx and output. (Slow)
                    # Option 2: Maintain a temporary cache during reorg? Complex.
                    # Option 3: Assume the necessary info (amount, scriptPubKey) is implicitly known or reconstructable? Risky.

                    # --- Placeholder for Option 1 (DB Lookup) ---
                    # This needs a way to efficiently find which block contains prev_tx_hash
                    # Or read_block_by_hash if you implement that in DB.
                    spent_output_dict = self._find_spent_output_from_db(prev_tx_hash, prev_index) # Needs implementation

                    if spent_output_dict:
                        self.utxos[utxo_key_to_restore] = spent_output_dict # Add the output dict/obj back
                    else:
                        # This is a critical error if we can't find the output to restore
                        logger.error(f"[RewindState] CRITICAL: Could not find spent output for {utxo_key_to_restore} while rewinding block {block_dict.get('Height')}. State inconsistent!")
                        # Should probably abort the reorg here.
                        return False
                    # --- End Placeholder ---

                # --- Remove newly created UTXOs (Outputs) ---
                for i, tx_out_dict in enumerate(tx_dict.get('tx_outs', [])):
                    utxo_key_to_remove = (tx_id, i) # Tuple key
                    if utxo_key_to_remove in self.utxos:
                        del self.utxos[utxo_key_to_remove]
                    # else: # This might happen if state was already inconsistent
                    #    logger.warning(f"[RewindState] UTXO {utxo_key_to_remove} not found to remove for block {block_dict.get('Height')}.")

                # --- Add back to Mempool (if not coinbase) ---
                is_coinbase = block_dict.get('Txs', [])[0].get('TxId') == tx_id
                if not is_coinbase:
                    # Store dict if mempool stores dicts, or convert to Tx object
                    self.mem_pool[tx_id] = tx_dict
            return True
        except Exception as e:
            logger.error(f"[Node {self.node_id} RewindState] ERROR rewinding state for block {block_dict.get('Height')}: {e}", exc_info=True)
            return False
        

    # --- Helper potentially needed by rewind_state_for_block ---
    def _find_spent_output_from_db(self, tx_hash, index):
        """Finds a specific output dict from a previous transaction using the DB tx_index."""
        try:
            # 1. Find the block height using the index
            block_height = self.db.get_tx_block_height(tx_hash)
            if block_height is None:
                logger.warning(f"[_find_spent_output_from_db] Tx {tx_hash} not found in DB index.")
                return None

            # 2. Read the block data from the main table
            block_dict = self.db.read_block(block_height)
            if not block_dict:
                logger.error(f"[_find_spent_output_from_db] Block {block_height} (indexed for tx {tx_hash}) not found in DB!")
                return None # Data inconsistency

            # Handle potential list wrapping if read_block returns [dict]
            if isinstance(block_dict, list) and len(block_dict) == 1:
                block_dict = block_dict[0]
            if not isinstance(block_dict, dict):
                 logger.error(f"[_find_spent_output_from_db] Invalid data type returned for block {block_height}: {type(block_dict)}")
                 return None

            # 3. Find the transaction within the block
            found_tx = None
            for tx_dict in block_dict.get('Txs', []):
                if tx_dict.get('TxId') == tx_hash:
                    found_tx = tx_dict
                    break

            if not found_tx:
                logger.error(f"[_find_spent_output_from_db] Tx {tx_hash} not found within block {block_height} data, despite being indexed!")
                return None # Data inconsistency

            # 4. Extract the specific output
            outputs = found_tx.get('tx_outs', [])
            if 0 <= index < len(outputs):
                return outputs[index] # Return the output dictionary
            else:
                logger.error(f"[_find_spent_output_from_db] Output index {index} out of bounds for tx {tx_hash} in block {block_height} (found {len(outputs)} outputs).")
                return None

        except Exception as e:
            logger.error(f"[_find_spent_output_from_db] Error finding output for {tx_hash}:{index}: {e}", exc_info=True)
            return None


    # --- Reorg Check/Execution Logic ---


    def check_for_reorg(self, current_height):
        """Checks if any fork in secondaryChain is better than main chain. Assumes lock is held by caller."""
        logger.info(f"[Node {self.node_id} ReorgCheck] Checking for better forks (current height {current_height})...")
        main_chain_length = current_height + 1
        best_fork_tip_hash = None
        best_fork_length = main_chain_length

        # Iterate potential forks stored in secondaryChain
        for fork_hash, fork_block_obj in list(self.secondaryChain.items()): # Iterate copy
            # Basic check: Is the fork block itself higher than current height?
            if not isinstance(fork_block_obj, Block):
                 logger.warning(f"[ReorgCheck] Invalid object in secondaryChain for hash {fork_hash}. Skipping.")
                 continue
            if fork_block_obj.Height < current_height: # Optimization: skip forks guaranteed to be shorter
                 continue

            fork_length = self._calculate_chain_length(fork_hash, current_height) # Pass current height for safety break
            if fork_length > best_fork_length:
                best_fork_length = fork_length
                best_fork_tip_hash = fork_hash

        # If a better fork is found, execute the reorg
        if best_fork_tip_hash:
            logger.info(f"[Node {self.node_id} ReorgCheck] Found better fork (length {best_fork_length}) ending in {best_fork_tip_hash[:8]}...")
            self._execute_reorg(best_fork_tip_hash, current_height)
        # else:
        #     logger.info(f"[Node {self.node_id} ReorgCheck] No better fork found.")


    def _get_current_height_unsafe(self):
        """Gets current height. Assumes lock is already held."""
        # Duplicated from Blockchain class - consider passing height or using DB directly
        last_block_dict = self.db.lastBlock()
        return last_block_dict['Height'] if last_block_dict and 'Height' in last_block_dict else -1

    def _get_tip_hash_unsafe(self):
        """Gets tip hash. Assumes lock is already held."""
        # Duplicated from Blockchain class - consider passing tip or using DB directly
        last_block_dict = self.db.lastBlock()
        if last_block_dict:
             block_hash = last_block_dict.get('BlockHeader', {}).get('blockHash') or last_block_dict.get('blockHash')
             return block_hash if block_hash else ZERO_HASH
        else:
             return ZERO_HASH

    def _calculate_chain_length(self, tip_hash, current_main_height):
        """Calculates length of a chain ending at tip_hash. Assumes lock is held by caller."""
        count = 0
        current_hash = tip_hash
        safety_limit = current_main_height + 50 # Limit traceback depth

        while current_hash != ZERO_HASH and current_hash != '0'*64:
            block_obj = None
            block_dict = None

            # 1. Check memory cache first
            if current_hash in self.secondaryChain:
                cached_obj = self.secondaryChain[current_hash]
                if isinstance(cached_obj, Block): # Ensure it's a Block object
                     block_obj = cached_obj
                else:
                     logger.warning(f"[CalculateLength] Non-Block object found in secondaryChain for {current_hash}. Stopping trace.")
                     return 0
                
            # 2. If not in memory, try reading from DB by hash
            if not block_obj:
                block_dict = self.db.read_block_by_hash(current_hash)
                if block_dict:
                    # Convert dict to Block object for consistent handling
                    try:
                        block_obj = Block.from_dict(block_dict) # Assumes Block.from_dict exists
                    except Exception as e:
                        logger.error(f"[CalculateLength] Failed to convert block dict (hash {current_hash}) to Block object: {e}. Stopping trace.", exc_info=True)
                        return 0
                else: # Block not found in DB either
                    logger.warning(f"[CalculateLength] Block {current_hash[:8]} not found in secondaryChain or DB. Stopping trace.")
                    return 0 # Cannot calculate full length

            # Process the found block (either from cache or DB)
                

            if block_obj:
                count += 1
                current_hash = block_obj.BlockHeader.prevBlockHash.hex()
                if count > safety_limit: # Safety break
                    logger.error(f"[CalculateLength] Traceback limit ({safety_limit}) exceeded for fork {tip_hash[:8]}. Aborting.")
                    return 0
            else:
                # Should not happen if secondaryChain check is done correctly
                logger.warning(f"[CalculateLength] Could not find block object for hash {current_hash}. Chain broken?")
                return 0 # Chain is broken

        return count # Length is number of blocks
    
    def _find_common_ancestor(self, fork_tip_hash, current_main_height):
        """Finds common ancestor block hash and height. Assumes lock is held by caller."""
        logger.info(f"[Node {self.node_id} FindAncestor] Finding common ancestor for fork {fork_tip_hash[:8]}...")
        fork_ancestors = {} # hash -> height (or just set of hashes)
        current_hash = fork_tip_hash
        safety_limit = current_main_height + 100

        # Build ancestor set/dict for the fork chain (trace back fork)
        processed_count = 0
        while current_hash != ZERO_HASH and current_hash != '0'*64:
            fork_ancestors[current_hash] = processed_count # Store depth or height if calculable

            block_obj = None
            block_dict = None

            # 1. Check memory cache
            if current_hash in self.secondaryChain:
                 cached_obj = self.secondaryChain[current_hash]
                 if isinstance(cached_obj, Block): block_obj = cached_obj
                 else: break # Invalid cache entry

            # 2. Check DB by hash
            if not block_obj:
                 block_dict = self.db.read_block_by_hash(current_hash)
                 if block_dict:
                      try:
                           block_obj = Block.from_dict(block_dict) # Assumes Block.from_dict
                      except Exception as e:
                           logger.error(f"[FindAncestor] Failed to convert fork block dict (hash {current_hash}) to Block object: {e}. Stopping trace.", exc_info=True)
                           break # Cannot proceed with fork trace
                 # else: # Block not found in DB
                 #      logger.warning(f"[FindAncestor] Fork block {current_hash[:8]} not found in cache or DB. Stopping trace.")
                 #      break # Fork chain broken or incomplete

            # Get previous hash
            if block_obj:
                current_hash = block_obj.BlockHeader.prevBlockHash.hex()
                processed_count += 1
                if processed_count > safety_limit: # Safety break
                    logger.error("[FindAncestor] Fork traceback limit exceeded.")
                    return None, -1
            else:
                 # Block not found in cache or DB
                 logger.warning(f"[FindAncestor] Fork block {current_hash[:8]} not found in cache or DB. Stopping trace.")
                 break # Fork chain broken or incomplete

        # Trace back main chain from DB (using height)
        main_height = current_main_height
        processed_count = 0
        while main_height >= 0:
            block_dict = self.db.read_block(main_height) # Read by height
            if not block_dict:
                logger.error(f"[FindAncestor] ERROR: Main chain block {main_height} not found in DB.")
                return None, -1

            # Extract block hash robustly
            block_hash = block_dict.get('BlockHeader', {}).get('blockHash') or block_dict.get('blockHash')
            if not block_hash:
                logger.error(f"[FindAncestor] ERROR: Cannot find hash for main chain block {main_height}.")
                return None, -1

            # Check if this main chain block hash is in the fork's ancestor list
            if block_hash in fork_ancestors:
                logger.info(f"[FindAncestor] Found common ancestor at height {main_height} ({block_hash[:8]}...)")
                return block_hash, main_height

            main_height -= 1
            processed_count += 1
            if processed_count > current_main_height + 50: # Safety break for main chain trace
                 logger.error("[FindAncestor] Main chain traceback limit exceeded.")
                 return None, -1

        logger.warning("[FindAncestor] No common ancestor found (reached genesis?).")
        return None, -1 # Indicate no common ancestor found


    # def _find_common_ancestor(self, fork_tip_hash, current_main_height):
    #     """Finds common ancestor block hash and height. Assumes lock is held by caller."""
    #     logger.info(f"[Node {self.node_id} FindAncestor] Finding common ancestor for fork {fork_tip_hash[:8]}...")
    #     fork_ancestors = {} # hash -> height
    #     current_hash = fork_tip_hash
    #     # Calculate starting height based on length (requires reliable _calculate_chain_length)
    #     fork_len = self._calculate_chain_length(fork_tip_hash, current_main_height)
    #     if fork_len == 0:
    #          logger.error("[FindAncestor] Cannot calculate fork length. Aborting.")
    #          return None, -1
    #     height_counter = fork_len - 1
    #     safety_limit = current_main_height + 50

    #     # Build ancestor list/dict for the fork chain
    #     processed_count = 0
    #     while current_hash != ZERO_HASH and current_hash != '0'*64 and height_counter >= 0:
    #         fork_ancestors[current_hash] = height_counter
    #         block = None
    #         if current_hash in self.secondaryChain:
    #             block_obj = self.secondaryChain[current_hash]
    #             if isinstance(block_obj, Block): block = block_obj
    #             else: break # Invalid object
    #         else:
    #             # block_dict = self.db.read_block_by_hash(current_hash) # Needs DB method
    #             # if block_dict: block = Block.to_obj(block_dict)
    #             logger.warning(f"[FindAncestor] Fork block {current_hash[:8]} not in secondaryChain, DB lookup needed (not implemented). Stopping trace.")
    #             break # Fork chain broken or requires DB lookup

    #         if block:
    #             current_hash = block.BlockHeader.prevBlockHash.hex()
    #             height_counter -= 1
    #             processed_count += 1
    #             if processed_count > safety_limit: # Safety break
    #                 logger.error("[FindAncestor] Fork traceback limit exceeded.")
    #                 return None, -1
    #         else:
    #             break # Fork chain broken

    #     # Trace back main chain from DB
    #     main_height = current_main_height
    #     processed_count = 0
    #     while main_height >= 0:
    #         block_dict = self.db.read_block(main_height) # Read by height
    #         if not block_dict:
    #             logger.error(f"[FindAncestor] ERROR: Main chain block {main_height} not found in DB.")
    #             return None, -1

    #         # Extract block hash robustly
    #         block_hash = block_dict.get('BlockHeader', {}).get('blockHash') or block_dict.get('blockHash')
    #         if not block_hash:
    #             logger.error(f"[FindAncestor] ERROR: Cannot find hash for main chain block {main_height}.")
    #             return None, -1

    #         if block_hash in fork_ancestors:
    #             logger.info(f"[FindAncestor] Found common ancestor at height {main_height} ({block_hash[:8]}...)")
    #             return block_hash, main_height

    #         main_height -= 1
    #         processed_count += 1
    #         if processed_count > current_main_height + 10: # Safety break
    #              logger.error("[FindAncestor] Main chain traceback limit exceeded.")
    #              return None, -1


    #     logger.warning("[FindAncestor] No common ancestor found (reached genesis?).")
    #     return None, -1 # Indicate no common ancestor found

    def _get_fork_blocks(self, fork_tip_hash, ancestor_hash, current_main_height):
        """Gets list of Block objects for a fork from ancestor+1 to tip. Assumes lock is held by caller."""
        blocks = []
        current_hash = fork_tip_hash
        safety_limit = current_main_height + 100

        while current_hash != ancestor_hash and current_hash != ZERO_HASH and current_hash != '0'*64:
            block_obj = None
            block_dict = None

            # 1. Check memory cache
            if current_hash in self.secondaryChain:
                 cached_obj = self.secondaryChain[current_hash]
                 if isinstance(cached_obj, Block): block_obj = cached_obj
                 else:
                      logger.error(f"[GetForkBlocks] Invalid object in secondaryChain for {current_hash}. Aborting.")
                      return [] # Invalid cache entry

            # 2. Check DB by hash
            if not block_obj:
                 block_dict = self.db.read_block_by_hash(current_hash)
                 if block_dict:
                      try:
                           block_obj = Block.from_dict(block_dict) # Assumes Block.from_dict
                      except Exception as e:
                           logger.error(f"[GetForkBlocks] Failed to convert fork block dict (hash {current_hash}) to Block object: {e}. Aborting.", exc_info=True)
                           return [] # Cannot proceed
                 # else: # Block not found in DB
                 #      logger.error(f"[GetForkBlocks] ERROR: Fork block {current_hash[:8]} not found in cache or DB. Cannot retrieve full fork.")
                 #      return [] # Failed to get full fork

            # Process found block
            if block_obj:
                blocks.append(block_obj)
                current_hash = block_obj.BlockHeader.prevBlockHash.hex()
                if len(blocks) > safety_limit: # Safety break
                    logger.error("[GetForkBlocks] Traceback limit exceeded.")
                    return []
            else:
                 # Block not found in cache or DB
                 logger.error(f"[GetForkBlocks] ERROR: Fork block {current_hash[:8]} not found in cache or DB. Cannot retrieve full fork.")
                 return [] # Failed to get full fork

        return blocks[::-1] # Return in order from ancestor+1 to tip




    # def _get_fork_blocks(self, fork_tip_hash, ancestor_hash, current_main_height):
    #     """Gets list of Block objects for a fork from ancestor+1 to tip. Assumes lock is held by caller."""
    #     blocks = []
    #     current_hash = fork_tip_hash
    #     safety_limit = current_main_height + 50

    #     while current_hash != ancestor_hash and current_hash != ZERO_HASH and current_hash != '0'*64:
    #         block = None
    #         if current_hash in self.secondaryChain:
    #              block_obj = self.secondaryChain[current_hash]
    #              if isinstance(block_obj, Block): block = block_obj
    #              else:
    #                   logger.error(f"[GetForkBlocks] Invalid object in secondaryChain for {current_hash}. Aborting.")
    #                   return []
    #         else:
    #             # block_dict = self.db.read_block_by_hash(current_hash) # Needs DB method
    #             # if block_dict: block = Block.to_obj(block_dict)
    #             logger.warning(f"[GetForkBlocks] Fork block {current_hash[:8]} not in secondaryChain, DB lookup needed (not implemented). Aborting.")
    #             return [] # Failed to get full fork without DB lookup

    #         if block:
    #             blocks.append(block)
    #             current_hash = block.BlockHeader.prevBlockHash.hex()
    #             if len(blocks) > safety_limit: # Safety break
    #                 logger.error("[GetForkBlocks] Traceback limit exceeded.")
    #                 return []
    #         else:
    #             logger.error(f"[GetForkBlocks] ERROR: Fork chain broken at {current_hash}. Cannot retrieve full fork.")
    #             return [] # Failed to get full fork

    #     return blocks[::-1] # Return in order from ancestor+1 to tip


    def _execute_reorg(self, best_fork_tip_hash, current_main_height):
        """Performs the chain reorganization. Assumes lock is held by caller."""
        logger.info(f"[Node {self.node_id} ExecuteReorg] Starting reorg to fork {best_fork_tip_hash[:8]}...")

        common_ancestor_hash, common_ancestor_height = self._find_common_ancestor(best_fork_tip_hash, current_main_height)

        if common_ancestor_hash is None:
            logger.error("[ExecuteReorg] Aborting: Could not find common ancestor.")
            # Consider removing the problematic fork tip from secondaryChain
            if best_fork_tip_hash in self.secondaryChain:
                 del self.secondaryChain[best_fork_tip_hash]
            return

        # --- 1. Rewind Main Chain ---
        logger.info(f"[ExecuteReorg] Rewinding main chain from {current_main_height} down to {common_ancestor_height}")
        rewind_success = True
        for height in range(current_main_height, common_ancestor_height, -1):
            block_dict = self.db.read_block(height)
            if block_dict:
                logger.info(f"[ExecuteReorg] Rewinding block {height}...")
                if not self.rewind_state_for_block(block_dict): # Rewind UTXO/Mempool
                     logger.error(f"[ExecuteReorg] CRITICAL: Failed to rewind state for block {height}. State inconsistent!")
                     rewind_success = False
                     break # Stop rewinding state if error occurs
            else:
                logger.error(f"[ExecuteReorg] ERROR: Block {height} not found in DB during rewind. Aborting reorg.")
                # State might be partially rewound. Very bad.
                return # Abort

        if not rewind_success:
             logger.error("[ExecuteReorg] Aborting reorg due to state rewind failure.")
             # Cannot safely proceed.
             return

        # Physically delete blocks from DB *after* state rewind
        deleted_count = self.db.delete_blocks_from_height(common_ancestor_height + 1)
        logger.info(f"[ExecuteReorg] Deleted {deleted_count} blocks from DB (height >= {common_ancestor_height + 1})")

        # --- 2. Apply New Fork ---
        fork_blocks = self._get_fork_blocks(best_fork_tip_hash, common_ancestor_hash, current_main_height)
        logger.info(f"[ExecuteReorg] Applying {len(fork_blocks)} blocks from new fork...")

        if not fork_blocks:
            logger.error("[ExecuteReorg] ERROR: Failed to retrieve blocks for the new fork. Aborting reorg.")
            # Main chain rewound, but no new fork applied. Very bad state.
            # Need robust error handling / recovery strategy.
            return

        apply_success = True
        for block_obj in fork_blocks:
            logger.info(f"[ExecuteReorg] Applying block {block_obj.Height} ({block_obj.BlockHeader.generateBlockHash()[:8]}...)")
            # Apply state first
            block_obj_copy = copy.deepcopy(block_obj)
            block_dict = block_obj_copy.to_dict()

            if not self.apply_state_for_block(block_dict): # Apply state using dict
                 logger.error(f"[ExecuteReorg] CRITICAL: Failed to apply state for block {block_obj.Height}.")
                 apply_success = False
                 break
            try:
                 self.db.write(block_dict) # Write dict to DB
            except Exception as e:
                 logger.error(f"[ExecuteReorg] CRITICAL: Failed to write block {block_obj.Height} to DB: {e}.")
                 apply_success = False
                 # Attempt state rewind?
                 break

        if apply_success:
            new_height = common_ancestor_height + len(fork_blocks)
            logger.info(f"[Node {self.node_id} ExecuteReorg] Reorganization successful. New tip height: {new_height}")
            # Clean up secondaryChain - remove blocks that are now part of main chain
            applied_hashes = {b.BlockHeader.generateBlockHash() for b in fork_blocks}
            for h in applied_hashes:
                if h in self.secondaryChain:
                    del self.secondaryChain[h]
            # Also remove the old main chain blocks that were rewound? Maybe not necessary.
        else:
            logger.critical(f"[Node {self.node_id} ExecuteReorg] Reorganization failed during fork application. Blockchain state is likely inconsistent!")
            # Need manual intervention or more robust recovery.
