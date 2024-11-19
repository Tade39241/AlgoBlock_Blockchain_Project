from Blockchain.Backend.core.network.connection import Node
from Blockchain.Backend.core.database.db import BlockchainDB, NodeDB
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.core.network.network import requestBlock, NetworkEnvelope, FinishedSending, portList
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.util.util import little_endian_to_int, int_to_little_endian

from threading import Thread

class syncManager:
    def __init__(self, host, port):
        self.host = host
        self.port = port

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

            if envelope.command == requestBlock.command:
                start_block, end_block = requestBlock.parse(envelope.stream())
                self.sendBlockToRequestor(start_block)
                print(f"Start Block is {start_block} \n End Block is {end_block}")
        except Exception as e:
            print(f"Error While processing the client request \n {e}")

    def addNode(self):
        nodeDb = NodeDB()
        portList = nodeDb.read()

        if self.addr[1] and (self.addr[1]+ 1 ) not in portList:
            nodeDb.write(self.addr[1] + 1 )


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
        ports = nodeDB.read()

        portlist = portList(ports)
        envelope = NetworkEnvelope(portlist.command, portlist.serialise())
        self.conn.sendall(envelope.serialise)

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

    def startDownload(self, localport ,port):
        print("Starting download...")
        lastBlock = BlockchainDB().lastBlock()

        if not lastBlock:
            lastBlockHeader = "00001bc3f715020a52b683f8f7d7296914a441d20c35ee978b2a9763574cc45c"
        else:
            lastBlockHeader = lastBlock[0]['BlockHeader']['blockHash']

        startBlock = bytes.fromhex(lastBlockHeader)

        getHeaders = requestBlock(startBlock=startBlock)
        self.connect = Node(self.host, port)
        self.socket = self.connect.connect(localport)
        self.stream = self.socket.makefile('rb', None)
        self.connect.send(getHeaders)

        while True:
            envelope = NetworkEnvelope.parse(self.stream)

            if envelope.command == b'Finished':
                blockObj = FinishedSending.parse(envelope.stream())
                print(f'All blocks receieved')
                self.socket.close()
                break

            if envelope.command == b'portlist':
                ports = portList.parse(envelope.stream())
                nodeDb = NodeDB()
                portlists = nodeDb.read()

                for port in ports:
                    if port not in portlists:
                        nodeDb.write([port])
            
            if envelope.command == b'block':
                blockObj = Block.parse(envelope.stream())
                BlockHeaderObj = BlockHeader(blockObj.BlockHeader.version,
                          blockObj.BlockHeader.prevBlockHash,
                          blockObj.BlockHeader.merkleRoot,
                          blockObj.BlockHeader.timestamp,
                          blockObj.BlockHeader.bits,
                          blockObj.BlockHeader.nonce)
              
                if BlockHeaderObj.validateBlock():
                    for idx,tx in enumerate(blockObj.Txs):
                        tx.TxId = tx.id()
                        blockObj.Txs[idx] = tx.to_dict()
                
                      
                    BlockHeaderObj.blockHash = BlockHeaderObj.generateBlockHash()
                    BlockHeaderObj.prevBlockHash = BlockHeaderObj.prevBlockHash.hex()
                    BlockHeaderObj.merkleRoot = BlockHeaderObj.merkleRoot.hex()
                    BlockHeaderObj.nonce = little_endian_to_int(BlockHeaderObj.nonce)
                    BlockHeaderObj.bits = BlockHeaderObj.bits.hex()

                    blockObj.BlockHeader = BlockHeaderObj

                    BlockchainDB().write([blockObj.to_dict()])

                    print(f"Block Received - {blockObj.Height}")
                else:
                    print("Chain is broken")