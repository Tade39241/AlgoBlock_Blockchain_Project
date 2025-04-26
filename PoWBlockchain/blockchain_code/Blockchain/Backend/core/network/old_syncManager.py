# # import json
# # import socket
# # from Blockchain.Backend.core.network.connection import Node
# # from Blockchain.Backend.core.database.db import BlockchainDB, NodeDB
# # from Blockchain.Backend.core.blockheader import BlockHeader
# # from Blockchain.Backend.core.network.network import requestBlock, NetworkEnvelope, FinishedSending, portList
# # from Blockchain.Backend.core.Tx import ZERO_HASH, Tx
# # from Blockchain.Backend.core.block import Block
# # from Blockchain.Backend.util.util import little_endian_to_int, int_to_little_endian

# # from threading import Thread

# # class syncManager:
# #     def __init__(self, host, port, MemoryPool ,blockchain=None, localHostPort=None, newBlockAvailable=None,secondaryChain=None, my_public_addr=None,node_id=None,db_path=None):
# #         self.host = host
# #         self.port = port
# #         self.blockchain = blockchain
# #         self.newBlockAvailable = {} if newBlockAvailable is None else newBlockAvailable        
# #         self.secondaryChain = secondaryChain
# #         self.MemoryPool = MemoryPool if MemoryPool is not None else {}
# #         self.localHostPort = localHostPort
# #         self.my_public_addr = my_public_addr  # Store the node's public address here
# #         self.node_id = node_id  # Store the node's ID here
# #         self.db_path = db_path or getattr(blockchain, 'db_path', None)

# #         # --- ADD DEBUG LOG ---
# #         print(f"[SyncManager Init {self.node_id}] Initialized for peer {host}:{port}")
# #         print(f"[SyncManager Init {self.node_id} DEBUG] Received blockchain object: {self.blockchain} (Type: {type(self.blockchain)})", flush=True)
# #         if self.blockchain:
# #              print(f"[SyncManager Init {self.node_id} DEBUG] Blockchain has 'db' attribute: {hasattr(self.blockchain, 'db')}", flush=True)
# #              if hasattr(self.blockchain, 'db'):
# #                   print(f"[SyncManager Init {self.node_id} DEBUG] Blockchain.db object: {self.blockchain.db} (Type: {type(self.blockchain.db)})", flush=True)
# #         # --- END DEBUG LOG ---
# #     def spinUpServer(self):
# #         self.server = Node(self.host, self.port)
# #         self.server.startServer()
# #         print("SERVER STARTED")
# #         print(f"LISTENING at {self.host}:{self.port}")    

# #         while True:
# #             self.conn, self.addr = self.server.acceptConnection()
# #             handleConn = Thread(target=self.handleConnection)
# #             handleConn.start()

# #     def handleConnection(self,conn, addr):
# #         current_conn = conn
# #         current_addr = addr
# #         print(f"[Node {self.node_id} Handler {current_addr}] Handling connection...") # Added log
        
# #         # --- PORTCHECK MAGIC HANDLING ---
# #         try:
# #             # Peek at the first 9 bytes using the correct connection
# #             portcheck_magic = current_conn.recv(9, socket.MSG_PEEK) # Use current_conn
# #             if portcheck_magic == b'PORTCHECK':
# #                 current_conn.recv(9)  # Consume the bytes using current_conn
# #                 print(f"[Node {self.node_id} Handler {current_addr}] Received port check magic, closing.") # Added context
# #                 current_conn.close() # Use current_conn
# #                 return
# #         except Exception as e:
# #             print(f"[Node {self.node_id} Handler {current_addr}] Error checking for port check magic: {e}") # Added context
# #             try:
# #                  current_conn.close() # Use current_conn
# #             except:
# #                  pass # Ignore errors during close
# #             return
# #         # --- END PORTCHECK MAGIC HANDLING ---
        
# #         try:
# #             # Correctly parse the envelope using the specific connection
# #             envelope = NetworkEnvelope.parse(current_conn.makefile('rb', None)) # Use NetworkEnvelope.parse and current_conn

# #             # --- Add Peer Node (Corrected Logic) ---
# #             peer_port = current_addr[1]
# #             # Check if port is valid and not our own listening port
# #             if 1024 <= peer_port <= 65535 and peer_port != self.localHostPort:
# #                 print(f"[Node {self.node_id} Handler {current_addr}] Adding peer node (Port: {peer_port})")
# #                 self.addNode(peer_port) # Pass the actual peer port to addNode
# #             else: # Optional: Log why it's skipped
# #                 print(f"[Node {self.node_id} Handler {current_addr}] Skipping addNode for port {peer_port} (Self or Invalid)")
# #             # --- End Add Peer Node ---

# #              # --- Process based on command (Existing logic is mostly fine) ---
# #             if envelope.command == b'tx':
# #                 tx = Tx.parse(envelope.stream())
# #                 # Optional: Remove the TxId check if Tx.parse doesn't set it
# #                 # if tx.id() != tx.TxId:
# #                 #     raise ValueError("TxId mismatch")
# #                 tx_id = tx.id() # Calculate ID
# #                 print(f"[Node {self.node_id} Handler {current_addr}] Transaction Received: {tx_id[:8]}...") # Added context
# #                 self.MemoryPool[tx_id] = tx # Store Tx OBJECT
            
# #             elif envelope.command == b'block':
# #                 blk = Block.parse(envelope.stream())
# #                 h = blk.BlockHeader.generateBlockHash()
# #                 print(f"[Node {self.node_id} Handler {current_addr}] Block Received: Height={blk.Height}, Hash={h[:8]}...") # Added context
# #                 self.newBlockAvailable[h] = blk # Store Block OBJECT
# #                 # print(f"New Block Received : {blk.Height}") # Redundant log
            
# #             # if envelope.command == b'tx':
# #             #     Transaction = Tx.parse(envelope.stream())
# #             #     calculated_txid = Transaction.id()
# #             #     Transaction.TxId = Transaction.id()
# #             #     if calculated_txid != Transaction.TxId:
# #             #             raise ValueError(f"TxId Mismatch! Calculated: {calculated_txid}, Received: {Transaction.TxId}")
# #             #     print(f"Transaction Received : {Transaction.TxId}")
                
# #             #     self.MemoryPool[Transaction.TxId] = Transaction


# #             # if envelope.command == b'block':
# #             #     blockObj = Block.parse(envelope.stream())
# #             #     BlockHeaderObj = BlockHeader(blockObj.BlockHeader.version,
# #             #               blockObj.BlockHeader.prevBlockHash,
# #             #               blockObj.BlockHeader.merkleRoot,
# #             #               blockObj.BlockHeader.timestamp,
# #             #               blockObj.BlockHeader.bits,
# #             #               blockObj.BlockHeader.nonce)
                
# #             #     block_hash = BlockHeaderObj.generateBlockHash() # Get hash

# #             #     print(f"[SyncManager {self.node_id} handleConnection DEBUG] Adding block {blockObj.Height} ({block_hash[:8]}) to newBlockAvailable from {self.addr}", flush=True) # ADD LOG
# #             #     self.newBlockAvailable[BlockHeaderObj.generateBlockHash()] = blockObj
# #             #     print(f"New Block Received : {blockObj.Height}")

            
# #             elif envelope.command == requestBlock.command:
# #                 start_block, end_block = requestBlock.parse(envelope.stream())
# #                 self.sendBlockToRequestor(start_block)
# #                 print(f"Start Block is {start_block} \n End Block is {end_block}")

# #             else:
# #                 print(f"[SyncManager] Ignoring envelope.command={envelope.command}")
            
# #         except Exception as e:
# #             print(f"[SyncManager {self.node_id}] Error while processing request: {e}")
# #         finally:
# #             self.conn.close()

        

# #     def addNode(self):
# #         # nodeDb = NodeDB()
# #         nodeDb = NodeDB(node_id=self.node_id) # NEW
# #         portList = nodeDb.read_nodes()
# #         print(f"[SyncManager {self.node_id}] Current ports in database: {portList}")

# #         if self.addr[1] and (self.addr[1]+ 1 ) not in portList:
# #             new_port = self.addr[1] + 1
# #             nodeDb.write(new_port)
# #             print(f"Added new port: {new_port}")

# #     def sendBlockToRequestor(self, start_block, requestor_conn): # Added requestor_conn
# #         """Fetches and sends blocks, orphans, port list, and finished message to the requestor."""
# #         addr = requestor_conn.getpeername() # Get address for logging
# #         print(f"[Node {self.node_id} Sender {addr}] Preparing response for requestBlock after {start_block.hex()[:8]}...")
# #         blocksToSend = self.fetchBlocksFromBlockchain(start_block)

# #         try:
# #             # Pass the specific connection to each sending method
# #             self.sendBlock(blocksToSend, requestor_conn) # Pass conn
# #             print(f"[Node {self.node_id} Sender {addr}] Sent {len(blocksToSend)} blocks.")
# #             self.sendSecondaryChain(requestor_conn) # Pass conn
# #             print(f"[Node {self.node_id} Sender {addr}] Sent secondary chain.")
# #             self.sendPortList(requestor_conn) # Pass conn
# #             print(f"[Node {self.node_id} Sender {addr}] Sent port list.")
# #             self.sendFinishedMessage(requestor_conn) # Pass conn
# #             print(f"[Node {self.node_id} Sender {addr}] Sent Finished message.")
# #         except Exception as e:
# #             print(f"[Node {self.node_id} Sender {addr}] Error sending response: {e}")
# #             # Consider closing the connection here if not handled by the caller
# #             try:
# #                 requestor_conn.close()
# #             except:
# #                 pass # Ignore errors during close

# #     # def sendBlockToRequestor(self, start_block: bytes):
# #     #     # 1) fetch raw dicts from DB
# #     #     blocks = self.fetchBlocksFromBlockchain(start_block)
# #     #     print(f"[SyncManager {self.node_id}] Prepared {len(blocks)} blocks to send.")

# #     #     # 2) send each block as a proper Block object
# #     #     for entry in blocks:
# #     #         # unwrap list‐wrapping
# #     #         blk_dict = entry[0] if isinstance(entry, list) and len(entry)==1 else entry

