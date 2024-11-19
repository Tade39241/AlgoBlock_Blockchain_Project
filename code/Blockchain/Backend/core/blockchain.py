import sys
sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code')


import configparser
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.util.util import hash256, merkle_root, target_to_bits
from Blockchain.Backend.core.database.db import BlockchainDB, NodeDB
from Blockchain.Backend.core.Tx import Coinbase_tx
from multiprocessing import Process, Manager
from Blockchain.Frontend.run import main
from Blockchain.Backend.core.network.syncManager import syncManager
import time
import json
import base58


ZERO_HASH = '0' * 64
VERSION = 1
INITIAL_TARGET = 0x0000FFFF00000000000000000000000000000000000000000000000000000000

class Blockchain:
    def __init__(self,utxos, mem_pool):
        self.mem_pool = mem_pool
        self.utxos = utxos
        self.current_target = INITIAL_TARGET
        self.bits = target_to_bits(INITIAL_TARGET)

    def write_on_disk(self,block):
        blockchainDB = BlockchainDB()
        blockchainDB.write(block)

    def fetch_last_block(self):
        blockchainDB = BlockchainDB()
        return blockchainDB.lastBlock()
    
    
    def GenesisBlock(self):
        BlockHeight = 0
        prevBlockHash = ZERO_HASH
        self.addBlock(BlockHeight, prevBlockHash)

    """ start the sync node """
    def startSync(self):
        try:
            node = NodeDB()
            portList = node.read()
            
            for port in portList:
                port = port[0]
                if localHostPort != port:
                    sync = syncManager(localHost,port)
                    sync.startDownload(localHostPort - 1, port)

        except Exception as err:
            print(f"Error while downloading the Blockchain \n{err}")

    def store_uxtos_in_cache(self):
        for tx in self.add_trans_in_block:
            self.utxos[tx.TxId] = tx

    def remove_spent_Transactions(self):
        for txId_index in self.remove_spent_transactions:
            if txId_index[0].hex() in self.utxos:

                if len(self.utxos[txId_index[0].hex()].tx_outs) < 2:
                    print(f" Spent Transaction removed {txId_index[0].hex()} ")
                    del self.utxos[txId_index[0].hex()]
                else:
                    prev_trans = self.utxos[txId_index[0].hex()]
                    self.utxos[txId_index[0].hex()] = prev_trans.tx_outs.pop(
                        txId_index[1]
                    )

    "Read transactions from mem pool"
    def read_trans_from_mempool(self):
        self.Blocksize = 80
        self.TxIds = []
        self.add_trans_in_block = []
        self.remove_spent_transactions = []

        for tx in self.mem_pool:
            self.TxIds.append(bytes.fromhex(tx))
            self.add_trans_in_block.append(self.mem_pool[tx])
            self.Blocksize += len(self.mem_pool[tx].serialise())

            for spent in self.mem_pool[tx].tx_ins:
                self.remove_spent_transactions.append([spent.prev_tx, spent.prev_index])
    
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
            if TxId_index[0].hex() in self.utxos:
                self.input_amount += self.utxos[TxId_index[0].hex()].tx_outs[TxId_index[1]].amount
        
        for tx in self.add_trans_in_block:
            for tx_out in tx.tx_outs:
                self.output_amount += tx_out.amount
        
        self.fee = self.input_amount - self.output_amount

    def addBlock(self, BlockHeight, prevBlockHash):
        self.read_trans_from_mempool()
        self.calculate_fee()
        timestamp = int(time.time())
        coinbase_instance = Coinbase_tx(BlockHeight)
        coinbaseTx = coinbase_instance.coinbase_transaction()
        self.Blocksize += len(coinbaseTx.serialise())

        coinbaseTx.tx_outs[0].amount = coinbaseTx.tx_outs[0].amount + self.fee

        self.TxIds.insert(0, bytes.fromhex(coinbaseTx.id()))
        self.add_trans_in_block.insert(0, coinbaseTx)

        merkleRoot = merkle_root(self.TxIds)[::-1].hex()

        blockheader = BlockHeader(VERSION, prevBlockHash, merkleRoot, timestamp, self.bits, nonce = 0)
        blockheader.mine(self.current_target)

        self.remove_spent_Transactions()
        self.remove_trans_from_mempool()
        self.store_uxtos_in_cache()
        self.convert_to_json()

        print(f"Block {BlockHeight} was mined successfully with a nonce value of {blockheader.nonce}")
        self.write_on_disk([Block(BlockHeight, 1, blockheader.__dict__, len(self.TxJson), self.TxJson).__dict__])
        

    def main(self):
        lastBlock = self.fetch_last_block()
        if lastBlock == None:
            self.GenesisBlock()
            
        while True:
            lastBlock = self.fetch_last_block()
            BlockHeight = lastBlock[0]['Height'] + 1
            prevBlockHash = lastBlock[0]['BlockHeader']['blockHash']
            self.addBlock(BlockHeight, prevBlockHash)

if __name__ == '__main__':
    """ read configuration file"""

    config = configparser.ConfigParser()
    config.read('config.ini')
    localHost = config['DEFAULT']['host']
    localHostPort = int(config['MINER']['port'])
    webport = int(config['Webhost']['port'])
    with Manager() as manager:
        mem_pool = manager.dict()
        utxos = manager.dict()

        webapp = Process(target=main, args=(utxos, mem_pool, webport))
        webapp.start()
        """Start server and listen for miner/user requests"""

        sync = syncManager(localHost,localHostPort)
        startServer = Process(target=sync.spinUpServer)
        startServer.start()


        blockchain = Blockchain(utxos, mem_pool)
        blockchain.startSync()
        blockchain.main()
        
