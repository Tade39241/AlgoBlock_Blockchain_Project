from Blockchain.Backend.core.network.connection import Node
from Blockchain.Backend.core.database.db import BlockchainDB, NodeDB
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.core.network.network import requestBlock, NetworkEnvelope, FinishedSending, portList
from Blockchain.Backend.core.tx import Tx, TxIn, TxOut
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.util.util import little_endian_to_int, int_to_little_endian

from threading import Thread

class syncManager:
    """
        Initialize the sync manager.
        
        Args:
            host: The host address to connect to
            port: The port to connect to
            blockchain: The blockchain instance (optional for transaction broadcasting)
            localHostPort: The local port (optional for transaction broadcasting)
    """
    def __init__(self, host, port, MemoryPool ,blockchain=None, localHostPort=None, newBlockAvailable=None,secondaryChain=None, my_public_addr=None):
        self.host = host
        self.port = port
        self.blockchain = blockchain
        self.newBlockAvailable = {} if newBlockAvailable is None else newBlockAvailable        
        self.secondaryChain = secondaryChain
        self.MemoryPool = MemoryPool if MemoryPool is not None else {}
        self.localHostPort = localHostPort
        self.my_public_addr = my_public_addr  # Store the node's public address here


    def spinUpServer(self):
        self.server = Node(self.host, self.port)
        self.server.startServer()
        print("SERVER STARTED")
        print(f"LISTENING at {self.host}:{self.port}")    

        while True:
            self.conn, self.addr = self.server.acceptConnection()
            handleConn = Thread(target=self.handleConnection)
            handleConn.start()

    def handleConnection(self):
        envelope = self.server.read()
        try:
            if len(str(self.addr[1]))== 4:
                self.addNode()
            
            if envelope.command == b'tx':
                Transaction = Tx.parse(envelope.stream())
                calculated_txid = Transaction.id()
                Transaction.TxId = Transaction.id()
                if calculated_txid != Transaction.TxId:
                        raise ValueError(f"TxId Mismatch! Calculated: {calculated_txid}, Received: {Transaction.TxId}")
                print(f"Transaction Received : {Transaction.TxId}")
                
                self.MemoryPool[Transaction.TxId] = Transaction

            if envelope.command == b'block':
                print(f"[Receiver] Received envelope with command: {envelope.command} and payload length: {len(envelope.payload)} bytes")
                blockObj = Block.parse(envelope.stream())
                BlockHeaderObj = BlockHeader(blockObj.BlockHeader.version,
                            blockObj.BlockHeader.prevBlockHash, 
                            blockObj.BlockHeader.merkleRoot, 
                            blockObj.BlockHeader.timestamp,
                            blockObj.BlockHeader.validator_pubkey,
                            blockObj.BlockHeader.signature)
            
                
                self.newBlockAvailable[BlockHeaderObj.generateBlockHash()] = blockObj
                print(f"New Block Received : {blockObj.Height}")
                print(f"Block Hash : {BlockHeaderObj.generateBlockHash()}, Block Signature : {BlockHeaderObj.signature.hex()}")
                print(f"block: {BlockHeaderObj.to_dict()}")
                
            if envelope.command == requestBlock.command:
                start_block, end_block = requestBlock.parse(envelope.stream())
                self.sendBlockToRequestor(start_block)
                print(f"Start Block is {start_block} \n End Block is {end_block}")
            
            self.conn.close()
        except Exception as e:
            self.conn.close()
            print(f"Error While processing the client request \n {e}")


    def addNode(self):
        nodeDb = NodeDB()
        portList = nodeDb.read()
        print(f"Current ports in database: {portList}")

        if self.addr[1] and (self.addr[1]+ 1 ) not in portList:
            new_port = self.addr[1] + 1
            nodeDb.write(new_port)
            print(f"Added new port: {new_port}")

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
    
    def process_received_block(self, block):
        """
        Process a newly received block.
        If the block is valid according to its header validation, update the UTXO set,
        remove confirmed transactions from the mempool, and write the block to the blockchain.
        Otherwise, add the block to the secondary chain.
        """
        # Reconstruct a BlockHeader object from the received block.
        BlockHeaderObj = BlockHeader(
            block.BlockHeader.version,
            block.BlockHeader.prevBlockHash,
            block.BlockHeader.merkleRoot,
            block.BlockHeader.timestamp,
            block.BlockHeader.validator_pubkey,
            block.BlockHeader.signature
        )

        
        print(f"[Receiver] Parsed block: prevHash {BlockHeaderObj.prevBlockHash.hex()},merkleRoot: {BlockHeaderObj.merkleRoot.hex()},signature: {BlockHeaderObj.signature}, validator_pubkey: {BlockHeaderObj.validator_pubkey.hex()}, timestamp: {BlockHeaderObj.timestamp}")


        # Validate the block header (this should include PoS checks, hash target, etc.)
        if BlockHeaderObj.validate_block():
            print(f"[BLOCK PROCESS] Valid block received. Height: {block.Height}")
            
            # Process each transaction in the block.
            for idx, tx in enumerate(block.Txs):
                # Recalculate the transaction ID.
                tx.TxId = tx.id()
                # Add the new outputs to the UTXO set.
                self.utxos[tx.TxId] = tx
                print(f"[BLOCK PROCESS] Added UTXO for Tx: {tx.TxId}")
                
                # Remove inputs from the UTXO set.
                for txin in tx.tx_ins:
                    prev_txid = txin.prev_tx.hex()
                    prev_index = txin.prev_index
                    if prev_txid in self.utxos:
                        if hasattr(self.utxos[prev_txid], 'tx_outs') and len(self.utxos[prev_txid].tx_outs) > prev_index:
                            print(f"[BLOCK PROCESS] Removing spent output from Tx: {prev_txid}, index {prev_index}")
                            self.utxos[prev_txid].tx_outs[prev_index] = None
                        else:
                            print(f"[BLOCK PROCESS] Warning: {prev_txid} has no output at index {prev_index}")
                
                # Remove the transaction from the mempool if present.
                if tx.TxId in self.mem_pool:
                    print(f"[BLOCK PROCESS] Removing Tx {tx.TxId} from mempool")
                    del self.mem_pool[tx.TxId]
                
                # Optionally, convert transaction to dictionary if needed for DB storage.
                block.Txs[idx] = tx.to_dict()

            # Finalise the block header (for example, convert fields to hex, compute final block hash, etc.)
            BlockHeaderObj.to_hex()
            block.BlockHeader = BlockHeaderObj
            # Write the valid block to the blockchain database.
            BlockchainDB().write([block.to_dict()])
            print(f"[BLOCK PROCESS] Block {block.Height} integrated into the blockchain.")
        else:
            # If the block is not valid, add it to the secondary chain.
            block_hash = BlockHeaderObj.generateBlockHash()
            # self.secondaryChain[block_hash] = block
            print(f"[BLOCK PROCESS] Block {block.Height} is invalid. Stored in secondary chain for review.")


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
    
    def connectToHost(self, localport, port, bindPort = None):
        self.connect = Node(self.host, port)
        if bindPort:
            self.socket = self.connect.connect(localport, bindPort)
            print(f"Trying to connect from {localport} to: {port}...")
        else:
            self.socket = self.connect.connect(localport)
            print(f"Trying to connect from {localport}: to: {port}...")

        self.stream = self.socket.makefile('rb', None)


    def publishTx(self,Tx):
        self.connect.send(Tx)
    
    def publishBlock(self, localport, port, block):
        # print(f"[Debug] publish block printing: {block.__dict__}")
        self.connectToHost(localport, port)
        print('Connected to host')
        # print(f"[Sender] Sending block {block.Height} with hash {block.BlockHeader.blockHash} and size {len(block_bytes)} bytes")
        self.connect.send(block)

    def startDownload(self, localport, port, bindPort):
        print("Starting download...")
        lastBlock = BlockchainDB().lastBlock()

        if not lastBlock:
            lastBlockHeader = "c2f45f49e7582f260195de06ed73098cdc6565e95d33704da95b4e715007dcbf"
        else:
            lastBlockHeader = lastBlock[0]['BlockHeader']['blockHash']

        startBlock = bytes.fromhex(lastBlockHeader)

        getHeaders = requestBlock(startBlock=startBlock)
        self.connectToHost(localport, port, bindPort)
        print(f"localport value: {localport}, type: {type(localport)}")
        self.connect.send(getHeaders)

        while True:
            envelope = NetworkEnvelope.parse(self.stream)
            print("DEBUG: Envelope command =", envelope.command)
            print("DEBUG: Envelope length =", len(envelope.payload))

            if envelope.command == b'Finished':
                blockObj = FinishedSending.parse(envelope.stream())
                print(f'All blocks receieved')
                self.socket.close()
                break

            if envelope.command == b'portlist':
                s = envelope.stream()
                raw_data = s.read()
                print("DEBUG: envelope stream bytes =", raw_data.hex())
                s.seek(0)

                ports = portList.parse(s)
                nodeDb = NodeDB()
                portlists = nodeDb.read_nodes()
                for port in ports:
                    if port not in portlists:
                        nodeDb.write(port)

            if envelope.command == b'block':
                blockObj = Block.parse(envelope.stream())
                print("DEBUG: envelope payload length =", len(envelope.payload))
                print("DEBUG: envelope payload hex =", envelope.payload.hex())
                BlockHeaderObj = BlockHeader(blockObj.BlockHeader.version,
                          blockObj.BlockHeader.prevBlockHash,
                          blockObj.BlockHeader.merkleRoot,
                          blockObj.BlockHeader.timestamp,
                          blockObj.BlockHeader.validator_pubkey,
                          blockObj.BlockHeader.signature)
              
                if BlockHeaderObj.validate_block():
                    for idx,tx in enumerate(blockObj.Txs):
                        tx.TxId = tx.id()
                        blockObj.Txs[idx] = tx.to_dict()
                      
                    BlockHeaderObj.blockHash = BlockHeaderObj.generateBlockHash()
                    BlockHeaderObj.prevBlockHash = BlockHeaderObj.prevBlockHash.hex()
                    BlockHeaderObj.merkleRoot = BlockHeaderObj.merkleRoot.hex()

                    blockObj.BlockHeader = BlockHeaderObj

                    BlockchainDB().write([blockObj.to_dict()])

                    print(f"Block Received - {blockObj.Height}")