# #     #         # normalize header fields back into bytes/int
# #     #         hdr = blk_dict['BlockHeader']
# #     #         # prevBlockHash and merkleRoot come in as hex‐strings
# #     #         if isinstance(hdr['prevBlockHash'], str):
# #     #             hdr['prevBlockHash'] = bytes.fromhex(hdr['prevBlockHash'])
# #     #         if isinstance(hdr['merkleRoot'], str):
# #     #             hdr['merkleRoot'] = bytes.fromhex(hdr['merkleRoot'])
# #     #         # version, timestamp, nonce come in possibly as str
# #     #         hdr['version']   = int(hdr['version'])
# #     #         hdr['timestamp'] = int(hdr['timestamp'])
# #     #         hdr['nonce']     = int(hdr['nonce'])
# #     #         # bits is a hex‐string like '1f00ffff'
# #     #         if isinstance(hdr['bits'], str):
# #     #             hdr['bits'] = int(hdr['bits'], 16)

# #     #         # rehydrate a Block instance
# #     #         blk = Block.from_dict(blk_dict)
# #     #         env = NetworkEnvelope(command=b'block', payload=blk.serialise())
# #     #         try:
# #     #             self.conn.sendall(env.serialise())
# #     #             print(f"[SyncManager {self.node_id}] Sent block {blk.Height}", flush=True)
# #     #         except Exception as e:
# #     #             print(f"[SyncManager {self.node_id}] Failed to send block {blk.Height}: {e}", flush=True)

# #     #     # 3) now send any orphans…
# #     #     if self.secondaryChain:
# #     #         for hdr_hash, orphan in self.secondaryChain.items():
# #     #             env = NetworkEnvelope(b'block', orphan.serialise())
# #     #             self.conn.sendall(env.serialise())
# #     #             print(f"[SyncManager {self.node_id}] Sent orphan block {orphan.Height}")

# #     #     # 4) then your port list
# #     #     pl = portList(ports=list(self.MemoryPool.keys()))
# #     #     self.conn.sendall(NetworkEnvelope(b'portlist', pl.serialise()).serialise())
# #     #     print(f"[SyncManager {self.node_id}] Sent portlist")

# #     #     # 5) and finally the Finished marker
# #     #     fin = FinishedSending()
# #     #     self.conn.sendall(NetworkEnvelope(b'Finished', fin.serialise()).serialise())
# #     #     print(f"[SyncManager {self.node_id}] Sent Finished")



# #     # def sendPortList(self):
# #     #     nodeDB = NodeDB(node_id=self.node_id) # NEW
# #     #     ports = nodeDB.read_nodes()
# #     #     if ports is None:
# #     #         raise ValueError("No nodes found in the NodeDB.")

# #     #     portlist = portList(ports)
# #     #     envelope = NetworkEnvelope(portlist.command, portlist.serialise())
# #     #     self.conn.sendall(envelope.serialise())

# #     # def sendPortList(self):
# #     #     nodeDB = NodeDB(node_id=self.node_id)
# #     #     raw_ports = nodeDB.read_nodes()              # e.g. ['9001', '9002', ...]
# #     #     if not raw_ports:
# #     #         raise ValueError("No nodes found in the NodeDB.")
# #     #     ports = [int(p) for p in raw_ports]          # <-- convert to ints here
# #     #     portlist = portList(ports)
# #     #     envelope = NetworkEnvelope(portlist.command, portlist.serialise())
# #     #     self.conn.sendall(envelope.serialise())

# #     def sendPortList(self, conn): # Added conn argument
# #         """Sends the list of known peer ports over the given connection."""
# #         addr = conn.getpeername() # <--- Uses getpeername() on the passed conn
# #         try:
# #             # Use node_id to get the correct NodeDB instance
# #             node_db = NodeDB(node_id=self.node_id)
# #             # Assuming read_nodes() returns list of strings or ints
# #             raw_ports = node_db.read_nodes()
# #             if raw_ports:
# #                 # Ensure ports are integers for portList object
# #                 ports = [int(p) for p in raw_ports]
# #                 # Assuming portList object has command and serialise methods
# #                 portListObj = portList(ports)
# #                 payload = portListObj.serialise()
# #                 env = NetworkEnvelope(portListObj.command, payload)
# #                 conn.sendall(env.serialise()) # <--- Uses the passed conn to send
# #                 print(f"[Node {self.node_id} Sender {addr}] Sent port list: {ports}")
# #             else:
# #                 print(f"[Node {self.node_id} Sender {addr}] No ports in NodeDB to send.")
# #         except Exception as e:
# #             print(f"[Node {self.node_id} Sender {addr}] Error sending port list: {e}")


# #     def sendSecondaryChain(self, conn): # Added conn
# #         """Sends orphan blocks (if any) over the given connection."""
# #         addr = conn.getpeername()
# #         if self.secondaryChain: # Check if the dictionary exists and is not empty
# #             print(f"[Node {self.node_id} Sender {addr}] Sending {len(self.secondaryChain)} orphan blocks...")
# #             for blockHash, blockObj in self.secondaryChain.items():
# #                 try:
# #                     # Assuming blockObj is already a Block object
# #                     payload = blockObj.serialise()
# #                     env = NetworkEnvelope(command=b'block', payload=payload) # Use 'block' command
# #                     conn.sendall(env.serialise())
# #                     print(f"[Node {self.node_id} Sender {addr}] Sent orphan block {blockObj.Height} ({blockHash[:8]}...)")
# #                 except Exception as e:
# #                     print(f"[Node {self.node_id} Sender {addr}] Error sending orphan block {blockHash[:8]}: {e}")
# #         else:
# #             print(f"[Node {self.node_id} Sender {addr}] No orphan blocks to send.")
    
# #     # def sendSecondaryChain(self):
# #     #     TempSecChain = dict(self.secondaryChain)
# #     #     for blockHash in TempSecChain:
# #     #         envelope = NetworkEnvelope(TempSecChain[blockHash].command, TempSecChain[blockHash].serialise())
# #     #         self.conn.sendall(envelope.serialise())

# #     # def sendFinishedMessage(self):
# #     #     MessageFinish = FinishedSending()
# #     #     envelope = NetworkEnvelope(MessageFinish.command, MessageFinish.serialise())
# #     #     self.conn.sendall(envelope.serialise())

# #     def sendFinishedMessage(self, conn): # Added conn
# #         """Sends a 'finished sending' message over the given connection."""
# #         addr = conn.getpeername()
# #         try:
# #             # Assuming FinishedSending object has command and serialise methods
# #             MessageFinish = FinishedSending()
# #             payload = MessageFinish.serialise()
# #             envelope = NetworkEnvelope(MessageFinish.command, payload)
# #             conn.sendall(envelope.serialise())
# #             print(f"[Node {self.node_id} Sender {addr}] Sent FinishedSending message.")
# #         except Exception as e:
# #             print(f"[Node {self.node_id} Sender {addr}] Error sending FinishedSending message: {e}")
      
# #     # def sendBlock(self, blockstosend):
# #     #     for block in blockstosend:
# #     #         cblock = Block.to_obj(block)
# #     #         envelope = NetworkEnvelope(cblock.command, cblock.serialise())
# #     #         self.conn.sendall(envelope.serialise())
# #     #         print(f'block sent {cblock.Height}')

# #     def sendBlock(self, blocksToSend, conn):
# #         """Send every block in blocksToSend as a P2P envelope over the given connection."""
# #         addr = conn.getpeername() # Get address for logging
# #         for entry in blocksToSend:
# #             # db.read_all_blocks() gives you dicts, so rehydrate to Block
# #             blk_dict = entry[0] if isinstance(entry, list) and len(entry)==1 else entry
# #             try:
# #                 blk_obj  = Block.from_dict(blk_dict) # Rehydrate object from dict
# #                 payload = blk_obj.serialise()        # Serialize object to bytes
# #                 env = NetworkEnvelope(command=b'block', payload=payload)
# #                 conn.sendall(env.serialise())        # Send bytes over the specific connection
# #                 print(f"[Node {self.node_id} Sender {addr}] Sent block {blk_obj.Height}", flush=True)
# #             except Exception as e:
# #                 # Log error but continue trying to send other blocks if possible
# #                 print(f"[Node {self.node_id} Sender {addr}] Failed to rehydrate/send block "
# #                     f"(Height: {blk_dict.get('Height', 'N/A')}): {e}", flush=True)
# #                 import traceback
# #                 traceback.print_exc()

# #     # def sendBlock(self, blocksToSend):
# #     #     for entry in blocksToSend:
# #     #         block_dict = entry[0] if isinstance(entry, list) and len(entry) == 1 else entry
# #     #         payload = json.dumps(block_dict).encode('utf-8')
# #     #         # wrap in the original P2P envelope:
# #     #         env = NetworkEnvelope(command=b'block', payload=payload)
# #     #         try:
# #     #             self.conn.sendall(env.serialise())
# #     #             print(f"[SyncManager {self.node_id}] Sent block {block_dict.get('Height')}", flush=True)
# #     #         except Exception as e:
# #     #             print(f"[SyncManager {self.node_id}] Failed to send block "
# #     #                   f"{block_dict.get('Height')}: {e}", flush=True)

# #     def fetchBlocksFromBlockchain(self, start_Block):
# #         fromBlockOnwards = start_Block.hex()
# #         handling_node_id = self.node_id if hasattr(self, 'node_id') else 'UNKNOWN'
# #         print(f"[fetchBlocksFromBlockchain {handling_node_id} DEBUG] Handling request for blocks after {fromBlockOnwards[:8]}...", flush=True)

# #         # --- FALLBACK: if we're running in the client and proxy has no .db, build one locally ---
# #         if not getattr(self.blockchain, 'db', None):
# #             # if no proxy‐db, open the same path your Blockchain already uses
# #             db_dir = self.db_path or getattr(self.blockchain, 'db_path', None)
# #             if db_dir is None:
# #                 raise RuntimeError("No db_path for fallback")
# #             print(f"[fetchBlocksFromBlockchain {handling_node_id}] Proxy has no .db, instantiating at {db_dir}", flush=True)
# #             self.blockchain.db = BlockchainDB(db_path=db_dir, node_id=self.node_id)

# #         print(f"[SyncManager] {self.node_id}] Fetching blocks from hash {fromBlockOnwards[:8]}...")
# #         blocksToSend = []

