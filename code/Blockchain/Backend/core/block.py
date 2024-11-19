from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.util.util import int_to_little_endian, little_endian_to_int, encode, read_varint
from Blockchain.Backend.core.Tx import Tx


class Block:
    """
    Block is a storage cpntainer that stores transactions
    """

    command = b'block'

    def __init__(self, Height, Blocksize, BlockHeader, TxCount, Txs):
        self.Height = Height
        self.Blocksize = Blocksize
        self.BlockHeader = BlockHeader
        self.TxCount = TxCount
        self.Txs = Txs

    @classmethod
    def parse(cls, s):
        Height = little_endian_to_int(s.read(4))
        BlockSize = little_endian_to_int(s.read(4))
        blockHeader = BlockHeader.parse(s)
        numTxs = read_varint(s)

        Txs = []

        for _ in range (numTxs):
            Txs.append(Tx.parse(s))

        return cls(Height, BlockSize, blockHeader, numTxs, Txs)

    def serialise(self):
        result = int_to_little_endian(self.Height, 4)
        result += int_to_little_endian(self.Blocksize, 4)
        result += self.BlockHeader.serialise()
        result += encode(len(self.Txs))

        for tx in self.Txs:
            result += tx.serialise()

        return result
        
    @classmethod
    def to_obj(cls, lastblock):
        block = BlockHeader(lastblock[0]['BlockHeader']['version'], 
                    bytes.fromhex(lastblock[0]['BlockHeader']['prevBlockHash']),
                    bytes.fromhex(lastblock[0]['BlockHeader']['merkleRoot']),
                    lastblock[0]['BlockHeader']['timestamp'],
                    bytes.fromhex(lastblock[0]['BlockHeader']['bits']))
        
        block.nonce = int_to_little_endian(lastblock[0]['BlockHeader']['nonce'], 4)

        Transactions = []
        for tx in lastblock[0]['Txs']:
            Transactions.append(Tx.to_obj(tx))

        block.blockHash = bytes.fromhex(lastblock[0]['BlockHeader']['blockHash'])
        return cls(lastblock[0]['Height'], lastblock[0]['Blocksize'], block, len(Transactions), Transactions)

    def to_dict(self):
        dt = self.__dict__
        self.BlockHeader = self.BlockHeader.to_dict()
        return dt
    
