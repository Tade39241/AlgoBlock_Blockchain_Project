import os
import socket
import sys
import time
from io import BytesIO
from threading import Thread
import traceback
import logging # Use logging

# Import necessary components (adjust paths if needed)
from Blockchain.Backend.core.network.connection import Node
from Blockchain.Backend.core.database.db import BlockchainDB, NodeDB
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.core.network.network import requestBlock, NetworkEnvelope, FinishedSending, portList
from Blockchain.Backend.core.Tx import Tx
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.util.util import little_endian_to_int, int_to_little_endian, read_varint # Add read_varint if needed by Block.parse

# Setup logger
logger = logging.getLogger(__name__)

# --- Logging Configuration ---

# Define log format
log_formatter = logging.Formatter('%(message)s')

# Get the root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG) # Set level to DEBUG to see syncManager logs

# --- Console Handler ---
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

# --- File Handler (Modified Path) ---
# Set the desired directory path
log_dir = 'blockchain_code/Blockchain/Backend/core/network' # <--- MODIFIED PATH
# Create the directory if it doesn't exist
os.makedirs(log_dir, exist_ok=True)
# Define the log file name within that directory
log_file = os.path.join(log_dir, 'network.log') # <--- Log file name

file_handler = logging.FileHandler(log_file, mode='a') # 'a' for append
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

# --- End Logging Configuration ---

ZERO_HASH = b'\x00' * 32 # Standard 32-byte zero hash