# #         # Check if blockchain and its db attribute are available
# #         if not self.blockchain or not hasattr(self.blockchain, 'db') or not self.blockchain.db:
# #             print(f"[SyncManager] {self.node_id}] Blockchain or DB instance not available in fetchBlocksFromBlockchain.")
# #             return []

# #         # Use the db attribute of the blockchain proxy to read blocks
# #         try:
# #             # Assuming read_all_blocks() is the correct method on the DB object
# #             all_blocks = self.blockchain.db.read_all_blocks()
# #         except Exception as e:
# #             print(f"[SyncManager {handling_node_id}] Error calling blockchain.db.read_all_blocks(): {e}")
# #             return [] # Return empty if reading fails

# #         foundBlock = False
# #         start_height = -1
# #         for i, block_dict in enumerate(all_blocks):
# #             # Handle potential list wrapping if db returns [[block_dict]]
# #             block_data = block_dict[0] if isinstance(block_dict, list) and len(block_dict) == 1 else block_dict
# #             if not isinstance(block_data, dict): continue # Skip invalid format

# #             block_hash = block_data.get('BlockHeader', {}).get('blockHash')
# #             if block_hash == fromBlockOnwards:
# #                 foundBlock = True
# #                 start_height = block_data.get('Height', i) # Use Height if available, else index
# #                 print(f"[SyncManager {self.node_id}] Found start block hash {fromBlockOnwards[:8]} at height {start_height}.")
# #                 # Don't add the start block itself, start from the next one
# #             elif foundBlock:
# #                 # Append the block dictionary (or list containing the dict)
# #                 blocksToSend.append(block_dict)

# #         if not foundBlock and fromBlockOnwards != getattr(self.blockchain, 'ZERO_HASH', '0'*64): # Check if it wasn't found unless it was ZERO_HASH
# #              print(f"[SyncManager {self.node_id}] Start block hash {fromBlockOnwards[:8]} not found in local chain.")
# #         elif not foundBlock and fromBlockOnwards == getattr(self.blockchain, 'ZERO_HASH', '0'*64):
# #              print(f"[SyncManager {self.node_id}] Request started from ZERO_HASH, sending all blocks.")
# #              # If start was ZERO_HASH and it wasn't "found" (because it's not stored), send everything
# #              blocksToSend = all_blocks # Send all blocks read from DB

# #         print(f"[SyncManager {self.node_id}] Prepared {len(blocksToSend)} blocks to send.")
# #         return blocksToSend


# #         # foundBlock = False
# #         # for block in blocks:
# #         #     if block['BlockHeader']['blockHash'] == fromBlockOnwards:
# #         #         foundBlock = True
# #         #         continue

# #         #     if foundBlock:
# #         #         blocksToSend.append(block)

# #         # return blocksToSend
    
# #     def connectToHost(self,bind_port = None):
# #         print(f"[connectToHost {self.node_id}] Attempting connection to {self.host}:{self.port} (binding to {bind_port})")
# #         self.connect = Node(self.host, self.port) # Use instance host/port
# #         self.socket = self.connect.connect(bind_port=bind_port) # Pass bind_port
# #         if not self.socket:
# #             # Reset attributes on failure
# #             self.connect = None
# #             self.socket = None
# #             self.stream = None
# #             raise ConnectionError(f"Failed to connect to {self.host}:{self.port}")
# #         self.stream = self.socket.makefile('rb', None)
# #         print(f"[connectToHost {self.node_id}] Connected successfully.")

# #     def publishTx(self, Tx):
# #         # Assuming connectToHost was called previously or connection is persistent
# #         if not self.connect:
# #             print(f"[publishTx {self.node_id}] Error: Not connected. Call connectToHost first.")
# #             return # Or raise error
# #         try:
# #             self.connect.send(Tx) # Assuming Node.send handles Tx objects
# #             print(f"[publishTx {self.node_id}] Published Tx {Tx.id()} to {self.host}:{self.port}")
# #         except Exception as e:
# #             print(f"[publishTx {self.node_id}] Error publishing Tx: {e}")

# #     # def publishBlock(self, localport, port, block):
# #     #     self.connectToHost(localport, port)
# #     #     block_bytes = block.serialise()
# #     #     # print("DEBUG (sender): block serial length =", len(block_bytes))
# #     #     # print("DEBUG (sender): block serial hex =", block_bytes.hex())
# #     #     # print("DEBUG (sender): block TxCount =", len(block.Txs))
# #     #     self.connect.send(block)

# #     # def publishBlock(self, localport, port, block):
# #     #     """
# #     #     Connects to the peer specified by self.host/self.port,
# #     #     binds the source to localport, and sends the block.
# #     #     The 'port' argument is ignored; self.port is used as the target.
# #     #     """
# #     #     temp_socket = None # Use a temporary variable for the socket
# #     #     try:
# #     #         # 1. Connect to the target peer (self.host, self.port) using a specific local port
# #     #         print(f"[publishBlock {self.node_id}] Attempting connection to {self.host}:{self.port} (from src port {localport})")
# #     #         temp_node = Node(self.host, self.port)
# #     #         temp_socket = temp_node.connect(bind_port=localport)

# #     #         if not temp_socket:
# #     #             raise ConnectionError(f"Failed to connect socket to {self.host}:{self.port}")
# #     #         print(f"[publishBlock {self.node_id}] Connected to {self.host}:{self.port}")

# #     #         # 2. Send the block (assuming Node.send handles serialization/envelope)
# #     #         # We need to use the 'send' method associated with the temp_node/temp_socket
# #     #         temp_node.socket = temp_socket # Assign the connected socket to the temp Node instance
# #     #         temp_node.send(block)

# #     #         block_hash = block.BlockHeader.generateBlockHash() # Get hash for logging
# #     #         print(f"[publishBlock {self.node_id}] Published block {block.Height} ({block_hash[:8]}) to {self.host}:{self.port}")

# #     #     except ConnectionError as ce:
# #     #          print(f"[publishBlock {self.node_id}] Connection failed for {self.host}:{self.port}: {ce}")
# #     #     except Exception as e:
# #     #         # Log other potential errors during sending
# #     #         print(f"[publishBlock {self.node_id}] Error publishing block to {self.host}:{self.port}: {e}")
# #     #     finally:
# #     #         # 3. Ensure the temporary connection is closed
# #     #         if temp_socket:
# #     #             try:
# #     #                 temp_socket.close()
# #     #                 print(f"[publishBlock {self.node_id}] Closed connection to {self.host}:{self.port}")
# #     #             except Exception as e_close:
# #     #                 print(f"[publishBlock {self.node_id}] Error closing connection: {e_close}")


# #     def publishBlock(self, localport, port, block):
# #         """
# #         Connects to the peer specified by self.host/self.port,
# #         and sends the block.
# #         The 'port' and 'localport' arguments are ignored; self.port is used as the target,
# #         and the OS chooses the source port.
# #         """
# #         temp_socket = None # Use a temporary variable for the socket
# #         try:
# #             # 1. Connect to the target peer (self.host, self.port)
# #             print(f"[publishBlock {self.node_id}] Attempting connection to {self.host}:{self.port} (OS chooses src port)")
# #             temp_node = Node(self.host, self.port)
# #             temp_socket = temp_node.connect() # Let OS choose source port

# #             if not temp_socket:
# #                 # temp_node.connect() now returns None on failure, so raise error here
# #                 raise ConnectionError(f"Failed to connect socket to {self.host}:{self.port}")
# #             print(f"[publishBlock {self.node_id}] Connected to {self.host}:{self.port}")

# #             # 2. Send the block (assuming Node.send handles serialization/envelope)
# #             temp_node.socket = temp_socket # Assign the connected socket to the temp Node instance
# #             temp_node.send(block)

# #             # Ensure block has necessary attributes before logging
# #             block_height = getattr(block, 'Height', 'N/A')
# #             block_hash = 'N/A'
# #             if hasattr(block, 'BlockHeader') and hasattr(block.BlockHeader, 'generateBlockHash'):
# #                  block_hash = block.BlockHeader.generateBlockHash()[:8] # Get first 8 chars of hash

# #             print(f"[publishBlock {self.node_id}] Published block {block_height} ({block_hash}) to {self.host}:{self.port}")

# #         except ConnectionError as ce:
# #              print(f"[publishBlock {self.node_id}] Connection failed for {self.host}:{self.port}: {ce}")
# #         except Exception as e:
# #             # Log other potential errors during sending
# #             print(f"[publishBlock {self.node_id}] Error publishing block to {self.host}:{self.port}: {e}")
# #             import traceback # Import traceback for detailed error info
# #             traceback.print_exc() # Print the full traceback for debugging
# #         finally:
# #             # 3. Ensure the temporary connection is closed
# #             if temp_socket:
# #                 try:
# #                     temp_socket.close()
# #                     print(f"[publishBlock {self.node_id}] Closed connection to {self.host}:{self.port}")
# #                 except Exception as e_close:
# #                     print(f"[publishBlock {self.node_id}] Error closing connection: {e_close}")


    
# #     def startDownload(self):
# #         print(f"[SyncManager {self.node_id}] Initiating startup synchronization...")
    
# #         # 1) Load peers from NodeDB
# #         try:
# #             node_db = NodeDB(node_id=self.node_id)
# #             peer_ports = node_db.read_nodes() or []
# #         except Exception as e:
# #             print(f"[SyncManager {self.node_id}] Error reading peers: {e}")
# #             return
    
# #         if not peer_ports:
# #             print(f"[SyncManager {self.node_id}] No peers found. Skipping sync.")
# #             return
    
# #         # 2) Figure our local tip
# #         tip = None
# #         try:
# #             tip = self.blockchain.get_last_block_hash() or bytes.fromhex(self.blockchain.ZERO_HASH)
# #         except:
# #             tip = bytes.fromhex(self.blockchain.ZERO_HASH)
# #         if not isinstance(tip, bytes):
# #             tip = bytes.fromhex(tip)
    
# #         print(f"[SyncManager {self.node_id}] Local tip hash: {tip.hex()[:16]}")
    
