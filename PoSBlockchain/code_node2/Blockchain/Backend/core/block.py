from Blockchain.Backend.core.EllepticCurve.EllepticCurve import Signature
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.util.util import int_to_little_endian, little_endian_to_int, encode, read_varint
from Blockchain.Backend.core.tx import Tx




class Block:
    """
    Block is a storage container that stores transactions
    """

    command = b'block'

    def __init__(self, Height, Blocksize, BlockHeader, TxCount, Txs, Signature=None):
        self.Height = Height
        self.Blocksize = Blocksize
        self.BlockHeader = BlockHeader
        self.TxCount = TxCount
        self.Txs = Txs
        self.Signature = Signature

    @classmethod
    def to_obj(cls, data):
        # If 'data' is already an instance of Block, just return it.
        if isinstance(data, cls):
            return data

        # If data is a list, assume the block dictionary is its first element.
        if isinstance(data, list):
            block_dict = data[0]
        elif isinstance(data, dict):
            block_dict = data
        else:
            raise TypeError("Unsupported type for Block.to_obj; expected dict or list.")

        header_data = block_dict['BlockHeader']
        sig_hex = header_data.get('signature')
        print(f"DEBUG: BlockHeader signature field type: {type(sig_hex)}, value: {sig_hex}")
        if sig_hex:
            sig_bytes = bytes.fromhex(sig_hex)
            try:
                signature = Signature.parse(sig_bytes)
                print(signature)
            except Exception as e:
                print(f"Error parsing signature from dict: {e}")
                signature = None
        else:
            signature = None

        block_header = BlockHeader(
            header_data['version'],
            bytes.fromhex(header_data['prevBlockHash']),
            bytes.fromhex(header_data['merkleRoot']),
            header_data['timestamp'],
            bytes.fromhex(header_data['validator_pubkey']),
            signature
        )
        block_header.blockHash = header_data['blockHash']

        # Reconstruct transactions.
        Transactions = []
        for tx in block_dict['Txs']:
            Transactions.append(Tx.to_obj(tx))

        # Return a new Block instance.
        return cls(
            block_dict['Height'],
            block_dict['Blocksize'],
            block_header,
            len(Transactions),
            Transactions
        )

    
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
        print(f"[DEBUG/BLOCK] Block {self.Height} TxIDs: {[tx.id() for tx in self.Txs]}")
        result = int_to_little_endian(self.Height, 4)
        result += int_to_little_endian(self.Blocksize, 4)
        result += self.BlockHeader.serialise_with_signature()
        result += encode(len(self.Txs))

        for tx in self.Txs:
            result += tx.serialise()

        print(f"[DEBUG/BLOCK] Block serialized bytes: {result.hex()}")
        return result
        
    
    def to_dict(self):
        dt = self.__dict__
        if hasattr(self.BlockHeader, "__dict__"):
            self.BlockHeader = self.BlockHeader.__dict__
            # Do NOT call .to_dict() on BlockHeader or Txs
        return dt