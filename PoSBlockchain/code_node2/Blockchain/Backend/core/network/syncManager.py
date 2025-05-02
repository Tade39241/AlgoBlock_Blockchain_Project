from io import BytesIO
import random
import socket
import threading
import time
from Blockchain.Backend.core.network.connection import Node
from Blockchain.Backend.core.database.db import BlockchainDB, NodeDB, AccountDB
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.core.network.network import requestBlock, NetworkEnvelope, FinishedSending, portList, GetPeerTip, PeerTip
from Blockchain.Backend.core.tx import Tx, TxIn, TxOut
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.util.util import little_endian_to_int, int_to_little_endian, merkle_root
from Blockchain.client.account import account
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import Signature
from threading import Thread
import traceback
import logging

logger = logging.getLogger(__name__)

import json

ZERO_HASH = "0" * 64


class syncManager:
    """
        Initialize the sync manager.
        
        Args:
            host: The host address to connect to
            port: The port to connect to
            blockchain: The blockchain instance (optional for transaction broadcasting)
            localHostPort: The local port (optional for transaction broadcasting)
    """
    def __init__(self, host, port, MemoryPool ,blockchain=None, localHostPort=None, newBlockAvailable=None,secondaryChain=None, my_public_addr=None,shared_lock=None):
        self.host = host
        self.port = port
        self.blockchain = blockchain
        self.newBlockAvailable = {} if newBlockAvailable is None else newBlockAvailable        
        self.secondaryChain = secondaryChain
        self.MemoryPool = MemoryPool if MemoryPool is not None else {}
        self.localHostPort = localHostPort
        self.my_public_addr = my_public_addr  # Store the node's public address here
        self.state_lock = shared_lock
        self._is_syncing_lock = threading.Lock() # Lock to protect the flag
        self._is_syncing = False
        # You might also need an event if using Option 2 signaling
        # self.sync_needed_event = threading.Event()

    def spinUpServer(self):
        self.server = Node(self.host, self.port)
        self.server.startServer()
        print("SERVER STARTED")
        print(f"LISTENING at {self.host}:{self.port}")    

        while True:
            self.conn, self.addr = self.server.acceptConnection()
            handleConn = Thread(target=self.handleConnection)
            handleConn.start()

    def query_peer_tips(self):
        """
        Sends 'getpeertip' to known peers and collects 'peertip' responses.
        Returns a dictionary {peer_port: {'height': H, 'tip_hash': 'HASH'}, ...}
        NOTE: This is a simplified, blocking implementation.
        """
        logger.info("[Query Tips] Requesting tip info from peers...")
        peer_tips = {}
        node_db = NodeDB()
        peers = node_db.read_nodes() or []
        if node_db.conn: node_db.conn.close() # Close DB connection

        # Create the request message once
        get_tip_request = GetPeerTip()
        request_envelope_bytes = get_tip_request.serialise() # Serialise once

        node_id = self.localHostPort - 9000 if self.localHostPort else 0
        local_bind_port = 8000 + node_id # For potential binding

        for peer_port in peers:
            # Ensure peer_port is an integer
            try: peer_port = int(peer_port)
            except (ValueError, TypeError): continue # Skip invalid ports

            if peer_port == self.localHostPort: # Don't query self
                continue

            logger.debug(f"[Query Tips] Attempting to query peer {peer_port}...")
            sock, connector = None, None
            response_envelope = None
            try:
                # Use connectToHost (which uses Node internally)
                # Setting bind_needed_flag to False might be okay for short requests
                sock, connector = self.connectToHost(local_bind_port, peer_port, False)
                if not sock or not connector:
                    logger.warning(f"[Query Tips] Failed to connect to peer {peer_port}.")
                    continue

                # Send the GetPeerTip request
                connector.send(request_envelope_bytes) # Assuming send_raw exists or adapt send
                logger.debug(f"[Query Tips] Sent GetPeerTip to {peer_port}.")

                # Wait for a response (blocking read with timeout)
                # The Node.read() method needs a timeout mechanism
                response_envelope = connector.read(timeout=5.0) # Add timeout parameter to read()

                if response_envelope is None:
                    logger.warning(f"[Query Tips] No response received from {peer_port} within timeout.")
                    continue

                # Check if the response is the expected PeerTip
                if response_envelope.command == PeerTip.command:
                    try:
                        tip_response = PeerTip.parse(response_envelope.stream())
                        peer_tips[peer_port] = {
                            'height': tip_response.height,
                            'tip_hash': tip_response.tip_hash
                        }
                        logger.info(f"[Query Tips] Received tip from {peer_port}: Height={tip_response.height}, Hash={tip_response.tip_hash[:8]}...")
                    except Exception as e_parse:
                        logger.warning(f"[Query Tips] Failed to parse PeerTip response from {peer_port}: {e_parse}")
                else:
                    logger.warning(f"[Query Tips] Received unexpected command {response_envelope.command} from {peer_port} instead of PeerTip.")

            except socket.timeout:
                 logger.warning(f"[Query Tips] Socket timeout connecting to or reading from {peer_port}.")
            except ConnectionRefusedError:
                 logger.warning(f"[Query Tips] Connection refused by {peer_port}.")
            except Exception as e:
                logger.error(f"[Query Tips] Error querying peer {peer_port}: {e}", exc_info=True)
            finally:
                # Close the connection used for this query
                if sock:
                    try: sock.close()
                    except Exception: pass
                # If connector holds resources, ensure they are released
                # if connector: connector.close() # If connector has a close method

        logger.info(f"[Query Tips] Finished querying peers. Collected {len(peer_tips)} responses.")
        return peer_tips

    def initiate_catch_up_sync(self, current_height ,triggered_by_peer_port=None):
        """
        Initiates the download process to catch up with the network using the existing startDownload method.
        Prevents starting multiple syncs simultaneously.
        """
        with self._is_syncing_lock:
            if self._is_syncing:
                logger.info("[Catch-Up] Sync already in progress, skipping new trigger.")
                return
            self._is_syncing = True

        try:
            peer_msg = f" (triggered by {triggered_by_peer_port})" if triggered_by_peer_port else ""
            logger.info(f"[Catch-Up] Starting sync process{peer_msg}. Local height: {current_height}")

            peer_tips = self.query_peer_tips() # Fetch peer tips

            if not peer_tips:
                logger.warning("[Catch-Up] No peers responded with tip information.")
                return # Exit if no peers

            # --- Identify Best Chain (Your existing logic) ---
            best_height = current_height
            best_tip_hash = None
            best_peers = []

            for peer_port, tip_info in peer_tips.items():
                peer_height = tip_info.get('height', -1)
                peer_tip_hash = tip_info.get('tip_hash', None) # Assuming hash is hex string

                # Convert peer_tip_hash to bytes if needed for comparison later
                # peer_tip_hash_bytes = bytes.fromhex(peer_tip_hash) if peer_tip_hash else None

                if peer_height > best_height:
                    best_height = peer_height
                    best_tip_hash = peer_tip_hash # Store best hash (hex)
                    best_peers = [peer_port] # Start new list
                elif peer_height == best_height and peer_height > current_height:
                    # Optional: Add logic here to compare hashes if heights are equal
                    # if peer_tip_hash != best_tip_hash:
                    #     logger.warning(f"Potential fork detected at height {best_height}. Sticking with first peer found.")
                    # else:
                    best_peers.append(peer_port) # Add peer to existing best height

            logger.info(f"[Catch-Up] Best height found among peers: {best_height}. Local height: {current_height}")

            if best_height <= current_height:
                logger.info("[Catch-Up] Local chain appears up-to-date.")
                return # Sync not needed

            logger.info(f"[Catch-Up] Sync required. Best peer(s) at height {best_height}: {best_peers}")

            if best_peers:
                # --- Select Peer ---
                target_peer_port = random.choice(best_peers) # Choose one target peer port
                logger.info(f"[Catch-Up] Attempting download from peer {target_peer_port} (target height {best_height})...")

                # --- Prepare arguments for the EXISTING startDownload ---
                # When acting as a client initiating a download, we usually DON'T
                # need to bind to a specific local port. Let the OS choose.
                local_port_arg = 0 # Pass 0 to indicate OS should choose ephemeral port if needed by connectToHost
                bind_needed_flag = False # Set to False because we don't need to bind locally

                # --- Call the EXISTING startDownload with required arguments ---
                try:
                    logger.debug(f"Calling self.startDownload(localport_to_bind={local_port_arg}, target_port={target_peer_port}, bind_needed_flag={bind_needed_flag})")
                    # <<< CALLING THE EXISTING METHOD >>>
                    self.startDownload(local_port_arg, target_peer_port, bind_needed_flag)

                    # Check final height after download attempt finishes
                    # This assumes startDownload blocks until complete or failed
                    final_height = self.blockchain.get_height()
                    if final_height >= best_height:
                         logger.info(f"[Catch-Up] Sync download phase finished. Final height {final_height}.")
                         # sync_successful = True # Mark success if needed elsewhere
                    else:
                         logger.warning(f"[Catch-Up] Sync download phase ended. Final height {final_height}, target was {best_height}.")
                except Exception as e_download:
                     # Catch errors specifically from the startDownload call
                     logger.error(f"[Catch-Up] Error during download call for peer {target_peer_port}: {e_download}", exc_info=True)
            else:
                 logger.warning("[Catch-Up] No suitable peers found at the best height to download from.")

        except Exception as e:
            # Catch errors during the coordination part (query_peer_tips, finding best peer)
            logger.error(f"[Catch-Up] Error during catch-up sync coordination: {e}", exc_info=True)
        finally:
            # Reset the flag regardless of outcome
            with self._is_syncing_lock:
                self._is_syncing = False
            logger.info("[Catch-Up] Sync flag reset.")


    def handleConnection(self):
        conn_info = f"from {self.addr}" if hasattr(self, 'addr') else "from unknown" # Get conn info early
        # print(f"[Server Handler {conn_info}] Connection accepted.")
        # --- PORTCHECK MAGIC HANDLING ---
        try:
            # Peek at the first 9 bytes to check for port check magic
            portcheck_magic = self.conn.recv(9, socket.MSG_PEEK)
            if portcheck_magic == b'PORTCHECK':
                self.conn.recv(9)  # Consume the bytes
                print("[syncManager] Received port check magic, closing connection.")
                self.conn.close()
                return
        except Exception as e:
            print(f"[syncManager] Error checking for port check magic: {e}")
            print(f"[Server Handler {conn_info}] Closing connection due to port check error.")
            if hasattr(self, 'conn') and self.conn: self.conn.close() # Ensure close
            return
        # --- END PORTCHECK MAGIC HANDLING ---
        from Blockchain.Backend.core.pos_blockchain import ZERO_HASH
        envelope = self.server.read()

        # print(f"[Server Handler {conn_info}] Received command: {envelope.command}")
        try:
            if envelope is None:
                logger.info(f"[Handler {conn_info}] Read returned None (timeout or connection closed). Ending handler.")
                return 
            if len(str(self.addr[1]))== 4:
                print(f"[Server Handler {conn_info}] Attempting addNode check...")
                self.addNode()

            elif envelope.command == GetPeerTip.command:
                logger.info(f"[Handler {conn_info}] Received GetPeerTip request.")
                tip_hash = ZERO_HASH
                height = -1
                response_envelope_bytes = None
                try:
                    # Get local tip info safely (use blockchain proxy)
                    # Need lock if get_height/get_tip_hash read DB? Assume they are safe or handle locks.
                    height = self.blockchain.get_height()
                    tip_hash = self.blockchain.get_tip_hash()

                    if tip_hash is None: # Handle error from get_tip_hash
                        logger.error(f"[Handler {conn_info}] Failed to get local tip hash to respond to GetPeerTip.")
                        # Maybe send an error response? For now, just close.
                        return # Or break loop

                    # Create the PeerTip response message
                    response_message = PeerTip(height=height, tip_hash=tip_hash)
                    response_envelope_bytes = response_message.serialise()

                    # Send the response back using the existing connection (conn)
                    self.conn.sendall(response_envelope_bytes)
                    logger.info(f"[Handler {conn_info}] Sent PeerTip response: Height={height}, Hash={tip_hash[:8]}...")

                except Exception as e:
                    logger.error(f"[Handler {conn_info}] Error processing GetPeerTip or sending PeerTip: {e}", exc_info=True)
            
            if envelope.command == b'tx':
                Transaction = Tx.parse(envelope.stream())
                # print(f"[DEBUG] Incoming TX serialized hex: {Transaction.serialise().hex()}")
                # print(f"[DEBUG] Incoming TX TxId: {Transaction.id()}")
                calculated_txid = Transaction.id()
                Transaction.TxId = Transaction.id()
                if calculated_txid != Transaction.TxId:
                        raise ValueError(f"TxId Mismatch! Calculated: {calculated_txid}, Received: {Transaction.TxId}")
                print(f"Transaction Received : {Transaction.TxId}")
                
                self.MemoryPool[Transaction.TxId] = Transaction
                # print(f"[DEBUG] MemoryPool now has: {list(self.MemoryPool.keys())}")
                # print(f"[Server Handler {conn_info}] Processed tx command.")

            elif envelope.command == b'block':
                    db_instance = BlockchainDB()
                    
                    # --- PROCESS BLOCK IMMEDIATELY ---
                    block_obj = None # Define block_obj outside try for logging
                    try:
                        block_obj = Block.parse(envelope.stream())
                        current_height = self.blockchain.get_height() # Get current height BEFORE validation

                        expected_height = current_height + 1
                        if block_obj.Height > expected_height:
                            logger.warning(f"[Handler] Received block height {block_obj.Height} is ahead of local tip {current_height}. Triggering sync.")
                            # Trigger a download process to catch up (non-blocking if possible)
                            # Option 1: Run in a new thread
                            threading.Thread(target=self.initiate_catch_up_sync, # Pass the method itself
                                        args=(current_height, self.localHostPort), # Pass args tuple
                                        daemon=True).start()
                            return
                        
                        elif block_obj.Height < expected_height:
                            logger.warning(f"[Handler] Received block height {block_obj.Height} is behind local tip {current_height}. Discarding.")
                            # Potentially send our higher block to the peer if needed? (More complex)
                            return # 
                        

                        # logger.info(f"[Handler] Received Block: Height={block_obj.Height}")

                        # --- START VALIDATION ---
                        header_obj = block_obj.BlockHeader

                        try:
                            header_obj.prevBlockHash = to_bytes_field(header_obj.prevBlockHash)
                            header_obj.merkleRoot = to_bytes_field(header_obj.merkleRoot)
                            header_obj.validator_pubkey = to_bytes_field(header_obj.validator_pubkey)
                            # Parse signature if needed BEFORE hashing
                            sig_field = header_obj.signature
                            if sig_field and not isinstance(sig_field, Signature):
                                    try: header_obj.signature = Signature.parse(sig_field)
                                    except Exception as e: raise ValueError(f"Invalid signature parse: {e}")
                            elif not sig_field: raise ValueError("Missing signature")

                            # Now calculate and store the hash
                            block_hash_hex = header_obj.generateBlockHash() # Calls serialise_with_signature
                            header_obj.blockHash = block_hash_hex # Store the calculated hex hash on the object
                            # logger.info(f"[Handler] Calculated hash for received block {block_obj.Height}: {block_hash_hex[:8]}...")
                        except Exception as e_hash:
                                logger.error(f"Failed to calculate hash for block {block_obj.Height}: {e_hash}", exc_info=True)
                                raise ValueError("Block hash calculation failed")
                        
                        # 2. Signature Parsing/Check (Already done during hash calc, but keep check)
                        if not isinstance(header_obj.signature, Signature):
                             # This case should ideally not be hit if hashing worked
                             raise ValueError("Signature object missing after hash calculation")

                        lock_type = type(self.state_lock)
                        lock_value_repr = repr(self.state_lock) # Use repr for potentially complex objects
                        logger.debug(f"[Handler {conn_info}] Acquiring lock. Type: {lock_type}, Value: {lock_value_repr}")
                        # 2. Check against Local Chain Tip (Needs Lock for Read Safety)
                        with self.state_lock: # Acquire lock to read DB/tip safely
                            last_block_dict = db_instance.lastBlock() # Use self.db
                            current_height = -1
                            tip_hash = ZERO_HASH
                            if last_block_dict:
                                 last_block_dict = last_block_dict[0] if isinstance(last_block_dict, list) else last_block_dict
                                 current_height = last_block_dict.get('Height', -1)
                                 tip_hash = last_block_dict.get('BlockHeader', {}).get('blockHash', ZERO_HASH)
                        # --- Release Lock ---

                        prev_hash_bytes = to_bytes_field(header_obj.prevBlockHash)
                        prev_hash_hex = prev_hash_bytes.hex()

                        if block_obj.Height != current_height + 1:
                             raise ValueError(f"Invalid height. Local tip {current_height}, got {block_obj.Height}")
                        if prev_hash_hex != tip_hash:
                             # Log both for comparison
                             logger.warning(f"Invalid prevBlockHash for received block {block_obj.Height}.")
                             logger.warning(f"  Expected tip: {tip_hash}")
                             logger.warning(f"  Received prev: {prev_hash_hex}")
                             raise ValueError(f"Invalid prevBlockHash.")

                        # 3. Internal Validation (Signature vs PubKey)
                        header_obj.validator_pubkey = to_bytes_field(header_obj.validator_pubkey)
                        if not header_obj.validate_block(): # Assumes this checks sig
                            raise ValueError("Block signature/content validation failed")

                        # # 4. (Optional but Recommended) Merkle Root Validation
                        # try:
                        #     tx_ids_bytes = [bytes.fromhex(tx.id()) for tx in block_obj.Txs]
                        #     calculated_merkle_root_bytes = merkle_root(tx_ids_bytes)[::-1]
                        #     header_merkle_root_bytes = to_bytes_field(header_obj.merkleRoot)
                        #     if calculated_merkle_root_bytes != header_merkle_root_bytes:
                        #          raise ValueError(f"Merkle root mismatch. Calc: {calculated_merkle_root_bytes.hex()}, Header: {header_merkle_root_bytes.hex()}")
                        # except Exception as e_mr:
                        #      raise ValueError(f"Merkle root calculation/validation failed: {e_mr}")
                        # # --- END VALIDATION ---

                        merkle_start = time.time()
                        try:
                            # --- Get TxIDs ---
                            received_tx_ids_for_merkle_hex = []
                            if not hasattr(block_obj, 'Txs') or not isinstance(block_obj.Txs, list):
                                 raise ValueError("Invalid Txs list in received block.")

                            logger.debug(f"[Handler {conn_info}] Calculating Tx IDs from received {len(block_obj.Txs)} transactions for Merkle check...")
                            for i, tx_obj in enumerate(block_obj.Txs):
                                 # ... (validation of tx_obj) ...
                                 try:
                                     tx_id_hex = tx_obj.id()
                                     received_tx_ids_for_merkle_hex.append(tx_id_hex)
                                     logger.debug(f"  Tx {i}: ID={tx_id_hex}")
                                 except Exception as e_id_calc:
                                      raise ValueError(f"Failed to calculate ID for tx at index {i}") from e_id_calc

                            logger.debug(f"[Handler {conn_info}] [MerkleCheck Recv] TxIDs for Block {block_obj.Height}: {received_tx_ids_for_merkle_hex}")

                            # --- Calculate Merkle Root ---
                            # Convert hex IDs to bytes
                            tx_ids_bytes = [bytes.fromhex(tx_id) for tx_id in received_tx_ids_for_merkle_hex]

                            # *** IMPORTANT: Pass a COPY to merkle_root if you might reuse tx_ids_bytes ***
                            # Although merkle_root now makes its own copy, being explicit is safer.
                            calculated_merkle_root_bytes = merkle_root(list(tx_ids_bytes)) # Pass a copy

                            # Ensure the result is reversed if needed by your convention
                            # calculated_merkle_root_bytes = calculated_merkle_root_bytes[::-1] # Apply reversal AFTER calculation if needed

                            # --- Compare ---
                            header_merkle_root_bytes = to_bytes_field(header_obj.merkleRoot)

                            logger.debug(f"Calculated Merkle: {calculated_merkle_root_bytes.hex()}")
                            logger.debug(f"Header Merkle:     {header_merkle_root_bytes.hex()}")

                            # --- Apply reversal CONSISTENTLY ---
                            # Option A: Assume both sender and receiver reverse AFTER merkle_root calculation
                            calculated_merkle_root_final = calculated_merkle_root_bytes[::-1]
                            header_merkle_root_final = header_merkle_root_bytes # Assume header already stored reversed if that's the convention

                            # Option B: Assume merkle_root returns in needed format (e.g., already reversed internally if needed)
                            # calculated_merkle_root_final = calculated_merkle_root_bytes
                            # header_merkle_root_final = header_merkle_root_bytes

                            # Choose ONE option for comparison:
                            if calculated_merkle_root_final != header_merkle_root_final:
                                 logger.warning(f"[Handler {conn_info}] REJECTING Block {block_obj.Height}: Merkle root mismatch.")
                                 logger.warning(f"  Calculated (Final): {calculated_merkle_root_final.hex()}")
                                 logger.warning(f"  Header     (Final): {header_merkle_root_final.hex()}")
                                 logger.warning(f"  TxIDs Used for Calc: {received_tx_ids_for_merkle_hex}")
                                 raise ValueError(f"Merkle root mismatch.")

                        except ValueError as ve:
                            raise ve # Re-raise specific errors
                        except Exception as e_mr:
                            # ... (generic error handling) ...
                            raise ValueError("Merkle root calculation/validation failed") from e_mr
                        merkle_end = time.time()
                        logger.debug(f"[Handler {conn_info}] Merkle root validation passed (took {merkle_end - merkle_start:.4f}s).")


                        # --- Block is Valid - Apply to State and DB ---
                        logger.info(f"Block {block_obj.Height} is valid. Applying...")

                        # --- Acquire Lock for Write/State Update ---
                        lock_type = type(self.state_lock)
                        lock_value_repr = repr(self.state_lock) # Use repr for potentially complex objects
                        logger.debug(f"[Handler {conn_info}] Acquiring lock. Type: {lock_type}, Value: {lock_value_repr}")
                        with self.state_lock:
                            # Convert Block OBJECT to DICT for DB
                            try:
                                block_dict_for_db = block_obj.to_dict()
                                # Ensure nested Tx/Header are dicts
                                if block_dict_for_db.get('Txs') and isinstance(block_dict_for_db['Txs'][0], Tx):
                                     block_dict_for_db['Txs'] = [tx.to_dict() for tx in block_dict_for_db['Txs']]
                                if isinstance(block_dict_for_db.get('BlockHeader'), BlockHeader):
                                     block_dict_for_db['BlockHeader'] = block_dict_for_db['BlockHeader'].to_dict()
                            except Exception as e_conv:
                                logger.error(f"Failed to convert valid block {block_obj.Height} to dict: {e_conv}", exc_info=True)
                                raise # Re-raise error, cannot proceed

                            # Write DICT to DB
                            try:
                                self.blockchain.write_on_disk([block_dict_for_db]) # Call blockchain's method
                            except Exception as e_write:
                                logger.error(f"CRITICAL: Failed DB write for valid block {block_obj.Height}: {e_write}. State may become inconsistent.", exc_info=True)
                                raise # Re-raise error, do not update state if DB failed

                            # Update State using the OBJECT
                            self.blockchain.update_utxo_set(block_obj)
                            self.blockchain.clean_mempool(block_obj)

                        # --- Release Lock ---
                        logger.info(f"Block {block_obj.Height} successfully added and state updated.")

                    except ValueError as ve: # Catch specific validation errors
                        height = block_obj.Height if block_obj else 'N/A'
                        logger.warning(f"[Handler] Discarding invalid block Height={height}: {ve}")
                    except Exception as e:
                        height = block_obj.Height if block_obj else 'N/A'
                        logger.error(f"[Handler] Error processing received block Height={height}: {e}", exc_info=True)

                    print(f"[Server Handler {conn_info}] Processed block command.")

            elif envelope.command == requestBlock.command:
                start_block = None
                print(f"[Server Handler {conn_info}] Processing requestBlock command...")
                try:
                    parsed_data = requestBlock.parse(envelope.stream())
                    if isinstance(parsed_data, tuple) and len(parsed_data) >= 1: start_block = parsed_data[0]
                    elif parsed_data is not None: start_block = parsed_data

                    if start_block is not None:
                        start_block_hex = start_block.hex() if isinstance(start_block, bytes) else str(start_block)
                        print(f"[Server Handler {conn_info}] Parsed requestBlock start: {start_block_hex[:10]}...")

                        print(f"[Server Handler {conn_info}] Calling sendBlockToRequestor...")
                        self.sendBlockToRequestor(start_block) # Call with only start_block
                        print(f"[Server Handler {conn_info}] sendBlockToRequestor completed.") # Crucial log
                        return 
                        # Optional: Log if more data was parsed but not used
                        # if len(parsed_data) > 1:
                        #    end_block = parsed_data[1]
                        #    print(f"(End Block provided but not used: {end_block})")
                    else:
                        # --- Add Debug Line ---
                        print(f"[Server Handler {conn_info}] Error: requestBlock.parse returned None/invalid.")
                        if hasattr(self, 'conn') and self.conn: self.conn.close()
                        return
                        # --- End Add Debug Line ---
                        # Consider closing connection here or sending an error response

                except Exception as e_req:
                    # --- Add Debug Line ---
                    print(f"[Server Handler {conn_info}] EXCEPTION processing requestBlock command itself: {e_req}")
                    traceback.print_exc() # Log the specific error
                    if hasattr(self, 'conn') and self.conn: self.conn.close()
                    return # Exit on exception
                     # --- End Add Debug Line ---
        
            if envelope.command == b'valselect':
                # This is the validator node telling a selected node to produce a block.
                print("[syncManager] Received validator selection message.")
                payload = envelope.payload.decode()
                # print('[DEBUG] payload:', payload)
                message = json.loads(payload)
                if message.get("type") == "validator_selection":
                    selected_validator = message["selected_validator"]                   
                    
                    print(f"[DEBUG] Selected validator: {selected_validator}")
                    print(f"[DEBUG] My public address: {self.my_public_addr}")
                    
                    # Get current node's account
                    my_account = None
                    try:
                        from Blockchain.client.account import account
                        my_account = account.get_account(self.my_public_addr)
                    except Exception as e:
                        print(f"Error getting account: {e}")
                        
                    # Compare addresses properly
                    validator_address = None
                    if isinstance(selected_validator, dict) and 'public_addr' in selected_validator:
                        validator_address = selected_validator['public_addr']
                    elif isinstance(selected_validator, str):
                        validator_address = selected_validator
                        
                    # Determine if this node is the validator
                    is_validator = False
                    if my_account and validator_address:
                        is_validator = (my_account.public_addr.strip() == validator_address.strip())
                    elif self.my_public_addr and validator_address:
                        is_validator = (self.my_public_addr.strip() == validator_address.strip())
                        
                    if is_validator:
                        # We are the chosen validator. Produce a block now.
                        print(f"[syncManager] I AM THE SELECTED VALIDATOR! - Address {self.my_public_addr} Producing next block.")

                        # print(f"[syncManager] Blockchain type: {type(self.blockchain)}")
                        
                        # Use the existing blockchain reference to create a block
                        blockchainDB = BlockchainDB()
                        lastBlock = blockchainDB.lastBlock()
                        
                        if lastBlock is None:
                            print(f"[syncManager] Selected as validator, but no local blockchain found. Waiting for Genesis from validator node.")
                            # Do nothing, let the main validator handle Genesis
                        else:
                            # <<< --- EXISTING LOGIC MOVED INSIDE ELSE --- >>>
                            # Chain exists, proceed to create the NEXT block
                            lastBlockDict = lastBlock[0] if isinstance(lastBlock, list) else lastBlock # Handle list wrapper
                            blockHeight = lastBlockDict.get('Height', -1) + 1
                            prevBlockHash = lastBlockDict.get('BlockHeader', {}).get('blockHash', ZERO_HASH)

                            # Optional: Wait briefly
                            print(f"[syncManager] I'm selected as validator. Waiting briefly...")
                            time.sleep(2) # Wait for 2 seconds

                            # Double-check tip
                            blockchainDB = BlockchainDB() # Create another local instance
                            freshLastBlock = blockchainDB.lastBlock()
                            if blockchainDB.conn: blockchainDB.conn.close() # Close connection
                            freshHeight = -1
                            if freshLastBlock:
                                 freshLastBlockDict = freshLastBlock[0] if isinstance(freshLastBlock, list) else freshLastBlock
                                 freshHeight = freshLastBlockDict.get('Height', -1)

                            if freshHeight >= blockHeight:
                                print(f"[syncManager] Chain advanced during wait. Skipping block {blockHeight}.")
                                return # Use return to exit handleConnection for this block

                            # Create the block
                            print(f"[syncManager] Creating block at height {blockHeight}")
                            try:
                                print(f"[syncManager/DEBUG] MEMPOOL CONTENTS: {self.MemoryPool}")
                                self.blockchain.addBlock(blockHeight, prevBlockHash, selected_validator)
                                print(f"[syncManager] Block {blockHeight} creation initiated.")
                            except Exception as e:
                                print(f"[syncManager] Error creating block: {e}")
                                traceback.print_exc()
                                print("[syncManager] Add block failed")

                    else:
                        print(f"[syncManager] Not the selected validator: {validator_address}")

                        
            elif envelope.command == b'account':
                try:
                    # Parse the account update message
                    payload = envelope.payload.decode()
                    message = json.loads(payload)
                    
                    if message.get('type') == 'account_update':
                        address = message.get('address')
                        account_data = message.get('data')
                        sender_port = message.get('sender_port')
                        
                        print(f"Received account update from port {sender_port} for address: {address}")
                        
                        # Update the local database with the received account data         
                        # Create a consistent account object that can be saved to the database
                        account_db = AccountDB()
                        account_db.update_account(address, json.dumps(account_data))
                        
                        print(f"Successfully updated local account database for {address}")
                except Exception as e:
                    print(f"Error processing account update: {e}")
            
            else:
                # --- Add Debug Line ---
                print(f"[Server Handler {conn_info}] Unknown command received: {envelope.command}")
                # --- End Add Debug Line ---

            command_str = envelope.command.decode() if envelope and isinstance(envelope.command, bytes) else str(envelope.command if envelope else 'N/A')
            print(f"[Server Handler {conn_info}] Closing connection after processing command '{command_str}'.")
            self.conn.close()
        except socket.timeout:
             # --- Add Debug Line ---
             print(f"[Server Handler {conn_info}] Socket timeout during read/processing.")
             # --- End Add Debug Line ---
             if hasattr(self, 'conn') and self.conn: self.conn.close()
        except OSError as e_os: # Catch broken pipe etc.
             # --- Add Debug Line ---
             print(f"[Server Handler {conn_info}] OSError during read/processing: {e_os}")
             # --- End Add Debug Line ---
             if hasattr(self, 'conn') and self.conn:
                  try: self.conn.close()
                  except: pass
        except Exception as e:
            # General exception catch for the whole handler
            # --- Add Debug Line ---
            print(f"[Server Handler {conn_info}] UNHANDLED EXCEPTION in handleConnection: {e}")
            traceback.print_exc() # Print full traceback
            # --- End Add Debug Line ---
            if hasattr(self, 'conn') and self.conn:
                 try: self.conn.close()
                 except Exception: pass
        finally:
            # Optional: Add a final log to confirm the handler thread is exiting
            # --- Add Debug Line ---
            print(f"[Server Handler {conn_info}] Thread exiting.")
            # --- End Add Debug Line ---


    def addNode(self):
        nodeDb = NodeDB()
        portList = nodeDb.read_nodes() # Use the correct method
        print(f"Current ports in database: {portList}")

        if hasattr(self, 'addr') and self.addr and len(self.addr) > 1:
            remote_port_int = int(self.addr[1])
            # --- FIX: Only add ports in the expected node range (e.g., 9000+) ---
            potential_node_port = remote_port_int + 1 # Or just remote_port_int if that's the listener
            if potential_node_port >= 9000 and potential_node_port not in portList:
                nodeDb.write(potential_node_port)
                print(f"Added potential node port: {potential_node_port}")
            else:
                print(f"Skipping addNode for port {potential_node_port} (not in range or already exists)")
        else:
            print("[addNode] Could not determine remote address/port.")

    def sendBlockToRequestor(self, start_block):
        blocksToSend = self.fetchBlocksFromBlockchain(start_block)

        try:
            self.sendBlock(blocksToSend)
            self.sendPortList()
            self.sendFinishedMessage()
        except Exception as e:
            print(f"Unable to send the blocks \n {e}")

    def sendPortList(self):
        nodeDB = NodeDB()
        ports = nodeDB.read_nodes()
        if ports is None:
            raise ValueError("No nodes found in the NodeDB.")

        portlist = portList(ports)
        envelope = NetworkEnvelope(portlist.command, portlist.serialise())
        self.conn.sendall(envelope.serialise())
    
    # def sendSecondaryChain(self):
    #     TempSecChain = dict(self.secondaryChain)
    #     for blockHash in TempSecChain:
    #         envelope = NetworkEnvelope(TempSecChain[blockHash].command, TempSecChain[blockHash].serialise())
    #         self.conn.sendall(envelope.serialise())

    def sendFinishedMessage(self):
        MessageFinish = FinishedSending()
        envelope = NetworkEnvelope(MessageFinish.command, MessageFinish.serialise())
        self.conn.sendall(envelope.serialise())
      
    def sendBlock(self, blockstosend):
        for block in blockstosend:
            cblock = Block.to_obj(block)
            envelope = NetworkEnvelope(cblock.command, cblock.serialise())
            self.conn.sendall(envelope.serialise())
            print(f'block sent {cblock.Height}')
    

    def fetchBlocksFromBlockchain(self, start_Block):
        fromBlockOnwards = start_Block.hex()

        blocksToSend = []

        blockchain = BlockchainDB()
        blocks = blockchain.read()

        foundBlock = False
        for block in blocks:
            if block[0]['BlockHeader']['blockHash'] == fromBlockOnwards:
                foundBlock = True
                continue

            if foundBlock:
                blocksToSend.append(block)

        return blocksToSend
    
    # def connectToHost(self, localport_arg, target_port_arg, bindPort_flag): 
    #     """
    #     Connects to a target host and port.
    #     MINIMAL CHANGE: Adapts arguments to match the internal logic of the existing Node.connect method.
    #     - localport_arg: The local port number to bind IF bindPort_flag is True.
    #     - target_port_arg: The port number of the peer to connect to.
    #     - bindPort_flag: Boolean or similar, indicates if binding is required. If True/non-None, Node.connect's second arg will be non-None.
    #     """
    #     # Create Node instance for the TARGET port
    #     self.connect = Node(self.host, target_port_arg) # Node instance represents the connection TARGET

    #     if bindPort_flag:
    #          # Node.connect needs the LOCAL BIND PORT as its FIRST argument ('port')
    #          # and something non-None as its SECOND argument ('bindPort') to trigger binding.
    #         print(f"Binding requested. Calling Node.connect({localport_arg}, {bindPort_flag}) to bind locally and connect to {target_port_arg}...")
    #         self.socket = self.connect.connect(localport_arg, bindPort_flag) # Pass LOCAL port first, flag second
    #         print(f"Connected from local port {localport_arg} to target {target_port_arg}")
    #     else:
    #         # No binding requested. Call Node.connect with only one arg.
    #         # The value passed doesn't matter much for the connect() call itself inside Node.connect,
    #         # as it uses self.port (target_port_arg) for the actual connection.
    #         # Pass the local port arg anyway, consistent with the bind case.
    #         print(f"No binding. Calling Node.connect({localport_arg}) to connect to {target_port_arg}...")
    #         self.socket = self.connect.connect(localport_arg) # Pass only one arg (bindPort=None)
    #         print(f"Connected from OS-assigned local port to target {target_port_arg}")

    #     # Set up the stream for reading/writing
    #     self.stream = self.socket.makefile('rb', None)
    #     self.connect.stream = self.stream
    #     return self.socket, self.connect

    def connectToHost(self, localport_arg, target_port_arg, bindPort_flag):
        """
        Connects to a target host and port using the Node class.
        Returns (socket, connector_node) on success, (None, None) on failure.
        """
        # Create Node instance for the TARGET port
        # Use 'connector_node' locally instead of self.connect to avoid confusion
        connector_node = Node(self.host, target_port_arg) # Node instance represents the connection TARGET

        connected_socket = None # Initialize socket variable

        try:
            if bindPort_flag:
                # Node.connect needs the LOCAL BIND PORT as its FIRST argument ('port')
                # and something non-None as its SECOND argument ('bindPort') to trigger binding.
                logger.debug(f"[connectToHost] Binding requested. Calling Node.connect({localport_arg}, {bindPort_flag}) to bind locally and connect to {target_port_arg}...")
                # Call Node.connect on the specific connector_node instance
                connected_socket = connector_node.connect(localport_arg, bindPort_flag) # Pass LOCAL port first, flag second
            else:
                # No binding requested. Call Node.connect with only one arg.
                logger.debug(f"[connectToHost] No binding. Calling Node.connect({localport_arg}) to connect to {target_port_arg}...")
                # Call Node.connect on the specific connector_node instance
                connected_socket = connector_node.connect(localport_arg) # Pass only one arg (bindPort=None)

            # ====================================================
            # === CRITICAL FIX: CHECK IF CONNECTION SUCCEEDED ===
            # ====================================================
            if connected_socket:
                # Connection succeeded, Node.connect should have set connector_node.stream
                # Double-check just in case (though improved Node.connect should handle it)
                if not connector_node.stream:
                    logger.warning("[connectToHost] Node.connect succeeded but stream not set. Creating stream.")
                    try:
                        # Create stream on the connector_node object
                        connector_node.stream = connected_socket.makefile('rb', buffering=0)
                    except Exception as e_stream:
                        logger.error(f"[connectToHost] Failed to create stream even after successful connect: {e_stream}")
                        connector_node.closeConnection() # Clean up the partially successful connection
                        return None, None # Return failure

                logger.info(f"[connectToHost] Successfully connected to {target_port_arg}.")
                # Return the raw socket AND the Node instance managing it
                return connected_socket, connector_node
            else:
                # Connection failed, Node.connect returned None
                # Node.connect should have logged the specific error already
                logger.error(f"[connectToHost] Failed to connect to {target_port_arg} (Node.connect returned None).")
                return None, None # Return failure
            # ====================================================

        # Catch unexpected errors during the connectToHost logic itself
        except Exception as e:
            logger.error(f"[connectToHost] Unexpected error during connection attempt to {target_port_arg}: {e}", exc_info=True)
            # Ensure cleanup if socket/node partially created
            if connected_socket:
                 try: connected_socket.close()
                 except: pass
            if connector_node:
                 # Use the Node's cleanup method
                 connector_node.closeConnection()
            return None, None # Return failure

    # def connectToHost(self, local_port_to_bind, target_port, bind_flag):
    #     """
    #     Establishes an OUTGOING connection to a target peer.
    #     Manages the creation and use of a Node object for the connection.

    #     Args:
    #         local_port_to_bind: The local port to bind to IF bind_flag is True.
    #         target_port: The port of the peer to connect to.
    #         bind_flag: Boolean indicating if local binding is required.

    #     Returns:
    #         tuple: (connected_socket, connector_node_instance) on success, (None, None) on failure.
    #     """
    #     logger.debug(f"Attempting connection to target={target_port} from bind_port={local_port_to_bind if bind_flag else 'OS-assigned'}...")

    #     # --- Create a NEW Node instance for this connection attempt ---
    #     # Pass the TARGET host/port for clarity, though connect() uses args primarily
    #     connector_node = Node(self.host, target_port) # Represents the connection attempt

    #     connected_socket = None
    #     try:
    #         # --- Call the connect method ON the new Node instance ---
    #         if bind_flag:
    #             # Pass target_port and the local bind port
    #             logger.debug(f"Calling connector_node.connect(port={target_port}, bindPort={local_port_to_bind})")
    #             connected_socket = connector_node.connect(port=target_port, bindPort=local_port_to_bind)
    #         else:
    #             # Pass target_port, bindPort will be None by default
    #             logger.debug(f"Calling connector_node.connect(port={target_port})")
    #             connected_socket = connector_node.connect(port=target_port) # bindPort is implicitly None

    #         # --- Check if connect method returned a socket ---
    #         if connected_socket:
    #             # IMPORTANT: Ensure Node.connect ALSO created connector_node.stream
    #             # If not, you need to add it here:
    #             if not hasattr(connector_node, 'stream') or not connector_node.stream:
    #                 logger.warning("Node.connect did not create stream, creating it now.")
    #                 connector_node.stream = connected_socket.makefile('rb', buffering=0)
    #                 # You might also need connector_node.write_stream if using separate write streams

    #             logger.info(f"Connection to {target_port} successful.")
    #             # Return BOTH the raw socket AND the Node object managing it
    #             return connected_socket, connector_node
    #         else:
    #             # Node.connect failed and returned None
    #             logger.warning(f"connector_node.connect failed for target {target_port}.")
    #             return None, None

    #     except Exception as e:
    #         # Catch any unexpected errors during the connect call itself
    #         logger.error(f"Unexpected error during connectToHost for target {target_port}: {e}", exc_info=True)
    #         # Ensure cleanup if connector_node was created but connection failed
    #         if connector_node and connector_node.socket:
    #             connector_node.close_client_socket() # Use appropriate close method
    #         return None, None


    # def publishTx(self, tx_obj):
    #     try:
    #         # Use connectToHost to get a socket (binding from self.localHostPort if needed)
    #         sock = self.connectToHost(self.localHostPort, self.port)
    #         # Wrap the transaction in a NetworkEnvelope
    #         envelope = NetworkEnvelope(tx_obj.command, tx_obj.serialise())
    #         sock.sendall(envelope.serialise())
    #         sock.close()
    #         print(f"Published Tx {tx_obj.TxId} to {self.host}:{self.port}")
    #     except Exception as e:
    #         print(f"Error publishing Tx to port {self.port}: {e}")

    def publishTx(self, tx_obj):
        logger = logging.getLogger(__name__) # Use logger
        try:
            # --- FIX TypeError Robustly ---
            # Determine the local port argument for connectToHost.
            # For simple outgoing connections (publishing), we typically don't need a specific local port.
            # Using 0 lets the OS choose an ephemeral port.
            local_port_arg = 0
            if self.localHostPort is not None:
                # Even if set, using 0 for outgoing is generally fine and avoids potential conflicts.
                logger.debug(f"self.localHostPort is {self.localHostPort}, using 0 for outgoing connection local port arg.")
                local_port_arg = 0 # Stick with 0 for simplicity/robustness
            else:
                logger.warning(f"self.localHostPort is None in publishTx. Using 0 for local port arg.")
                local_port_arg = 0

            # Target port is self.port (port of the peer we want to send to)
            target_port = self.port
            # We are not binding the local port when just publishing
            bind_flag = False

            logger.debug(f"Calling connectToHost with: localport_arg={local_port_arg}, target_port_arg={target_port}, bindPort_flag={bind_flag}")
            sock, connector = self.connectToHost(local_port_arg, target_port, bind_flag)
            # --- END FIX ---

            if not sock or not connector:
                logger.error(f"Failed to connect to {self.host}:{target_port} for publishing Tx.")
                return

            # Use the connector object returned by connectToHost to send
            connector.send(tx_obj)
            logger.info(f"Published Tx {tx_obj.TxId} to {self.host}:{target_port}") # Log target port

        except Exception as e:
            # Log the full error trace for debugging
            logger.error(f"Error publishing Tx to target port {self.port}: {e}", exc_info=True)


    # def publishTx(self, tx_obj):
    #     try:
    #         # --- FIX: Call connectToHost with 3 arguments ---
    #         # Use self.localHostPort for binding if needed, or 0 for OS assigned. Let's assume no bind needed.
    #         sock, connector = self.connectToHost(self.localHostPort - 1000, self.port, False) # Example: no bind
    #         # --- END FIX ---
    #         if not sock or not connector:
    #             print(f"Failed to connect to {self.host}:{self.port} for publishing Tx.")
    #             return

    #         connector.send(tx_obj) # Use connector to send
    #         print(f"Published Tx {tx_obj.TxId} to {self.host}:{self.port}") # Use self.port
    #     except Exception as e:
    #         print(f"Error publishing Tx to port {self.port}: {e}") # Use self.port
        
    # def publishBlock(self, localport, port, block):
    #     # print(f"[Debug] publish block printing: {block.__dict__}")
    #     self.connectToHost(localport, port)
    #     print('Connected to host')
    #     # print(f"[Sender] Sending block {block.Height} with hash {block.BlockHeader.blockHash} and size {len(block_bytes)} bytes")
    #     self.connect.send(block)

    def publishBlock(self, localport, port, block):
        # --- FIX: Call connectToHost with 3 arguments ---
        # Pass False for the bindPort_flag as binding is not needed here
        sock, connector = self.connectToHost(localport, port, False)
        # --- END FIX ---

        if not sock or not connector:
            print(f"Failed to connect to host {self.host}:{port} for publishing block.")
            return

        print(f'Connected to host {self.host}:{port}') # Use self.host
        try:
            # Use the connector (Node object) to send
            connector.send(block)
            print(f"Published block {block.Height} to {self.host}:{port}")
        except Exception as e:
            print(f"Error sending block to {self.host}:{port}: {e}")

    # def publish_account_update(self, sender_port, receiver_port, address, account_data):
    #     """Send account updates to other nodes"""
    #     try:
    #         print(f"Publishing account update for {address} to node at port {receiver_port}")
            
    #         # Connect to the target node
    #         self.connectToHost(sender_port, receiver_port)
    #         print(f"Connected to host at port {receiver_port}")
            
    #         # Create a properly formatted message object
    #         from Blockchain.Backend.core.network.network import AccountUpdateMessage
    #         msg = AccountUpdateMessage(sender_port, address, account_data)
            
    #         # Send exactly like you send blocks
    #         self.connect.send(msg)
    #         print(f"Account update for {address} sent to port {receiver_port}")
    #         return True
    #     except Exception as e:
    #         print(f"Error in publish_account_update: {e}")
    #         import traceback
    #         traceback.print_exc()
    #         return False


    def publish_account_update(self, sender_port, receiver_port, address, account_data):
        """Send account updates to other nodes"""
        sock, connector = None, None # Initialize
        try:
            print(f"Publishing account update for {address} to node at port {receiver_port}")

            # --- FIX: Call connectToHost with 3 arguments ---
            # Binding is usually not required for sending updates
            sock, connector = self.connectToHost(sender_port -1000, receiver_port, False) # Example: no bind
             # --- END FIX ---

            if not sock or not connector:
                 print(f"Failed to connect to host {self.host}:{receiver_port} for account update.")
                 return False

            print(f"Connected to host {self.host}:{receiver_port}") # Use self.host

            # Create a properly formatted message object
            from Blockchain.Backend.core.network.network import AccountUpdateMessage
            msg = AccountUpdateMessage(sender_port, address, account_data)

            # Send using the connector object
            connector.send(msg)
            print(f"Account update for {address} sent to port {receiver_port}")
            return True
        except Exception as e:
            print(f"Error in publish_account_update: {e}")
            import traceback
            traceback.print_exc()
            return False
        

    def startDownload(self, localport_to_bind, target_port, bind_needed_flag):
        """
        Initiates block download from a peer, validates blocks, updates local DB and state.
        """
        logger.info(f"[Downloader] Starting download from {localport_to_bind} :{target_port}...")

        # --- Determine Start Hash ---
        startBlockBytes = bytes.fromhex(ZERO_HASH) # Default to Genesis
        local_db_for_tip = None
        acquired_lock = False
        acquired_block_lock = False
        try:
            local_db_for_tip = BlockchainDB()
            # --- Explicitly acquire lock ---
            self.state_lock.acquire()
            acquired_lock = True
            lastBlockDict = local_db_for_tip.lastBlock()
            # --- Explicitly release lock ---
            self.state_lock.release()
            acquired_lock = False
            if lastBlockDict:
                # Handle potential list wrapping from DB read
                lastBlockDict = lastBlockDict[0] if isinstance(lastBlockDict, list) else lastBlockDict
                lastBlockHashHex = lastBlockDict.get('BlockHeader', {}).get('blockHash', ZERO_HASH)
                # Validate hex string before conversion
                if lastBlockHashHex and len(lastBlockHashHex) == 64:
                     try:
                         startBlockBytes = bytes.fromhex(lastBlockHashHex)
                         logger.info(f"[Downloader] Requesting blocks after local tip: {lastBlockHashHex[:8]}...")
                     except ValueError:
                         logger.error(f"Invalid hex for last block hash: {lastBlockHashHex}. Requesting from Genesis.")
                         startBlockBytes = bytes.fromhex(ZERO_HASH)
                else:
                     logger.warning(f"Could not read valid last block hash. Requesting from Genesis.")
                     startBlockBytes = bytes.fromhex(ZERO_HASH)
            else:
                logger.info("[Downloader] No local blocks found. Requesting from Genesis.")
        except Exception as e:
            logger.error(f"Error getting last block for download start: {e}", exc_info=True)
            startBlockBytes = bytes.fromhex(ZERO_HASH) # Fallback
        finally:
            # Explicitly close the connection used only for the tip check
            if acquired_lock: self.state_lock.release()
            # Close DB connection used for tip check
            if local_db_for_tip and local_db_for_tip.conn:
                try: local_db_for_tip.conn.close()
                except Exception as e_close: logger.warning(f"Error closing DB conn after tip check: {e_close}")
        # --- End Start Hash Determination ---

        getBlocksRequest = requestBlock(startBlock=startBlockBytes)
        sock, connector = None, None
        acquired_block_lock = False
        try:
            # Connect (use localHostPort for binding if provided)
            logger.debug(f"Calling connector.connect(bindPort={self.localHostPort})") # Log before call
            sock, connector = self.connectToHost(localport_to_bind, target_port, bind_needed_flag)
            if not sock or not connector: return # Connection failed

            connector.send(getBlocksRequest) # Use Node's send method
            logger.info(f"[Downloader] Sent requestBlock to {localport_to_bind}:{target_port}")

            # Loop to receive blocks/messages using Node's read method
            while True:
                envelope = connector.read(timeout=30.0)
                if envelope is None: # Connection closed or error during read
                    if not connector.socket or connector.socket.fileno() < 0: # Check if socket closed
                        logger.warning(f"[Downloader] Connection to {target_port} appears closed after read returned None.")
                        break # Exit loop, connection is gone
                    else:
                        logger.warning(f"[Downloader {target_port}] Read timed out. Peer might be slow or finished sending without 'Finished' msg?")
                        # Decide: break here, or continue waiting? Continuing risks infinite loop if peer died.
                        # Let's break after a timeout for simplicity now.
                        logger.warning(f"[Downloader {target_port}] Assuming download finished or stalled after timeout.")
                        break # Exit loop after timeou

                logger.debug(f"[Downloader {target_port}] Received command: {envelope.command}")

                if envelope.command == FinishedSending.command:
                    logger.info(f"[Downloader {target_port}] Received FinishedSending. Download complete.")
                    break # Finished download loop

                elif envelope.command == portList.command:
                    try:
                        ports = portList.parse(envelope.stream())
                        logger.info(f"[Downloader {target_port}] Received portlist: {ports}")
                        nodedb_instance = NodeDB() # Local instance for this check
                        if nodedb_instance: # Ensure node_db is available
                            current_nodes = nodedb_instance.read_nodes() or []
                            added_count = 0
                            for p in ports:
                                if p != self.localHostPort and p not in current_nodes:
                                    nodedb_instance.write(p)
                                    added_count += 1
                            if added_count > 0:
                                logger.info(f"[Downloader {target_port}] Added {added_count} new peer(s).")
                    except Exception as e: logger.error(f"Error processing portlist: {e}", exc_info=True)

                elif envelope.command == Block.command:
                    # --- PROCESS BLOCK DIRECTLY ---
                    block_obj = None
                    db_instance_check = None # Define here for finally block
                    try:
                        block_obj = Block.parse(envelope.stream())
                        block_height = block_obj.Height # Get height early
                        logger.info(f"[Downloader {target_port}] Received Block: Height={block_height}")

                        # --- Acquire Lock for validation against tip and potential update ---
                        self.state_lock.acquire()
                        acquired_block_lock = True
                        # --- START VALIDATION (under lock) ---
                        header_obj = block_obj.BlockHeader

                        # 1. Calculate and Store Block Hash
                        try:
                            # Ensure header fields are bytes
                            header_obj.prevBlockHash = to_bytes_field(header_obj.prevBlockHash)
                            header_obj.merkleRoot = to_bytes_field(header_obj.merkleRoot)
                            header_obj.validator_pubkey = to_bytes_field(header_obj.validator_pubkey)
                            # Parse signature if needed
                            sig_field = header_obj.signature
                            if sig_field and not isinstance(sig_field, Signature):
                                try: header_obj.signature = Signature.parse(sig_field)
                                except Exception as e: raise ValueError(f"Invalid sig parse: {e}")
                            elif not sig_field: raise ValueError("Missing signature")
                            # Calculate and store
                            block_hash_hex = header_obj.generateBlockHash()
                            header_obj.blockHash = block_hash_hex
                            logger.debug(f"[Downloader] Calculated hash {block_hash_hex[:8]} for block {block_height}")
                        except Exception as e_hash: raise ValueError(f"Block hash calc failed: {e_hash}")

                        # 1.5 Check if block already exists (using calculated hash)
                        # db_instance_check = BlockchainDB() # Local instance for this check
                        # try:
                        #         if db_instance_check.read_block_by_hash(block_hash_hex):
                        #             logger.info(f"[Downloader] Block {block_height} ({block_hash_hex[:8]}) already exists. Skipping.")
                        #             continue # Skip to next message in loop
                        # finally:
                        #         if db_instance_check.conn: db_instance_check.conn.close()
                        #             # Release lock BEFORE continuing outer loop
                        #             if acquired_block_lock:
                        #                 logger.debug(f"[Downloader {target_port}] Releasing lock for already existing block {block_height}.")
                        #                 self.state_lock.release()
                        #                 acquired_block_lock = False # Mark lock as released
                        #             continue # Skip rest of processing for this block, read next message

                        block_already_exists = False # <<< ADD Flag before the check
                        db_instance_check = BlockchainDB() # Local instance for this check
                        try:
                            # Check the database for the block hash
                            if db_instance_check.read_block_by_hash(block_hash_hex):
                                logger.info(f"[Downloader] Block {block_height} ({block_hash_hex[:8]}) already exists. Will skip further processing.")
                                block_already_exists = True # <<< SET Flag instead of continue
                        finally:
                            # Always close the specific DB connection used for the check
                            if db_instance_check.conn:
                                try:
                                     db_instance_check.conn.close()
                                except Exception as e_db_close:
                                     logger.warning(f"[Downloader] Error closing DB connection for exists check: {e_db_close}")

                        # --- Now, check the flag AFTER the try...finally block ---
                        if block_already_exists:
                            logger.debug(f"[Downloader {target_port}] Detected block {block_height} already exists. Releasing lock and continuing loop.")
                            # Release the MAIN lock acquired for block processing
                            # This lock was acquired *before* this check section
                            if acquired_block_lock:
                                self.state_lock.release()
                                acquired_block_lock = False # Mark lock as released
                            # Use continue to skip to the next iteration of the OUTER while True loop
                            continue # <<< CORRECT placement of continue

                        # --- Block does not exist, continue validation (still under lock) ---
                        # (The rest of your validation logic: check tip, internal valid, Merkle)
                        logger.debug(f"[Downloader {target_port}] Block {block_height} doesn't exist locally. Proceeding with validation...")

                        # 2. Check against Local Chain Tip
                        db_instance_check = BlockchainDB() # New instance for fresh tip read
                        try:
                                last_block_dict = db_instance_check.lastBlock()
                        finally:
                                if db_instance_check.conn: db_instance_check.conn.close()
                        current_height = -1; tip_hash = ZERO_HASH
                        if last_block_dict:
                            last_block_dict = last_block_dict[0] if isinstance(last_block_dict, list) else last_block_dict
                            current_height = last_block_dict.get('Height', -1)
                            tip_hash = last_block_dict.get('BlockHeader', {}).get('blockHash', ZERO_HASH)

                        prev_hash_bytes = to_bytes_field(header_obj.prevBlockHash)
                        prev_hash_hex = prev_hash_bytes.hex()
                        if block_height != current_height + 1: raise ValueError(f"Invalid height. Tip {current_height}, got {block_height}")
                        if prev_hash_hex != tip_hash: raise ValueError(f"Invalid prevHash. Tip {tip_hash[:8]}, got {prev_hash_hex[:8]}")

                        # 3. Internal Validation
                        if not header_obj.validate_block(): raise ValueError("Internal validation failed (sig/content)")

                        # 4. Merkle Root Check
                        try:
                            tx_ids_bytes = [bytes.fromhex(tx.id()) for tx in block_obj.Txs]
                            calculated_merkle_root = merkle_root(tx_ids_bytes)[::-1]
                            header_merkle_root = to_bytes_field(header_obj.merkleRoot)
                            if calculated_merkle_root != header_merkle_root: raise ValueError("Merkle root mismatch")
                        except Exception as e_mr: raise ValueError(f"Merkle validation failed: {e_mr}")
                        # --- END VALIDATION ---

                        # --- Block is Valid - Apply State and DB (still under lock) ---
                        logger.info(f"[Downloader] Block {block_height} is valid. Applying...")
                        block_dict_for_db = block_obj.to_dict()
                        # (Ensure nested conversion)
                        if block_dict_for_db.get('Txs') and isinstance(block_dict_for_db['Txs'][0], Tx): block_dict_for_db['Txs'] = [tx.to_dict() for tx in block_dict_for_db['Txs']]
                        if isinstance(block_dict_for_db.get('BlockHeader'), BlockHeader): block_dict_for_db['BlockHeader'] = block_dict_for_db['BlockHeader'].to_dict()

                        # Write DICT via Blockchain method (creates its own connection)
                        self.blockchain.write_on_disk([block_dict_for_db])

                        # Update State using OBJECT
                        self.blockchain.update_utxo_set(block_obj)
                        self.blockchain.clean_mempool(block_obj)

                    
                        logger.info(f"[Downloader] Block {block_height} successfully added.")

                    except ValueError as ve:
                        height = block_obj.Height if block_obj else 'N/A'
                        logger.warning(f"[Downloader {target_port}] Discarding invalid block Height={height}: {ve}")
                        break
                    except Exception as e:
                        height = block_obj.Height if block_obj else 'N/A'
                        logger.error(f"[Downloader {target_port}] Error processing downloaded block Height={height}: {e}", exc_info=True)
                        break
                    finally:
                        # --- Release lock for this block ---
                        if acquired_block_lock:
                            self.state_lock.release()
                            acquired_block_lock = False
                        # Close DB connection if opened
                        if db_instance_check and db_instance_check.conn:
                             try: db_instance_check.conn.close()
                             except: pass
                     # --- END PROCESS BLOCK DIRECTLY ---

                else:
                    logger.warning(f"[Downloader {target_port}] Ignoring unknown command: {envelope.command}")

        except ConnectionRefusedError: logger.warning(f"Connection refused by {localport_to_bind}:{target_port}.")
        except Exception as e: logger.error(f"Error during download from {localport_to_bind}:{target_port}: {e}", exc_info=True)
        finally:
            # Ensure lock is released if exception happened before finally block in loop
            if acquired_block_lock: self.state_lock.release()
            logger.info(f"[Downloader] Connection to {localport_to_bind}:{target_port} closed.")

def to_bytes_field(field):
        if isinstance(field, bytes):
            return field
        elif isinstance(field, str):
            try:
                return bytes.fromhex(field)
            except Exception as e:
                # If not valid hex, fallback to UTF-8 encoding (adjust if needed)
                return field.encode('utf-8')
        else:
            raise TypeError("Expected field to be str or bytes")