# #         # 3) Try each peer until one succeeds
# #         for port in peer_ports:
# #             if port == self.localHostPort:
# #                 continue
# #             print(f"\n[SyncManager {self.node_id}] Syncing from peer {self.host}:{port}")
# #             try:
# #                 peer = Node(self.host, port)
# #                 sock = peer.connect()
# #                 if not sock:
# #                     raise ConnectionError("connect() returned None")
# #                 peer.socket = sock
    
# #                 # 4) Send the requestBlock envelope
# #                 req = requestBlock(startBlock=tip)
# #                 print(f"[SyncManager {self.node_id}] Requesting blocks after {tip.hex()[:16]}")
# #                 peer.send(req)
    
# #                 # 5) Read envelopes until 'Finished'
# #                 stream = sock.makefile('rb')
# #                 while True:
# #                     env = NetworkEnvelope.parse(stream)
# #                     cmd = env.command
    
# #                     if cmd == b'Finished':
# #                         print(f"[SyncManager {self.node_id}] Received Finished from {port}")
# #                         break
    
# #                     if cmd == portList.command:
# #                         ports = portList.parse(env.stream())
# #                         db = NodeDB(node_id=self.node_id)
# #                         added = 0
# #                         for p in ports:
# #                             if p not in db.read_nodes():
# #                                 db.write(p)
# #                                 added += 1
# #                         if added:
# #                             print(f"[SyncManager {self.node_id}] Added {added} new peer(s)")
    
# #                     elif cmd == b'block':
# #                         blk = Block.parse(env.stream())
# #                         h = blk.BlockHeader.generateBlockHash()
# #                         print(f"[SyncManager {self.node_id}] Received block {blk.Height} ({h[:8]})")
# #                         self.newBlockAvailable[h] = blk
    
# #                     else:
# #                         print(f"[SyncManager {self.node_id}] Skipping cmd={cmd}")
    
# #                 sock.close()
# #                 print(f"[SyncManager {self.node_id}] Sync with {port} complete.")
# #                 break
    
# #             except Exception as e:
# #                 print(f"[SyncManager {self.node_id}] Error syncing {port}: {e}")
# #                 try: sock.close()
# #                 except: pass
    
# #         print(f"[SyncManager {self.node_id}] Startup synchronization finished.")


        
# #     # --- END FIX ---

# #     # def startDownload(self, localport, port, bindPort):
# #     #     print(f"[SyncManager {self.node_id}] Starting download from peer {self.host}:{port}...")
# #     #     # --- FIX: Use existing BlockchainDB instance ---
# #     #     # lastBlock = BlockchainDB().lastBlock() # OLD
# #     #     if not self.blockchain or not self.blockchain.db:
# #     #          print(f"[SyncManager {self.node_id}] Blockchain or DB instance not available in startDownload.")
# #     #          # Handle error: maybe try to get genesis hash or abort
# #     #          lastBlockHeader = ZERO_HASH # Fallback
# #     #     else:
# #     #         lastBlock = self.blockchain.db.lastBlock() # Use existing instance
# #     #         if not lastBlock:
# #     #             print(f"[SyncManager {self.node_id}] Local blockchain is empty. Requesting from genesis.")
# #     #             # Use a known genesis hash or ZERO_HASH if genesis isn't fixed/known
# #     #             # Assuming genesis_block.json hash is '40177a34e0f1d315ef0deb6719621370eac4789ce790e66449af534ede7c1a66'
# #     #             lastBlockHeader = "40177a34e0f1d315ef0deb6719621370eac4789ce790e66449af534ede7c1a66" # Or ZERO_HASH
# #     #         else:
# #     #             # Handle potential list wrapping
# #     #             block_data = lastBlock[0] if isinstance(lastBlock, list) and len(lastBlock) == 1 else lastBlock
# #     #             if isinstance(block_data, dict) and 'BlockHeader' in block_data:
# #     #                 lastBlockHeader = block_data['BlockHeader']['blockHash']
# #     #             else:
# #     #                 print(f"[SyncManager {self.node_id}] Could not get hash from last block: {lastBlock}")
# #     #                 lastBlockHeader = ZERO_HASH # Fallback
# #     #     # --- END FIX ---

# #     #     startBlock = bytes.fromhex(lastBlockHeader)
# #     #     print(f"[SyncManager {self.node_id}] Requesting blocks starting after: {lastBlockHeader[:8]}...")

# #     #     getHeaders = requestBlock(startBlock=startBlock)
# #     #     self.connectToHost(localport, port, bindPort)
# #     #     self.connect.send(getHeaders)

# #     #     while True:
# #     #         try:
# #     #             envelope = NetworkEnvelope.parse(self.stream)
# #     #             print(f"[SyncManager {self.node_id}] Received envelope command={envelope.command}, len={len(envelope.payload)}")

# #     #             if envelope.command == b'Finished':
# #     #                 # blockObj = FinishedSending.parse(envelope.stream()) # Parsing might not be needed
# #     #                 print(f'[SyncManager {self.node_id}] Received Finished message. Download complete.')
# #     #                 self.socket.close()
# #     #                 break

# #     #             if envelope.command == b'portlist':
# #     #                 try:
# #     #                     ports = portList.parse(envelope.stream())
# #     #                     # --- FIX: Instantiate NodeDB correctly ---
# #     #                     # nodeDb = NodeDB() # OLD
# #     #                     nodeDb = NodeDB(node_id=self.node_id) # NEW
# #     #                     # --- END FIX ---
# #     #                     portlists = nodeDb.read_nodes()
# #     #                     added_count = 0
# #     #                     for p in ports:
# #     #                         if p not in portlists:
# #     #                             nodeDb.write(p)
# #     #                             added_count += 1
# #     #                     if added_count > 0:
# #     #                          print(f"[SyncManager {self.node_id}] Added {added_count} new ports from peer list.")
# #     #                 except Exception as e:
# #     #                      print(f"[SyncManager {self.node_id}] Error processing received portlist: {e}", exc_info=True)


# #     #             if envelope.command == b'block':
# #     #                 try:
# #     #                     blockObj = Block.parse(envelope.stream())
# #     #                     print(f"[SyncManager {self.node_id}] Received block {blockObj.Height}")

# #     #                     # Add received block to the newBlockAvailable dict for processing by Blockchain.LostCompetition
# #     #                     # Need block hash as key
# #     #                     block_hash = blockObj.BlockHeader.generateBlockHash() # Assuming this works on the parsed object
# #     #                     self.newBlockAvailable[block_hash] = blockObj
# #     #                     print(f"[SyncManager {self.node_id}] Added block {blockObj.Height} ({block_hash[:8]}) to newBlockAvailable.")

# #     #                     # --- REMOVE direct write/validation from here ---
# #     #                     # The Blockchain.LostCompetition method will handle validation, state changes, and writing.
# #     #                     # --- END REMOVAL ---

# #     #                 except Exception as e:
# #     #                      print(f"[SyncManager {self.node_id}] Error processing received block: {e}", exc_info=True)

# #     #         except Exception as e:
# #     #              print(f"[SyncManager {self.node_id}] Error reading from stream during download: {e}", exc_info=True)
# #     #              try: self.socket.close()
# #     #              except: pass
# #     #              break # Exit loop on stream error

# #     #     print(f"[SyncManager {self.node_id}] Download process finished.")


# #         # print("Starting download...")
# #         # lastBlock = BlockchainDB().lastBlock()

# #         # if not lastBlock:
# #         #     lastBlockHeader = "00000b4f115d20e3c33951d2987d79b975a446e37e489ca1d6ea66238f7b4ba9"
# #         # else:
# #         #     lastBlockHeader = lastBlock[0]['BlockHeader']['blockHash']

# #         # startBlock = bytes.fromhex(lastBlockHeader)

# #         # getHeaders = requestBlock(startBlock=startBlock)
# #         # self.connectToHost(localport, port, bindPort)
# #         # print(f"localport value: {localport}, type: {type(localport)}")
# #         # self.connect.send(getHeaders)

# #         # while True:
# #         #     envelope = NetworkEnvelope.parse(self.stream)
# #         #     print("DEBUG: Envelope command =", envelope.command)
# #         #     print("DEBUG: Envelope length =", len(envelope.payload))

# #         #     if envelope.command == b'Finished':
# #         #         blockObj = FinishedSending.parse(envelope.stream())
# #         #         print(f'All blocks receieved')
# #         #         self.socket.close()
# #         #         break

# #         #     if envelope.command == b'portlist':
# #         #         s = envelope.stream()
# #         #         raw_data = s.read()
# #         #         print("DEBUG: envelope stream bytes =", raw_data.hex())
# #         #         s.seek(0)

# #         #         ports = portList.parse(s)
# #         #         nodeDb = NodeDB()
# #         #         portlists = nodeDb.read_nodes()
# #         #         for port in ports:
# #         #             if port not in portlists:
# #         #                 nodeDb.write(port)

# #         #     if envelope.command == b'block':
# #         #         blockObj = Block.parse(envelope.stream())
# #         #         print("DEBUG: envelope payload length =", len(envelope.payload))
# #         #         print("DEBUG: envelope payload hex =", envelope.payload.hex())
# #         #         BlockHeaderObj = BlockHeader(blockObj.BlockHeader.version,
# #         #                   blockObj.BlockHeader.prevBlockHash,
# #         #                   blockObj.BlockHeader.merkleRoot,
# #         #                   blockObj.BlockHeader.timestamp,
# #         #                   blockObj.BlockHeader.bits,
# #         #                   blockObj.BlockHeader.nonce)
              
# #         #         if BlockHeaderObj.validateBlock():
# #         #             for idx,tx in enumerate(blockObj.Txs):
# #         #                 tx.TxId = tx.id()
# #         #                 blockObj.Txs[idx] = tx.to_dict()
                
                      
# #         #             BlockHeaderObj.blockHash = BlockHeaderObj.generateBlockHash()
# #         #             BlockHeaderObj.prevBlockHash = BlockHeaderObj.prevBlockHash.hex()
# #         #             BlockHeaderObj.merkleRoot = BlockHeaderObj.merkleRoot.hex()
# #         #             BlockHeaderObj.nonce = little_endian_to_int(BlockHeaderObj.nonce)
# #         #             BlockHeaderObj.bits = BlockHeaderObj.bits.hex()

# #         #             blockObj.BlockHeader = BlockHeaderObj