class syncManager:
    """
    Manages network synchronization (listening, connecting, message handling)
    for a PoW blockchain node in a thread-safe manner.
    """
    def __init__(self, host, port, MemoryPool, blockchain=None, localHostPort=None, newBlockAvailable=None, secondaryChain=None, node_id=None, db_path=None,my_public_addr=None):
        """
        Initializes the sync manager.

        Args:
            host (str): The host address to bind the server to.
            port (int): The port to bind the server to.
            MemoryPool (dict): Shared dictionary for pending transactions.
            blockchain (Blockchain, optional): Reference to the main blockchain object. Defaults to None.
            localHostPort (int, optional): The listening port of this node. Defaults to None.
            newBlockAvailable (dict, optional): Shared dictionary for newly received blocks. Defaults to None.
            secondaryChain (dict, optional): Shared dictionary for orphan blocks. Defaults to None.
            node_id (str, optional): Unique identifier for this node. Defaults to None.
            db_path (str, optional): Path to the blockchain database file. Defaults to None.
        """
        self.host = host
        self.port = port
        self.blockchain = blockchain # Reference to the main Blockchain object
        # Shared dictionary for newly received blocks (passed from main process)
        self.newBlockAvailable = {} if newBlockAvailable is None else newBlockAvailable
        # Shared dictionary for orphan blocks (passed from main process)
        self.secondaryChain = {} if secondaryChain is None else secondaryChain
        # Shared dictionary for mempool (passed from main process)
        self.MemoryPool = {} if MemoryPool is None else MemoryPool
        self.localHostPort = localHostPort # This node's listening port
        self.node_id = node_id  # This node's unique ID
        # Path to the database, potentially derived from blockchain object or passed directly
        self.db_path = db_path or getattr(blockchain, 'db_path', f'blockchain_{node_id}.db' if node_id else 'blockchain.db')
        
        self.server = None # Server socket object
        self.peers = {} # Dictionary to track active connections { (host, port): Node_instance }
        self.my_public_addr = my_public_addr # Store the public address
        logger.info(f"[SyncManager Init {self.node_id}] Initialized. Listening on {host}:{port}. DB: {self.db_path}")
        # Add NodeDB initialization if needed immediately
        try:
            self.node_db = NodeDB(node_id=self.node_id)
            logger.info(f"[SyncManager Init {self.node_id}] NodeDB initialized.")
        except Exception as e:
            logger.error(f"[SyncManager Init {self.node_id}] Failed to initialize NodeDB: {e}")
            self.node_db = None

    def spinUpServer(self):
        """Initializes and starts the node's listening server."""
        if self.server:
            logger.warning(f"[Node {self.node_id} Server] Server already running.")
            return

        try:
            self.server = Node(self.host, self.port)
            self.server.startServer() # Binds the socket and starts listening
            logger.info(f"[Node {self.node_id} Server] SERVER STARTED. LISTENING at {self.host}:{self.port}")

            # Main server loop: Accept connections and spawn handler threads
            while True:
                try:
                    conn, addr = self.server.acceptConnection()
                    logger.info(f"[Node {self.node_id} Server] Accepted connection from {addr}")
                    # Pass conn and addr explicitly to the handler thread
                    handleConn = Thread(target=self.handleConnection, args=(conn, addr), daemon=True) # Use daemon threads
                    handleConn.start()
                except OSError as e:
                     # Handle cases where the socket might be closed during shutdown
                     logger.warning(f"[Node {self.node_id} Server] Error accepting connection (OSError): {e}. Server might be shutting down.")
                     break # Exit the loop if the server socket is likely closed
                except Exception as e:
                     logger.error(f"[Node {self.node_id} Server] Error accepting connection: {e}", exc_info=True)
                     # Decide if the loop should continue or break on other errors

        except Exception as e:
            logger.error(f"[Node {self.node_id} Server] Failed to start server: {e}", exc_info=True)
        finally:
            logger.info(f"[Node {self.node_id} Server] Server loop finished.")
            if self.server:
                self.server.close() # Ensure server socket is closed on exit
                self.server = None

    def handleConnection(self, conn, addr): # Accept conn and addr as arguments
        """Handles an incoming connection from a peer."""
        current_conn = conn
        current_addr = addr
        logger.info(f"[Node {self.node_id} Handler {current_addr}] Handling connection...")

        # --- PORTCHECK MAGIC HANDLING ---
        try:
            # Peek at the first 9 bytes to check for port check magic
            portcheck_magic = current_conn.recv(9, socket.MSG_PEEK)
            if portcheck_magic == b'PORTCHECK':
                current_conn.recv(9)  # Consume the bytes
                logger.info(f"[Node {self.node_id} Handler {current_addr}] Received port check magic, closing.")
                # No return here, close in finally
        except ConnectionResetError:
             logger.warning(f"[Node {self.node_id} Handler {current_addr}] Connection reset during port check.")
             # No return here, close in finally
        except Exception as e:
            logger.error(f"[Node {self.node_id} Handler {current_addr}] Error checking for port check magic: {e}")
            # No return here, close in finally
        # --- END PORTCHECK MAGIC HANDLING ---

        # If port check was received, we still hit the finally block to close
        if portcheck_magic == b'PORTCHECK':
             pass # Proceed to finally block for closing
        else:
            # --- Process Actual Messages ---
            try:
                # Read the next message envelope from the connection
                 # --- ADD LOGGING BEFORE PARSE ---
                logger.debug(f"[Node {self.node_id} Handler {current_addr}] Attempting to parse NetworkEnvelope...")
                # --- END LOGGING ---
                envelope = NetworkEnvelope.parse(current_conn.makefile('rb', None))
                # --- ADD LOGGING AFTER PARSE ---
                logger.debug(f"[Node {self.node_id} Handler {current_addr}] Successfully parsed envelope. Command: {envelope.command}, Payload len: {len(envelope.payload)}")
                # --- END LOGGING ---
                
                # --- Process based on command ---
                if envelope.command == b'tx':
                    # --- ADD LOGGING BEFORE TX PARSE ---
                    logger.debug(f"[Node {self.node_id} Handler {current_addr}] Attempting to parse Tx from payload...")
                    # --- END LOGGING ---
                    tx = Tx.parse(envelope.stream())
                    tx_id = tx.id() # Calculate ID
                    # --- ADD LOGGING AFTER TX PARSE ---
                    logger.debug(f"[Node {self.node_id} Handler {current_addr}] Successfully parsed Tx: {tx_id[:8]}")
                    # --- END LOGGING ---
                    logger.info(f"[Node {self.node_id} Handler {current_addr}] Transaction Received: {tx_id[:8]}...")
                    self.MemoryPool[tx_id] = tx
                    # --- ADD LOGGING AFTER MEMPOOL ADD ---
                    logger.debug(f"[Node {self.node_id} Handler {current_addr}] Added Tx {tx_id[:8]} to MemoryPool. Pool size: {len(self.MemoryPool)}")
                    # --- END LOGGING ---


                elif envelope.command == b'block':
                    blk = Block.parse(envelope.stream())
                    # Calculate the block hash from the header object
                    # Ensure generateBlockHash exists and works on the parsed header
                    h = blk.BlockHeader.generateBlockHash()
                    logger.info(f"[Node {self.node_id} Handler {current_addr}] Block Received: Height={blk.Height}, Hash={h[:8]}...")
                    # Store the Block OBJECT in the shared newBlockAvailable dictionary
                    self.newBlockAvailable[h] = blk

                elif envelope.command == requestBlock.command:
                    start_block_hash, end_block_hash = requestBlock.parse(envelope.stream()) # Assuming it returns start and end
                    logger.info(f"[Node {self.node_id} Handler {current_addr}] Received requestBlock after: {start_block_hash[:8]}...")
                    # Delegate sending blocks back to the requestor
                    # Pass the connection object to the sending method
                    self.sendBlockToRequestor(start_block_hash, current_conn)

                elif envelope.command == portList.command:
                    try:
                        ports = portList.parse(envelope.stream())
                        logger.info(f"[Node {self.node_id} Handler {current_addr}] Received portlist: {ports}")
                        if self.node_db:
                            added_count = 0
                            current_nodes = self.node_db.read_nodes() or []
                            for p in ports:
                                if p != self.localHostPort and p not in current_nodes:
                                    self.node_db.write(p)
                                    added_count += 1
                            if added_count > 0:
                                logger.info(f"[Node {self.node_id} Handler {current_addr}] Added {added_count} new peer(s) from received list.")
                        else:
                            logger.warning(f"[Node {self.node_id} Handler {current_addr}] NodeDB not available, cannot process received portlist.")
                    except Exception as e_pl:
                        logger.error(f"[Node {self.node_id} Handler {current_addr}] Error processing received portlist: {e_pl}", exc_info=True)

                else:
                    logger.warning(f"[Node {self.node_id} Handler {current_addr}] Ignoring unknown command: {envelope.command}")

            except EOFError:
                 logger.info(f"[Node {self.node_id} Handler {current_addr}] Connection closed by peer (EOF).")
            except ConnectionResetError:
                 logger.warning(f"[Node {self.node_id} Handler {current_addr}] Connection reset by peer.")
            except Exception as e:
                logger.error(f"[Node {self.node_id} Handler {current_addr}] Error processing message: {e}", exc_info=True)

        # Ensure connection is closed at the end
            finally:
                try:
                    logger.info(f"[Node {self.node_id} Handler {current_addr}] Closing connection.")
                    current_conn.close()
                except Exception as e_close:
                    logger.error(f"[Node {self.node_id} Handler {current_addr}] Error closing connection: {e_close}")

    def addNode(self, peer_port): # Accept peer_port as argument
        """Adds the peer's port to the NodeDB if not already present."""
        if not self.node_db:
            logger.warning(f"[Node {self.node_id} addNode] NodeDB not available, cannot add peer port {peer_port}.")
            return
        try:
            portList = self.node_db.read_nodes() # Read known ports
            # Ensure portList is a list (read_nodes might return None or other)
            if portList is None:
                portList = []

            # Check if the actual peer port is already known (convert to int for comparison)
            peer_port_int = int(peer_port)
            if peer_port_int not in portList:
                self.node_db.write(peer_port_int) # Write the actual peer port as int
                logger.info(f"[Node {self.node_id} addNode] Added new peer port: {peer_port_int}")
            # else:
            #     logger.debug(f"[Node {self.node_id} addNode] Peer port {peer_port_int} already known.")
        except Exception as e:
            logger.error(f"[Node {self.node_id} addNode] Error accessing or writing to NodeDB: {e}", exc_info=True)

    # --- Sending Logic (Adapted from modified old_syncManager) ---

    def sendBlockToRequestor(self, start_block_hash, requestor_conn):
        """Fetches and sends blocks, orphans, port list, and finished message to the requestor."""
        addr = requestor_conn.getpeername()
        logger.info(f"[Node {self.node_id} Sender {addr}] Preparing response for requestBlock after {start_block_hash[:8]}...")
        blocksToSend = self.fetchBlocksFromBlockchain(start_block_hash)

        try:
            # Pass the specific connection to each sending method
            self.sendBlock(blocksToSend, requestor_conn)
            logger.info(f"[Node {self.node_id} Sender {addr}] Sent {len(blocksToSend)} blocks.")
            self.sendSecondaryChain(requestor_conn)
            # logger.info(f"[Node {self.node_id} Sender {addr}] Sent secondary chain.") # Logging done inside sendSecondaryChain
            self.sendPortList(requestor_conn)
            # logger.info(f"[Node {self.node_id} Sender {addr}] Sent port list.") # Logging done inside sendPortList
            self.sendFinishedMessage(requestor_conn)
            # logger.info(f"[Node {self.node_id} Sender {addr}] Sent Finished message.") # Logging done inside sendFinishedMessage
        except Exception as e:
            logger.error(f"[Node {self.node_id} Sender {addr}] Error sending response: {e}", exc_info=True)
            # Consider closing the connection here if not handled by the caller
            try:
                requestor_conn.close()
            except:
                pass # Ignore errors during close

    def fetchBlocksFromBlockchain(self, start_block_hash):
        """Fetches block dictionaries from the database starting after start_block_hash."""
        blocksToSend = []
        try:
            # Use self.db_path to instantiate DB if self.blockchain.db isn't available/reliable
            db = None
            if self.blockchain and hasattr(self.blockchain, 'db') and self.blockchain.db:
                 db = self.blockchain.db
            else:
                 db = BlockchainDB(db_path=self.db_path) # Use node-specific path

            all_blocks_data = db.read_all_blocks() # Assumes this returns list of [block_dict] or similar

            foundStartBlock = (start_block_hash == ZERO_HASH) # If start is ZERO_HASH, send all

            for block_data in all_blocks_data:
                # Assuming read_all_blocks returns list where each item is [block_dict]
                block_dict = block_data[0] if isinstance(block_data, list) and len(block_data) > 0 else block_data

                if not isinstance(block_dict, dict) or 'BlockHeader' not in block_dict or 'blockHash' not in block_dict['BlockHeader']:
                     logger.warning(f"[Node {self.node_id} fetchBlocks] Skipping invalid block data format: {block_data}")
                     continue

                current_hash_hex = block_dict['BlockHeader']['blockHash']

                if foundStartBlock:
                    blocksToSend.append(block_dict) # Append the dictionary
                elif current_hash_hex == start_block_hash:
                    foundStartBlock = True
                    # Don't send the start_block_hash itself, only subsequent blocks

            logger.info(f"[Node {self.node_id} fetchBlocks] Found {len(blocksToSend)} blocks to send after {start_block_hash[:8]}.")

        except Exception as e:
            logger.error(f"[Node {self.node_id} fetchBlocks] Error reading blocks from DB: {e}", exc_info=True)

        return blocksToSend # List of block dictionaries

    def sendBlock(self, blocksToSend, conn):
        """Sends each block dictionary as a rehydrated Block object over the connection."""
        addr = conn.getpeername()
        sent_count = 0
        for blk_dict in blocksToSend: # blocksToSend contains dictionaries from fetchBlocksFromBlockchain
            try:
                # Rehydrate Block object from dictionary using your to_obj method
                blk_obj = Block.to_obj(blk_dict) # <--- Changed from from_dict to to_obj
                payload = blk_obj.serialise() # Serialize the Block object
                env = NetworkEnvelope(command=b'block', payload=payload)
                conn.sendall(env.serialise())
                sent_count += 1
                # logger.debug(f"[Node {self.node_id} Sender {addr}] Sent block {blk_obj.Height}")
            except AttributeError as ae:
                 # This might now indicate missing Tx.to_obj or BlockHeader issues
                 logger.error(f"[Node {self.node_id} Sender {addr}] Missing method error (check Block/Tx.to_obj or serialise): {ae}", exc_info=True)
                 break # Stop sending if core methods are missing
            except Exception as e:
                # Log error but continue trying to send other blocks if possible
                logger.error(f"[Node {self.node_id} Sender {addr}] Failed to rehydrate (to_obj)/send block "
                             f"(Height: {blk_dict.get('Height', 'N/A')}): {e}", exc_info=True)
        logger.info(f"[Node {self.node_id} Sender {addr}] Finished sending {sent_count}/{len(blocksToSend)} blocks.")


    def sendSecondaryChain(self, conn):
        """Sends orphan blocks (Block objects) over the given connection."""
        addr = conn.getpeername()
        # Make a copy to avoid issues if dict changes during iteration
        secondary_chain_copy = dict(self.secondaryChain)
        if secondary_chain_copy:
            logger.info(f"[Node {self.node_id} Sender {addr}] Sending {len(secondary_chain_copy)} orphan blocks...")
            sent_count = 0
            for blockHash, blockObj in secondary_chain_copy.items():
                try:
                    # Assuming blockObj is already a Block object
                    payload = blockObj.serialise()
                    env = NetworkEnvelope(command=b'block', payload=payload) # Use 'block' command
                    conn.sendall(env.serialise())
                    sent_count += 1
                    # logger.debug(f"[Node {self.node_id} Sender {addr}] Sent orphan block {blockObj.Height} ({blockHash[:8]}...)")
                except Exception as e:
                    logger.error(f"[Node {self.node_id} Sender {addr}] Error sending orphan block {blockHash[:8]}: {e}")
            logger.info(f"[Node {self.node_id} Sender {addr}] Finished sending {sent_count}/{len(secondary_chain_copy)} orphan blocks.")
        else:
            logger.info(f"[Node {self.node_id} Sender {addr}] No orphan blocks to send.")

    def sendPortList(self, conn):
        """Sends the list of known peer ports over the given connection."""
        addr = conn.getpeername()
        if not self.node_db:
            logger.warning(f"[Node {self.node_id} Sender {addr}] NodeDB not available, cannot send port list.")
            return
        try:
            ports = self.node_db.read_nodes() # Read ports for this node
            if ports:
                # Ensure ports are integers
                int_ports = [int(p) for p in ports]
                # Assuming portList object has command and serialise methods
                portListObj = portList(int_ports)
                payload = portListObj.serialise()
                env = NetworkEnvelope(portListObj.command, payload)
                conn.sendall(env.serialise())
                logger.info(f"[Node {self.node_id} Sender {addr}] Sent port list: {int_ports}")
            else:
                logger.info(f"[Node {self.node_id} Sender {addr}] No ports in NodeDB to send.")
        except Exception as e:
            logger.error(f"[Node {self.node_id} Sender {addr}] Error sending port list: {e}", exc_info=True)

    def sendFinishedMessage(self, conn):
        """Sends a 'finished sending' message over the given connection."""
        addr = conn.getpeername()
        try:
            # Assuming FinishedSending object has command and serialise methods
            MessageFinish = FinishedSending()
            payload = MessageFinish.serialise()
            envelope = NetworkEnvelope(MessageFinish.command, payload)
            conn.sendall(envelope.serialise())
            logger.info(f"[Node {self.node_id} Sender {addr}] Sent FinishedSending message.")
        except Exception as e:
            logger.error(f"[Node {self.node_id} Sender {addr}] Error sending FinishedSending message: {e}", exc_info=True)

    # --- Client/Download Logic ---

    def connectToHost(self, target_host, target_port, bind_port=None):
        """Establishes a connection to a target peer."""
        # Use a temporary Node instance for the connection attempt
        connector = Node(target_host, target_port)
        try:
            # Bind to the node's listening port if specified
            sock = connector.connect(bind_port=bind_port) # Pass the original bind_port (which might be None) # Pass bind_port correctly
            logger.info(f"[Node {self.node_id} Connector] Connected to {target_host}:{target_port} from local port {bind_port or 'OS-assigned'}")
            return sock, connector # Return socket and the Node instance managing it
        except Exception as e:
            logger.error(f"[Node {self.node_id} Connector] Failed to connect to {target_host}:{target_port} from {bind_port or 'OS-assigned'}: {e}")
            return None, None

    def startDownload(self, target_host, target_port):
        """Initiates block download from a specific peer."""
        logger.info(f"[Node {self.node_id} Downloader] Starting download from {target_host}:{target_port}...")

        # Determine the starting block hash
        lastBlock = None
        try:
             # Use node-specific DB path
             db = BlockchainDB(db_path=self.db_path)
             lastBlock = db.lastBlock()
        except Exception as e:
             logger.error(f"[Node {self.node_id} Downloader] Error reading last block from DB: {e}", exc_info=True)

        if not lastBlock:
            # Use standard Genesis hash if no blocks exist locally
            startBlock = ZERO_HASH
            logger.info(f"[Node {self.node_id} Downloader] No local blocks found. Requesting from Genesis ({ZERO_HASH}).")
        else:
            try:
                lastBlockHeaderHashHex = lastBlock['BlockHeader']['blockHash']
                startBlock = bytes.fromhex(lastBlockHeaderHashHex)
                logger.info(f"[Node {self.node_id} Downloader] Requesting blocks after local tip: {lastBlockHeaderHashHex[:8]}...")
            except (KeyError, IndexError, TypeError, ValueError) as e:
                 logger.error(f"[Node {self.node_id} Downloader] Error parsing last block hash: {e}. Defaulting to Genesis.", exc_info=True)
                 startBlock = ZERO_HASH

        # Prepare request
        getBlocksRequest = requestBlock(startBlock=startBlock)

        sock = None
        connector = None
        stream = None
        try:
            # Connect using the node's listening port for binding
            sock, connector = self.connectToHost(target_host, target_port)
            if not sock or not connector:
                return # Connection failed

            # Send the request
            connector.send(getBlocksRequest) # Use Node's send method
            logger.info(f"[Node {self.node_id} Downloader] Sent requestBlock to {target_host}:{target_port}")

            stream = sock.makefile('rb', None)

            # Receive and process messages
            while True:
                envelope = NetworkEnvelope.parse(stream)
                logger.debug(f"[Node {self.node_id} Downloader {target_port}] Received command: {envelope.command}")

                if envelope.command == FinishedSending.command:
                    logger.info(f"[Node {self.node_id} Downloader {target_port}] Received FinishedSending message. Download complete.")
                    break # Finished

                elif envelope.command == portList.command:
                    try:
                        ports = portList.parse(envelope.stream())
                        logger.info(f"[Node {self.node_id} Downloader {target_port}] Received portlist: {ports}")
                        if self.node_db:
                            added_count = 0
                            current_nodes = self.node_db.read_nodes() or []
                            for p in ports:
                                if p != self.localHostPort and p not in current_nodes:
                                    self.node_db.write(p)
                                    added_count += 1
                            if added_count > 0:
                                logger.info(f"[Node {self.node_id} Downloader {target_port}] Added {added_count} new peer(s) from received list.")
                        else:
                            logger.warning(f"[Node {self.node_id} Downloader {target_port}] NodeDB not available, cannot process received portlist.")
                    except Exception as e_pl:
                        logger.error(f"[Node {self.node_id} Downloader {target_port}] Error processing received portlist: {e_pl}", exc_info=True)

                elif envelope.command == Block.command:
                    try:
                        # Parse into Block object
                        blockObj = Block.parse(envelope.stream())
                        # Calculate hash
                        blockHash = blockObj.BlockHeader.generateBlockHash()
                        logger.info(f"[Node {self.node_id} Downloader {target_port}] Received Block: Height={blockObj.Height}, Hash={blockHash[:8]}...")
                        # Store Block OBJECT for later processing
                        self.newBlockAvailable[blockHash] = blockObj
                    except Exception as e_blk:
                         logger.error(f"[Node {self.node_id} Downloader {target_port}] Error parsing received block: {e_blk}", exc_info=True)

                else:
                    logger.warning(f"[Node {self.node_id} Downloader {target_port}] Ignoring unknown command: {envelope.command}")

        except EOFError:
            logger.info(f"[Node {self.node_id} Downloader {target_port}] Peer closed connection (EOF).")
        except ConnectionRefusedError:
             logger.warning(f"[Node {self.node_id} Downloader] Connection refused by {target_host}:{target_port}.")
        except Exception as e:
            logger.error(f"[Node {self.node_id} Downloader {target_port}] Error during download: {e}", exc_info=True)
        finally:
            if stream:
                try: stream.close()
                except: pass
            if sock:
                try: sock.close()
                except: pass
            logger.info(f"[Node {self.node_id} Downloader] Connection to {target_host}:{target_port} closed.")

    # --- Publishing Logic ---

    def publishTx(self, tx_obj, target_host, target_port):
        """Publishes a transaction object to a specific peer."""
        logger.info(f"[Node {self.node_id} Publisher] Publishing Tx {tx_obj.id()[:8]} to {target_host}:{target_port}")
        sock = None
        connector = None
        try:
            # Connect using the node's listening port for binding
            sock, connector = self.connectToHost(target_host, target_port)
            if not sock or not connector:
                return # Connection failed

            # Use Node's send method which handles envelope creation
            connector.send(tx_obj)
            logger.info(f"[Node {self.node_id} Publisher] Published Tx {tx_obj.id()[:8]} to {target_host}:{target_port}")

        except Exception as e:
            logger.error(f"[Node {self.node_id} Publisher] Error publishing Tx to {target_host}:{target_port}: {e}", exc_info=True)
        finally:
             if sock:
                 try: sock.close()
                 except: pass

    def publishBlock(self, block_obj, target_host, target_port):
        """Publishes a block object to a specific peer."""
        blockHash = block_obj.BlockHeader.generateBlockHash()
        logger.info(f"[Node {self.node_id} Publisher] Publishing Block {block_obj.Height} ({blockHash[:8]}) to {target_host}:{target_port}")
        sock = None
        connector = None
        try:
            # Connect using the node's listening port for binding
            sock, connector = self.connectToHost(target_host, target_port)
            if not sock or not connector:
                return # Connection failed

            # Use Node's send method which handles envelope creation
            connector.send(block_obj)
            logger.info(f"[Node {self.node_id} Publisher] Published Block {block_obj.Height} to {target_host}:{target_port}")

        except Exception as e:
            logger.error(f"[Node {self.node_id} Publisher] Error publishing Block to {target_host}:{target_port}: {e}", exc_info=True)
        finally:
             if sock:
                 try: sock.close()
                 except: pass

    # --- Broadcasting ---
    def broadcast_message(self, message_obj):
        """Broadcasts a message object (Tx, Block) to all known peers."""
        if not self.node_db:
             logger.warning(f"[Node {self.node_id} Broadcaster] NodeDB not available, cannot broadcast.")
             return

        known_peers = self.node_db.read_nodes() or []
        logger.info(f"[Node {self.node_id} Broadcaster] Broadcasting {type(message_obj).__name__} to {len(known_peers)} peer(s): {known_peers}")

        for peer_port in known_peers:
             if peer_port == self.localHostPort:
                 continue # Don't broadcast to self

             # Assuming peers run on the same host for simplicity, adjust if needed
             target_host = self.host # Or derive from peer_port if it includes host info

             # Use the specific publish method
             if isinstance(message_obj, Tx):
                 # Create a thread for each publication to avoid blocking
                 pub_thread = Thread(target=self.publishTx, args=(message_obj, target_host, peer_port), daemon=True)
                 pub_thread.start()
             elif isinstance(message_obj, Block):
                 pub_thread = Thread(target=self.publishBlock, args=(message_obj, target_host, peer_port), daemon=True)
                 pub_thread.start()
             else:
                 logger.warning(f"[Node {self.node_id} Broadcaster] Cannot broadcast unknown message type: {type(message_obj).__name__}")

# Helper function (if needed, e.g., by Block.from_dict)
def to_bytes_field(field):
        if isinstance(field, bytes):
            return field
        elif isinstance(field, str):
            try:
                # Try decoding from hex first
                return bytes.fromhex(field)
            except ValueError:
                # If not hex, assume it's a string needing encoding (e.g., UTF-8)
                # Adjust encoding if necessary based on your data source
                logger.warning(f"Field '{field}' is not valid hex, encoding as UTF-8.")
                return field.encode('utf-8')
            except Exception as e:
                 logger.error(f"Error converting string field '{field}' to bytes: {e}")
                 raise TypeError(f"Could not convert string field to bytes: {field}")
        else:
            raise TypeError(f"Expected field to be str or bytes, got {type(field)}")