# #         #             BlockchainDB().write([blockObj.to_dict()])

# #         #             print(f"Block Received - {blockObj.Height}")
# #         #         else:
# #         #             self.secondaryChain[BlockHeaderObj.generateBlockHash()] = blockObj



# from io import BytesIO
# import socket
# import time
# from Blockchain.Backend.core.network.connection import Node
# from Blockchain.Backend.core.database.db import BlockchainDB, NodeDB, AccountDB
# from Blockchain.Backend.core.blockheader import BlockHeader
# from Blockchain.Backend.core.network.network import requestBlock, NetworkEnvelope, FinishedSending, portList
# from Blockchain.Backend.core.Tx import Tx, TxIn, TxOut
# from Blockchain.Backend.core.block import Block
# from Blockchain.Backend.util.util import little_endian_to_int, int_to_little_endian
# from Blockchain.client.account import account
# from Blockchain.Backend.core.EllepticCurve.EllepticCurve import Signature
# from threading import Thread
# import traceback

# import json

# ZERO_HASH = "0" * 64


# class syncManager:
#     """
#         Initialize the sync manager.
        
#         Args:
#             host: The host address to connect to
#             port: The port to connect to
#             blockchain: The blockchain instance (optional for transaction broadcasting)
#             localHostPort: The local port (optional for transaction broadcasting)
#     """
#     def __init__(self, host, port, MemoryPool ,blockchain=None, localHostPort=None, newBlockAvailable=None,secondaryChain=None, my_public_addr=None):
#         self.host = host
#         self.port = port
#         self.blockchain = blockchain
#         self.newBlockAvailable = {} if newBlockAvailable is None else newBlockAvailable        
#         self.secondaryChain = secondaryChain
#         self.MemoryPool = MemoryPool if MemoryPool is not None else {}
#         self.localHostPort = localHostPort
#         self.my_public_addr = my_public_addr  # Store the node's public address here

#     def spinUpServer(self):
#         self.server = Node(self.host, self.port)
#         self.server.startServer()
#         print("SERVER STARTED")
#         print(f"LISTENING at {self.host}:{self.port}")    

#         while True:
#             self.conn, self.addr = self.server.acceptConnection()
#             handleConn = Thread(target=self.handleConnection)
#             handleConn.start()

#     def handleConnection(self):
#         # --- PORTCHECK MAGIC HANDLING ---
#         try:
#             # Peek at the first 9 bytes to check for port check magic
#             portcheck_magic = self.conn.recv(9, socket.MSG_PEEK)
#             if portcheck_magic == b'PORTCHECK':
#                 self.conn.recv(9)  # Consume the bytes
#                 print("[syncManager] Received port check magic, closing connection.")
#                 self.conn.close()
#                 return
#         except Exception as e:
#             print(f"[syncManager] Error checking for port check magic: {e}")
#             self.conn.close()
#             return
#         # --- END PORTCHECK MAGIC HANDLING ---
#         from Blockchain.Backend.core.blockchain import ZERO_HASH
#         envelope = self.server.read()
#         try:
#             if len(str(self.addr[1]))== 4:
#                 self.addNode()
            
#             if envelope.command == b'tx':
#                 Transaction = Tx.parse(envelope.stream())
#                 print(f"[DEBUG] Incoming TX serialized hex: {Transaction.serialise().hex()}")
#                 print(f"[DEBUG] Incoming TX TxId: {Transaction.id()}")
#                 calculated_txid = Transaction.id()
#                 Transaction.TxId = Transaction.id()
#                 if calculated_txid != Transaction.TxId:
#                         raise ValueError(f"TxId Mismatch! Calculated: {calculated_txid}, Received: {Transaction.TxId}")
#                 print(f"Transaction Received : {Transaction.TxId}")
                
#                 self.MemoryPool[Transaction.TxId] = Transaction
#                 print(f"[DEBUG] MemoryPool now has: {list(self.MemoryPool.keys())}")

#             elif envelope.command == b'block':
#                 print(f"[Receiver] Received envelope with command: {envelope.command} and payload length: {len(envelope.payload)} bytes")
#                 # print("THIS IS WORKING")
#                 blockObj = Block.parse(envelope.stream())
                
#                 # Check if the header's signature is already a Signature instance; if not, convert it.
                
#                 sig_field = blockObj.BlockHeader.signature
#                 # print(f"Signature field type: {type(sig_field)}")
#                 if sig_field and not isinstance(sig_field, Signature):
#                     try:
#                         blockObj.BlockHeader.signature = Signature.parse(sig_field)
#                         print(f"Successfully parsed signature: {blockObj.BlockHeader.signature}")
#                     except Exception as e:
#                         print(f"Error parsing signature in handleConnection: {e}")
#                         # Don't proceed with invalid signature
#                         raise ValueError("Failed to parse signature")
                
#                 # No need to create a new BlockHeader object - we've already fixed the signature in the original
#                 # First check and convert each field properly
#                 prev_block_hash = blockObj.BlockHeader.prevBlockHash.hex() if isinstance(blockObj.BlockHeader.prevBlockHash, bytes) else blockObj.BlockHeader.prevBlockHash
#                 merkle_root = blockObj.BlockHeader.merkleRoot.hex() if isinstance(blockObj.BlockHeader.merkleRoot, bytes) else blockObj.BlockHeader.merkleRoot
#                 validator_pubkey = blockObj.BlockHeader.validator_pubkey.hex() if isinstance(blockObj.BlockHeader.validator_pubkey, bytes) else blockObj.BlockHeader.validator_pubkey
                

#                 # Create the test_dict with properly converted values
#                 reconstructed_dict = BlockHeader(
#                     blockObj.BlockHeader.version,
#                     to_bytes_field(prev_block_hash),
#                     to_bytes_field(merkle_root),
#                     blockObj.BlockHeader.timestamp,
#                     to_bytes_field(validator_pubkey),
#                     blockObj.BlockHeader.signature  # Already a Signature object!
#                 )
#                 print(f"[HANDLECONN_DEBUG] Reconstructed BlockHeader: {reconstructed_dict}")
#                 # print(test_dict.__dict__)
#                 print(f"[HANDLECONN_DEBUG]Signature: {reconstructed_dict.signature} {type(reconstructed_dict.signature)}")
#                 print(f"[HANDLECONN_DEBUG]Serialized header: {reconstructed_dict.serialise_with_signature().hex()}")   

#                 # Generate a block hash from the existing header
#                 reconstructed_dict.blockHash = reconstructed_dict.generateBlockHash()
#                 # print(f"Reconstructed block hash: {reconstructed_dict.blockHash}")
#                 block_hash = reconstructed_dict.blockHash
#                 # Safety check before assignment
#                 if self.newBlockAvailable is None:
#                     print("Warning: newBlockAvailable was None, reinitializing...")
#                     self.newBlockAvailable = {}
                    
#                 self.newBlockAvailable[block_hash] = blockObj
#                 print(f"New Block Received : {blockObj.Height}")

#                 self.processReceivedBlocks()
#                 time.sleep(2) # Allow time for processing
#                 self.blockchain.buildUTXOS()

#             if envelope.command == requestBlock.command:
#                 start_block, end_block = requestBlock.parse(envelope.stream())
#                 self.sendBlockToRequestor(start_block)
#                 print(f"Start Block is {start_block} \n End Block is {end_block}")
        
#             if envelope.command == b'valselect':
#                 # This is the validator node telling a selected node to produce a block.
#                 print("[syncManager] Received validator selection message.")
#                 payload = envelope.payload.decode()
#                 # print('[DEBUG] payload:', payload)
#                 message = json.loads(payload)
#                 if message.get("type") == "validator_selection":
#                     selected_validator = message["selected_validator"]                   
                    
#                     print(f"[DEBUG] Selected validator: {selected_validator}")
#                     print(f"[DEBUG] My public address: {self.my_public_addr}")
                    
#                     # Get current node's account
#                     my_account = None
#                     try:
#                         from Blockchain.client.account import account
#                         my_account = account.get_account(self.my_public_addr)
#                     except Exception as e:
#                         print(f"Error getting account: {e}")
                        
#                     # Compare addresses properly
#                     validator_address = None
#                     if isinstance(selected_validator, dict) and 'public_addr' in selected_validator:
#                         validator_address = selected_validator['public_addr']
#                     elif isinstance(selected_validator, str):
#                         validator_address = selected_validator
                        
#                     # Determine if this node is the validator
#                     is_validator = False
#                     if my_account and validator_address:
#                         is_validator = (my_account.public_addr.strip() == validator_address.strip())
#                     elif self.my_public_addr and validator_address:
#                         is_validator = (self.my_public_addr.strip() == validator_address.strip())
                        
#                     if is_validator:
#                         # We are the chosen validator. Produce a block now.
#                         print(f"[syncManager] I AM THE SELECTED VALIDATOR! - Address {self.my_public_addr} Producing next block.")

#                         # print(f"[syncManager] Blockchain type: {type(self.blockchain)}")
                        
#                         # Use the existing blockchain reference to create a block
#                         blockchainDB = BlockchainDB()
#                         lastBlock = blockchainDB.lastBlock()
                        
#                         if lastBlock:
#                             blockHeight = lastBlock[0]['Height'] + 1
#                             prevBlockHash = lastBlock[0]['BlockHeader']['blockHash']
#                             # NEW: Check if there are any pending blocks at this height in the network
#                             # This is a simple 2-second delay to allow any existing blocks to arrive
#                             print(f"[syncManager] I'm selected as validator. Waiting briefly for any competing blocks...")
#                             time.sleep(2)  # Brief wait to allow competing blocks to arrive
        
#                             # Check if another block has arrived during our wait
#                             freshLastBlock = blockchainDB.lastBlock()
#                             if freshLastBlock and freshLastBlock[0]['Height'] >= blockHeight:
#                                 print(f"[syncManager] Another validator has already created block {blockHeight}. Skipping creation.")
#                                 return
                                
#                             print(f"[syncManager] I AM THE SELECTED VALIDATOR! Creating block at height {blockHeight}")
#                         else:
#                             print("[syncManager] I am the selected validator, creating genesis block.")
#                             self.blockchain.GenesisBlock()
#                             print("[syncManager] Genesis block created and broadcast.")
#                             return
                            
                        
#                         try:
#                             print(f"[syncManager] Creating block at height {blockHeight}")
#                             # Use our existing blockchain reference
#                             print(f"[syncManager/DEBUG] MEMPOOL CONTENTS: {self.MemoryPool}")
#                             self.blockchain.addBlock(blockHeight, prevBlockHash, selected_validator)
#                             print(f"[syncManager] Block {blockHeight} created successfully")

#                         except Exception as e:
#                             print(f"[syncManager] Error creating block: {e}")
#                             traceback.print_exc()
                            
#                             # Fallback: Create block directly if blockchain.addBlock fails
#                             # self.createBlockDirectly(blockHeight, prevBlockHash, selected_validator)
#                             print("[syncManager] Add block failed")
#                     else:
#                         print(f"[syncManager] Not the selected validator: {validator_address}")

                        
#             elif envelope.command == b'account':
#                 try:
#                     # Parse the account update message
#                     payload = envelope.payload.decode()
#                     message = json.loads(payload)
                    
#                     if message.get('type') == 'account_update':
#                         address = message.get('address')
#                         account_data = message.get('data')
#                         sender_port = message.get('sender_port')
                        
#                         print(f"Received account update from port {sender_port} for address: {address}")
                        
#                         # Update the local database with the received account data         
#                         # Create a consistent account object that can be saved to the database
#                         account_db = AccountDB()
#                         account_db.update_account(address, json.dumps(account_data))
                        
#                         print(f"Successfully updated local account database for {address}")
#                 except Exception as e:
#                     print(f"Error processing account update: {e}")

            
#             self.conn.close()
#         except Exception as e:
#             self.conn.close()
#             print(f"Error While processing the client request \n {e}")


#     def addNode(self):
#         nodeDb = NodeDB()
#         portList = nodeDb.read()
#         print(f"Current ports in database: {portList}")

#         if self.addr[1] and (self.addr[1]+ 1 ) not in portList:
#             new_port = self.addr[1] + 1
#             nodeDb.write(new_port)
#             print(f"Added new port: {new_port}")

#     def sendBlockToRequestor(self, start_block):
#         blocksToSend = self.fetchBlocksFromBlockchain(start_block)

#         try:
#             self.sendBlock(blocksToSend)
#             self.sendPortList()
#             self.sendFinishedMessage()
#         except Exception as e:
#             print(f"Unable to send the blocks \n {e}")

#     def sendPortList(self):
#         nodeDB = NodeDB()
#         ports = nodeDB.read_nodes()
#         if ports is None:
#             raise ValueError("No nodes found in the NodeDB.")

#         portlist = portList(ports)
#         envelope = NetworkEnvelope(portlist.command, portlist.serialise())
#         self.conn.sendall(envelope.serialise())
    
#     # def sendSecondaryChain(self):
#     #     TempSecChain = dict(self.secondaryChain)
#     #     for blockHash in TempSecChain:
#     #         envelope = NetworkEnvelope(TempSecChain[blockHash].command, TempSecChain[blockHash].serialise())
#     #         self.conn.sendall(envelope.serialise())

#     def sendFinishedMessage(self):
#         MessageFinish = FinishedSending()
#         envelope = NetworkEnvelope(MessageFinish.command, MessageFinish.serialise())
#         self.conn.sendall(envelope.serialise())
      
#     def sendBlock(self, blockstosend):
#         for block in blockstosend:
#             cblock = Block.to_obj(block)
#             envelope = NetworkEnvelope(cblock.command, cblock.serialise())
#             self.conn.sendall(envelope.serialise())
#             print(f'block sent {cblock.Height}')
    

#     def processReceivedBlocks(self):
#         """
#         Process and store all blocks received in self.newBlockAvailable, with conflict
#         resolution and atomic database writes.
#         """
#         # Ensure these dictionaries exist.
#         if not hasattr(self, 'newBlockAvailable') or self.newBlockAvailable is None:
#             self.newBlockAvailable = {}
#         if not hasattr(self, 'secondaryChain') or self.secondaryChain is None:
#             self.secondaryChain = {}

#         # Obtain direct references to UTXOs and mempool for in-place updating.
#         utxos = self.blockchain.utxos if hasattr(self.blockchain, 'utxos') else {}
#         mem_pool = self.blockchain.mem_pool if hasattr(self.blockchain, 'mem_pool') else {}

#         deleteBlocks = []

#         # Create a safe copy of newBlockAvailable to iterate through.
#         try:
#             tempBlocks = dict(self.newBlockAvailable)
#         except Exception as e:
#             print(f"Error copying newBlockAvailable: {e}")
#             tempBlocks = {}

#         print(f"Blocks to process: {len(tempBlocks)}")

#         # Initialize a BlockchainDB instance for reading the current chain state.
#         db = BlockchainDB()

#         for blockHash, block in tempBlocks.items():
#             try:
#                 # Robustly extract a dict representation of the block
#                 if isinstance(block, list):
#                     block_dict = block[0]
#                 elif isinstance(block, dict):
#                     block_dict = block
#                 elif hasattr(block, "to_dict"):
#                     block_dict = block.to_dict()
#                 else:
#                     print(f"[syncManager] Unexpected block type: {type(block)} for blockHash {blockHash}")
#                     continue

#                 block_height = block_dict['Height']
#                 block_hash = block_dict['BlockHeader']['blockHash']


#                 blockchainDB = BlockchainDB()
#                 last_block = blockchainDB.lastBlock()
#                 if last_block:
#                     last_block_height = last_block[0]['Height']
#                     last_block_hash = last_block[0]['BlockHeader']['blockHash']
#                     # If block at this height and hash already exists, skip processing
#                     if last_block_height == block_height and last_block_hash == block_hash:
#                         print(f"[syncManager] Block at height {block_height} with hash {block_hash} already exists. Skipping.")
#                         continue

#                 print(f"Processing block with hash: {blockHash[:8]}...")
                
#                 # Add blockHash to deletion list regardless of outcome, to avoid reprocessing.
#                 deleteBlocks.append(blockHash)

#                 # Ensure the block has a valid BlockHeader.
#                 if not hasattr(block, 'BlockHeader') or block.BlockHeader is None:
#                     print("Error: Block has no BlockHeader")
                    

#                 # If the BlockHeader already has a signature (and we assume it should be parsed),
#                 # skip processing if not already handled.
#                 if hasattr(block.BlockHeader, 'signature'):
#                     print(f"Signature type: {type(block.BlockHeader.signature)}")
#                     # If the signature is already processed, skip this block.
                    
#                  # --- PATCH START: Always reconstruct BlockHeader from dict and parse signature ---
#                 if isinstance(block.BlockHeader, dict):
#                     header_data = block.BlockHeader
#                     sig_field = header_data.get('signature')
#                     signature_obj = None

#                     # Always parse the signature as a Signature object
#                     if isinstance(sig_field, Signature):
#                         signature_obj = sig_field
#                     elif isinstance(sig_field, bytes):
#                         signature_obj = Signature.parse(sig_field)
#                     elif isinstance(sig_field, str) and sig_field:
#                         signature_obj = Signature.parse(bytes.fromhex(sig_field))
#                     else:
#                         print(f"Error: signature field is not a valid type: {type(sig_field)}")
#                         self.secondaryChain[blockHash] = block
#                         print(f"[LocalChain] Block with invalid signature stored for review.")
#                         continue

#                     # Now reconstruct the BlockHeader with the correct signature object
#                     BlockHeaderObj = BlockHeader(
#                         version=header_data['version'],
#                         prevBlockHash=to_bytes_field(header_data['prevBlockHash']),
#                         merkleRoot=to_bytes_field(header_data['merkleRoot']),
#                         timestamp=header_data['timestamp'],
#                         validator_pubkey=to_bytes_field(header_data['validator_pubkey']),
#                         signature=signature_obj
#                     )
#                 else:
#                     BlockHeaderObj = block.BlockHeader
#                     # If signature is not a Signature object, parse it
#                     if hasattr(BlockHeaderObj, 'signature') and BlockHeaderObj.signature and not isinstance(BlockHeaderObj.signature, Signature):
#                         BlockHeaderObj.signature = Signature.parse(BlockHeaderObj.signature)
#                     if not hasattr(BlockHeaderObj, 'signature') or BlockHeaderObj.signature is None:
#                         print("Error: Block header has no signature")
#                         self.secondaryChain[blockHash] = block
#                         print(f"[LocalChain] Block with no signature stored for review.")
#                         continue
#                 # --- PATCH END ---
#                 # Process BlockHeader from dictionary if needed.
#                 # if isinstance(block.BlockHeader, dict):
#                 #     header_data = block.BlockHeader
#                 #     signature_obj = None
#                 #     sig_field = header_data.get('signature')

#                 #     if isinstance(sig_field, Signature):
#                 #         signature_obj = sig_field
#                 #     elif isinstance(sig_field, bytes):
#                 #         try:
#                 #             signature_obj = Signature.parse(sig_field)
#                 #             print(f"Successfully parsed signature from bytes: {signature_obj}")
#                 #         except Exception as e:
#                 #             print(f"Error parsing signature from bytes: {e}")
#                 #             self.secondaryChain[blockHash] = block
#                 #             print(f"[LocalChain] Block with invalid signature stored for review.")
#                 #             continue
#                 #     elif isinstance(sig_field, str) and sig_field:
#                 #         try:
#                 #             sig_bytes = bytes.fromhex(sig_field)
#                 #             signature_obj = Signature.parse(sig_bytes)
#                 #             print(f"Successfully parsed signature from hex string: {signature_obj}")
#                 #         except Exception as e:
#                 #             print(f"Error parsing signature from hex string: {e}")
#                 #             self.secondaryChain[blockHash] = block
#                 #             print(f"[LocalChain] Block with invalid signature stored for review.")
#                 #             continue
#                 #     else:
#                 #         print(f"Error: signature field is not a valid type: {type(sig_field)}")
#                 #         self.secondaryChain[blockHash] = block
#                 #         print(f"[LocalChain] Block with invalid signature stored for review.")
#                 #         continue

#                 #     try:
#                 #         BlockHeaderObj = BlockHeader(
#                 #             version=header_data['version'],
#                 #             prevBlockHash=to_bytes_field(header_data['prevBlockHash']),
#                 #             merkleRoot=to_bytes_field(header_data['merkleRoot']),
#                 #             timestamp=header_data['timestamp'],
#                 #             validator_pubkey=to_bytes_field(header_data['validator_pubkey']),
#                 #             signature=signature_obj
#                 #         )
#                 #     except Exception as e:
#                 #         print(f"Error creating BlockHeader: {e}")
#                 #         continue
                    
#                     # --- ADD DEBUG PRINTS HERE ---
#                     print(f"[DEBUG/PRB] BlockHeader fields for block {blockHash}:")
#                     print(f"  version: {BlockHeaderObj.version}")
#                     print(f"  prevBlockHash: {BlockHeaderObj.prevBlockHash} ({type(BlockHeaderObj.prevBlockHash)})")
#                     print(f"  merkleRoot: {BlockHeaderObj.merkleRoot} ({type(BlockHeaderObj.merkleRoot)})")
#                     print(f"  timestamp: {BlockHeaderObj.timestamp}")
#                     print(f"  validator_pubkey: {BlockHeaderObj.validator_pubkey} ({type(BlockHeaderObj.validator_pubkey)})")
#                     print(f"  signature: {BlockHeaderObj.signature} ({type(BlockHeaderObj.signature)})")
#                     print(f"  serialized header (with sig): {BlockHeaderObj.serialise_with_signature().hex()}")
#                     print(f"  serialized header (no sig): {BlockHeaderObj.serialise_without_signature().hex()}")
#                     print(f"  computed block hash: {BlockHeaderObj.generateBlockHash()}")
#                     # --- END DEBUG PRINTS ---
#                 # else:
#                 #     BlockHeaderObj = block.BlockHeader
#                 #     if hasattr(BlockHeaderObj, 'signature') and BlockHeaderObj.signature and not isinstance(BlockHeaderObj.signature, Signature):
#                 #         try:
#                 #             BlockHeaderObj.signature = Signature.parse(BlockHeaderObj.signature)
#                 #             print(f"Successfully parsed signature: {BlockHeaderObj.signature}")
#                 #         except Exception as e:
#                 #             print(f"Error parsing signature from object: {e}")
#                 #             self.secondaryChain[blockHash] = block
#                 #             print(f"[LocalChain] Block with invalid signature stored for review.")
#                 #             continue

#                     if not hasattr(BlockHeaderObj, 'signature') or BlockHeaderObj.signature is None:
#                         print("Error: Block header has no signature")
#                         self.secondaryChain[blockHash] = block
#                         print(f"[LocalChain] Block with no signature stored for review.")
#                         continue
                
#                 print(f"[DEBUG/PRB] BlockHeader fields for block {blockHash}:")
#                 print(f"  version: {BlockHeaderObj.version}")
#                 print(f"  prevBlockHash: {BlockHeaderObj.prevBlockHash} ({type(BlockHeaderObj.prevBlockHash)})")
#                 print(f"  merkleRoot: {BlockHeaderObj.merkleRoot} ({type(BlockHeaderObj.merkleRoot)})")
#                 print(f"  timestamp: {BlockHeaderObj.timestamp}")
#                 print(f"  validator_pubkey: {BlockHeaderObj.validator_pubkey} ({type(BlockHeaderObj.validator_pubkey)})")
#                 print(f"  signature: {BlockHeaderObj.signature} ({type(BlockHeaderObj.signature)})")
#                 print(f"  serialized header (with sig): {BlockHeaderObj.serialise_with_signature().hex()}")
#                 print(f"  serialized header (no sig): {BlockHeaderObj.serialise_without_signature().hex()}")
#                 print(f"  computed block hash: {BlockHeaderObj.generateBlockHash()}")
                                        

#                 # Before validation, check for a block height conflict.
#                 # (Assuming block.Height is present and your db provides a read_all_blocks method.)
#                 if hasattr(block, 'Height'):
#                     existing_blocks = []
#                     all_blocks = db.read_all_blocks()  # You may need to add this method if not present.
#                     for existing in all_blocks:
#                         if existing[0]['Height'] == block.Height:
#                             existing_blocks.append(existing[0])
#                     if existing_blocks:
#                         # Apply a simple resolution: choose the block with the lower blockHash (string comparison).
#                         existing_hash = existing_blocks[0]['BlockHeader']['blockHash']
#                         if blockHash > existing_hash:
#                             print(f"Conflict at height {block.Height}: keeping existing block with hash {existing_hash[:8]}")
                            
#                         else:
#                             print(f"Conflict at height {block.Height}: replacing existing block with new block {blockHash[:8]}")

#                 # Validate the block header.
#                 validation_result = False
#                 try:
#                     validation_result = BlockHeaderObj.validate_block()
#                 except Exception as e:
#                     print(f"Error during block validation: {e}")

#                 if validation_result:
#                     # Create dictionary for database storage.
#                     header_dict = {
#                         'version': BlockHeaderObj.version,
#                         'prevBlockHash': BlockHeaderObj.prevBlockHash.hex() if isinstance(BlockHeaderObj.prevBlockHash, bytes) else BlockHeaderObj.prevBlockHash,
#                         'merkleRoot': BlockHeaderObj.merkleRoot.hex() if isinstance(BlockHeaderObj.merkleRoot, bytes) else BlockHeaderObj.merkleRoot,
#                         'timestamp': BlockHeaderObj.timestamp,
#                         'validator_pubkey': BlockHeaderObj.validator_pubkey.hex() if isinstance(BlockHeaderObj.validator_pubkey, bytes) else BlockHeaderObj.validator_pubkey,
#                         'signature': BlockHeaderObj.signature.der().hex() if hasattr(BlockHeaderObj.signature, 'der') else '',
#                         'blockHash': blockHash
#                     }

#                     # Process transactions
#                     for idx, tx in enumerate(block.Txs):
#                         try:
#                             tx_obj = tx if hasattr(tx, 'tx_ins') else Tx.to_obj(tx)
#                             tx_id = tx_obj.id()
#                             tx_dict = tx_obj.to_dict()
#                             tx_dict['TxId'] = tx_id
#                             block.Txs[idx] = tx_dict

#                             if utxos is not None:
#                                 try:
#                                     local_utxos = dict(utxos)
#                                     # Add new outputs as (txid, index): tx_out
#                                     for out_idx, tx_out in enumerate(tx_obj.tx_outs):
#                                         local_utxos[(tx_id, out_idx)] = tx_out
#                                     # Remove spent outputs by (prev_txid, prev_index)
#                                     for txin_data in tx_obj.tx_ins:
#                                         txin_obj = None
#                                         if isinstance(txin_data, TxIn):
#                                             txin_obj = txin_data
#                                         elif isinstance(txin_data, dict):
#                                             txin_obj = TxIn(
#                                                 prev_tx=bytes.fromhex(txin_data['prev_tx']),
#                                                 prev_index=txin_data['prev_index'],
#                                                 script_sig=txin_data.get('script_sig', b''),
#                                                 sequence=txin_data.get('sequence', 0xffffffff)
#                                             )
#                                         if txin_obj:
#                                             spent_key = (txin_obj.prev_tx.hex(), txin_obj.prev_index)
#                                             if spent_key in local_utxos:
#                                                 del local_utxos[spent_key]
#                                     utxos.clear()
#                                     for k, v in local_utxos.items():
#                                         utxos[k] = v
#                                 except Exception as e:
#                                     print(f"UTXO update failed (non-critical): {e}")
#                                     import traceback
#                                     traceback.print_exc() # Print full traceback for debugging UTXO errors

#                             if mem_pool is not None:
#                                 try:
#                                     if tx_id in mem_pool:
#                                         del mem_pool[tx_id]
#                                 except Exception as e:
#                                     print(f"Mempool update failed (non-critical): {e}")

#                             print(f"Processed transaction with ID: {tx_id}")
#                         except Exception as e:
#                             print(f"Error processing transaction: {e}")

#                     # Assemble block dictionary and write atomically.
#                     block_dict = block.to_dict()
#                     block_dict['BlockHeader'] = header_dict

#                     import json
#                     print(f"Attempting atomic write of block to database file: {db.filepath}")
#                     # print(f"Block dict to be written:\n{json.dumps(block_dict, indent=2)}")

#                     try:
#                         db.conn.execute("BEGIN TRANSACTION")
#                         db.write([block_dict])
#                         db.conn.commit()
#                         print(f"[LocalChain] Block {block.Height if hasattr(block, 'Height') else '?'} successfully integrated (atomic write).")
#                         # --- START: Add this block ---
#                         # If this is the Genesis block and we haven't started sync yet, start it now
#                         if hasattr(self.blockchain, 'needs_genesis') and self.blockchain.needs_genesis:
#                             if hasattr(block, 'Height') and block.Height == 0:
#                                 self.blockchain.needs_genesis = False
#                                 print("[syncManager] Genesis block received and written. Starting sync process.")
#                                 self.blockchain.startSync()
#                         # --- END: Add this block ---

#                     except Exception as e:
#                         db.conn.rollback()
#                         print(f"Error writing block to database file {db.filepath}: {e}")

#                 else:
#                     self.secondaryChain[blockHash] = block
#                     print(f"[LocalChain] Block {block.Height if hasattr(block, 'Height') else 'unknown'} is invalid. Stored for review.")
                    
#             except Exception as e:
#                 print(f"Validation Error for block {blockHash[:8]}: {e}")
#                 import traceback
#                 traceback.print_exc()
#                 if hasattr(self, 'secondaryChain') and blockHash in self.newBlockAvailable:
#                     self.secondaryChain[blockHash] = block
#                     print(f"[LocalChain] Block {block.Height if hasattr(block, 'Height') else 'unknown'} stored for review due to exception.")

#         # Finally, remove all blocks that were processed from the newBlockAvailable dictionary.
#         for bh in deleteBlocks:
#             if bh in self.newBlockAvailable:
#                 del self.newBlockAvailable[bh]
        
#         if hasattr(self.blockchain, 'buildUTXOS'):
#             self.blockchain.buildUTXOS()
#             print("[DEBUG] UTXO set rebuilt.")
#         self.clean_mempool_against_chain(mem_pool=self.MemoryPool)
#         print("[DEBUG] Mempool cleaned against chain.")


#     def fetchBlocksFromBlockchain(self, start_Block):
#         fromBlockOnwards = start_Block.hex()

#         blocksToSend = []

#         blockchain = BlockchainDB()
#         blocks = blockchain.read()

#         foundBlock = False
#         for block in blocks:
#             if block[0]['BlockHeader']['blockHash'] == fromBlockOnwards:
#                 foundBlock = True
#                 continue

#             if foundBlock:
#                 blocksToSend.append(block)

#         return blocksToSend
    
#     def connectToHost(self, localport, port, bindPort = None):
#         self.connect = Node(self.host, port)
#         if bindPort:
#             self.socket = self.connect.connect(localport, bindPort)
#             print(f"Trying to connect from {localport} to: {port}...")
#         else:
#             self.socket = self.connect.connect(localport)
#             print(f"Trying to connect from {localport}: to: {port}...")

#         self.stream = self.socket.makefile('rb', None)
#         return self.socket


#     # def publishTx(self,Tx):
#     #     self.connect.send(Tx)

#     def publishTx(self, tx_obj):
#         try:
#             # Use connectToHost to get a socket (binding from self.localHostPort if needed)
#             sock = self.connectToHost(self.localHostPort, self.port)
#             # Wrap the transaction in a NetworkEnvelope
#             envelope = NetworkEnvelope(tx_obj.command, tx_obj.serialise())
#             sock.sendall(envelope.serialise())
#             sock.close()
#             print(f"Published Tx {tx_obj.TxId} to {self.host}:{self.port}")
#         except Exception as e:
#             print(f"Error publishing Tx to port {self.port}: {e}")
        
#     def publishBlock(self, localport, port, block):
#         # print(f"[Debug] publish block printing: {block.__dict__}")
#         self.connectToHost(localport, port)
#         print('Connected to host')
#         # print(f"[Sender] Sending block {block.Height} with hash {block.BlockHeader.blockHash} and size {len(block_bytes)} bytes")
#         self.connect.send(block)

#     def publish_account_update(self, sender_port, receiver_port, address, account_data):
#         """Send account updates to other nodes"""
#         try:
#             print(f"Publishing account update for {address} to node at port {receiver_port}")
            
#             # Connect to the target node
#             self.connectToHost(sender_port, receiver_port)
#             print(f"Connected to host at port {receiver_port}")
            
#             # Create a properly formatted message object
#             from Blockchain.Backend.core.network.network import AccountUpdateMessage
#             msg = AccountUpdateMessage(sender_port, address, account_data)
            
#             # Send exactly like you send blocks
#             self.connect.send(msg)
#             print(f"Account update for {address} sent to port {receiver_port}")
#             return True
#         except Exception as e:
#             print(f"Error in publish_account_update: {e}")
#             import traceback
#             traceback.print_exc()
#             return False

#     def startDownload(self, localport, port, bindPort):
#         print("Starting download...")
#         lastBlock = BlockchainDB().lastBlock()

#         if not lastBlock:
#             lastBlockHeader = "a73b050e2d0d1f030f7b29def74e0471a9a65f868e4ac21d3ba6267c2eb74909" # Genesis block hash
#         else:
#             lastBlockHeader = lastBlock[0]['BlockHeader']['blockHash']

#         startBlock = bytes.fromhex(lastBlockHeader)

#         getHeaders = requestBlock(startBlock=startBlock)
#         self.connectToHost(localport, port, bindPort)
#         print(f"localport value: {localport}, type: {type(localport)}")
#         self.connect.send(getHeaders)

#         while True:
#             envelope = NetworkEnvelope.parse(self.stream)
#             print("DEBUG: Envelope command =", envelope.command)
#             print("DEBUG: Envelope length =", len(envelope.payload))

#             if envelope.command == b'Finished':
#                 blockObj = FinishedSending.parse(envelope.stream())
#                 print(f'All blocks receieved')
#                 self.socket.close()
#                 break

#             if envelope.command == b'portlist':
#                 s = envelope.stream()
#                 raw_data = s.read()
#                 print("DEBUG: envelope stream bytes =", raw_data.hex())
#                 s.seek(0)

#                 ports = portList.parse(s)
#                 nodeDb = NodeDB()
#                 portlists = nodeDb.read_nodes()
#                 for port in ports:
#                     if port not in portlists:
#                         nodeDb.write(port)

#             if envelope.command == b'block':
#                 blockObj = Block.parse(envelope.stream())
#                 print("DEBUG: envelope payload length =", len(envelope.payload))
#                 print("DEBUG: envelope payload hex =", envelope.payload.hex())
#                 BlockHeaderObj = BlockHeader(blockObj.BlockHeader.version,
#                           blockObj.BlockHeader.prevBlockHash,
#                           blockObj.BlockHeader.merkleRoot,
#                           blockObj.BlockHeader.timestamp,
#                           blockObj.BlockHeader.validator_pubkey,
#                           blockObj.BlockHeader.signature)
              
#                 if BlockHeaderObj.validate_block():
#                     for idx,tx in enumerate(blockObj.Txs):
#                         tx.TxId = tx.id()
#                         blockObj.Txs[idx] = tx.to_dict()
                      
#                     BlockHeaderObj.blockHash = BlockHeaderObj.generateBlockHash()
#                     BlockHeaderObj.prevBlockHash = BlockHeaderObj.prevBlockHash.hex()
#                     BlockHeaderObj.merkleRoot = BlockHeaderObj.merkleRoot.hex()

#                     blockObj.BlockHeader = BlockHeaderObj

#                     BlockchainDB().write([blockObj.to_dict()])

#                     print(f"Block Received - {blockObj.Height}")
#     # Add a wrapper method to handle blockchain operations safely

#     # def clean_mempool_against_chain(self, mem_pool, blockchain):
#     #     """
#     #     Remove transactions from mem_pool that are already confirmed in the blockchain.
#     #     Should be called after processing new blocks and before block creation.
#     #     """
#     #     confirmed_txids = set()
#     #     try:
#     #         for block in blockchain.get_all_blocks():
#     #             for tx in getattr(block, 'Txs', []):
#     #                 txid = None
#     #                 # Try to extract TxId from object or dict
#     #                 if hasattr(tx, "TxId") and tx.TxId:
#     #                     txid = tx.TxId
#     #                 elif hasattr(tx, "id"):
#     #                     try:
#     #                         txid = tx.id()
#     #                     except Exception:
#     #                         pass
#     #                 elif isinstance(tx, dict) and "TxId" in tx:
#     #                     txid = tx["TxId"]
#     #                 if txid:
#     #                     confirmed_txids.add(txid)
#     #                 else:
#     #                     print(f"[Mempool Cleanup] Warning: Could not extract TxId from tx: {tx}")
#     #     except Exception as e:
#     #         print(f"[Mempool Cleanup] Error while collecting confirmed txids: {e}")
#     #     print(f"[Mempool Cleanup] mem_pool keys: {list(mem_pool.keys())}")
#     #     print(f"[Mempool Cleanup] confirmed_txids: {confirmed_txids}")
#     #     removed = []
#     #     for txid in list(mem_pool.keys()):
#     #         if txid in confirmed_txids:
#     #             del mem_pool[txid]
#     #             removed.append(txid)
#     #     if removed:
#     #         print(f"[Mempool Cleanup] Removed confirmed transactions from mempool: {removed}")
#     #     else:
#     #         print("[Mempool Cleanup] No confirmed transactions found in mempool.")

#     def clean_mempool_against_chain(self, mem_pool, blockchain=None):
#         """
#         Remove transactions from mem_pool that are already confirmed in the blockchain.
#         Should be called after processing new blocks and before block creation.
#         """
#         from Blockchain.Backend.core.database.db import BlockchainDB
#         confirmed_txids = set()
#         try:
#             db = BlockchainDB()
#             blocks = db.read_all_blocks()
#             for block in blocks:
                
#                 block_obj = block[0] if isinstance(block, (list, tuple)) else block
#                 for tx in block_obj.get('Txs', []):
#                     txid = None
#                     if isinstance(tx, dict) and "TxId" in tx:
#                         txid = str(tx["TxId"])
#                     elif hasattr(tx, "TxId") and tx.TxId:
#                         txid = str(tx.TxId)
#                     elif hasattr(tx, "id"):
#                         try:
#                             txid = str(tx.id())
#                         except Exception:
#                             pass
#                     if txid:
#                         confirmed_txids.add(txid)
#         except Exception as e:
#             print(f"[Mempool Cleanup] Error while collecting confirmed txids: {e}")

#         removed = []
#         for txid in list(mem_pool.keys()):
#             if str(txid) in confirmed_txids:
#                 del mem_pool[txid]
#                 removed.append(txid)
#         if removed:
#             print(f"[Mempool Cleanup] Removed confirmed transactions from mempool: {removed}")
#         else:
#             print("[Mempool Cleanup] No confirmed transactions found in mempool.")
# # def safe_add_block(self, blockchain, blockHeight, prevBlockHash, selected_validator):
# #     """Safely create and add a block to the blockchain without direct dictionary assignment"""
# #     try:
# #         # Make sure blockchain has access to the correct mempool
# #         if hasattr(self, 'MemoryPool') and self.MemoryPool:
# #             blockchain.mem_pool = self.MemoryPool
            
# #         # Access blockchain's real UTXO set if available
# #         if hasattr(self, 'blockchain') and hasattr(self.blockchain, 'utxos'):
# #             blockchain.utxos = self.blockchain.utxos

# #         # Now call addBlock with the correct state references
# #         result = blockchain.addBlock(blockHeight, prevBlockHash, selected_validator)
        
# #         print(f"Block {blockHeight} successfully created and mempool synchronized")
# #         return result
# #     except Exception as e:
# #         print(f"Error in safe_add_block: {e}")
# #         import traceback
# #         traceback.print_exc()
# #         return None


            

# def to_bytes_field(field):
#         if isinstance(field, bytes):
#             return field
#         elif isinstance(field, str):
#             try:
#                 return bytes.fromhex(field)
#             except Exception as e:
#                 # If not valid hex, fallback to UTF-8 encoding (adjust if needed)
#                 return field.encode('utf-8')
#         else:
#             raise TypeError("Expected field to be str or bytes")