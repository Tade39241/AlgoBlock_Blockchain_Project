from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.util.util import int_to_little_endian, little_endian_to_int, encode, read_varint
from Blockchain.Backend.core.Tx import Tx
import logging # Add logging

logger = logging.getLogger(__name__) 


class Block:
    """
    Block is a storage container that stores transactions
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
        # This method seems specific to loading the *very last block* from a specific list structure.
        # It might be better named or refactored if its purpose is different.
        # Keeping it as is for now.
        try:
            # Ensure lastblock is the dictionary, not the list containing it
            if isinstance(lastblock, list) and len(lastblock) == 1:
                block_data = lastblock[0]
            elif isinstance(lastblock, dict):
                block_data = lastblock
            else:
                 raise ValueError("Invalid format for lastblock in to_obj")

            header_data = block_data['BlockHeader']
            block_header = BlockHeader(
                header_data['version'],
                bytes.fromhex(header_data['prevBlockHash']),
                bytes.fromhex(header_data['merkleRoot']),
                header_data['timestamp'],
                bytes.fromhex(header_data['bits'])
            )
            # Assuming nonce and blockHash are set correctly within BlockHeader's init or methods
            # If they are stored as hex/int in the dict, they need conversion here or in BlockHeader.from_dict
            block_header.nonce = int_to_little_endian(header_data['nonce'], 4) # Assuming nonce is int in dict
            block_header.blockHash = bytes.fromhex(header_data['blockHash']) # Assuming blockHash is hex in dict

            transactions = []
            for tx_dict in block_data.get('Txs', []):
                # Assuming Tx.to_obj works like a from_dict for Tx
                transactions.append(Tx.to_obj(tx_dict))

            return cls(
                block_data['Height'],
                block_data['Blocksize'],
                block_header,
                len(transactions), # Use actual length of reconstructed Txs
                transactions
            )
        except Exception as e:
            logger.error(f"Error in Block.to_obj: {e}", exc_info=True)
            raise # Re-raise the exception after logging
        
    @classmethod
    def to_obj(cls, block_dict): # Renamed input variable for clarity
        """Reconstructs a Block object from its dictionary representation."""
        try:
            if not isinstance(block_dict, dict):
                 raise TypeError(f"Input must be a dictionary, got {type(block_dict)}")

            header_data = block_dict['BlockHeader']

            # Create BlockHeader - Assuming BlockHeader constructor takes these args
            # Or, preferably, BlockHeader should also have a to_obj/from_dict method
            block_header = BlockHeader(
                header_data['version'],
                bytes.fromhex(header_data['prevBlockHash']),
                bytes.fromhex(header_data['merkleRoot']),
                header_data['timestamp'], # Use header_data directly
                bytes.fromhex(header_data['bits'])
            )
            # Manually set nonce and blockHash if not handled by BlockHeader constructor/method
            # Ensure 'nonce' and 'blockHash' keys exist in header_data
            block_header.nonce = int_to_little_endian(header_data['nonce'], 4) # Convert int nonce to bytes
            block_header.blockHash = bytes.fromhex(header_data['blockHash']) # Convert hex hash to bytes

            transactions = []
            # Ensure 'Txs' key exists, default to empty list if not
            for tx_dict in block_dict.get('Txs', []):
                # Assumes Tx.to_obj exists and works like from_dict for Tx
                transactions.append(Tx.to_obj(tx_dict))

            # Create the Block object using data directly from block_dict
            return cls(
                block_dict['Height'],
                block_dict['Blocksize'], # Use block_dict directly
                block_header,
                len(transactions), # Use actual length of reconstructed Txs
                transactions
            )
        except KeyError as e:
             logger.error(f"Missing key in block_dict for Block.to_obj: {e}", exc_info=True)
             raise ValueError(f"Invalid block dictionary format: Missing key {e}") from e
        except Exception as e:
            logger.error(f"Error in Block.to_obj: {e}", exc_info=True)
            raise # Re-raise other unexpected errors


    # def to_dict(self):
    #     dt = self.__dict__
    #     self.BlockHeader = self.BlockHeader.to_dict()
    #     return dt

    def to_dict(self):
        """Converts the Block object to a dictionary suitable for JSON serialization."""
        # Create a copy to avoid mutating the original object's header
        block_dict = {
            'Height': self.Height,
            'Blocksize': self.Blocksize,
            # Ensure BlockHeader.to_dict exists and returns a serializable dict
            'BlockHeader': self.BlockHeader.to_dict(),
            'TxCount': self.TxCount,
            # Ensure Tx.to_dict exists and returns a serializable dict
            'Txs': [tx.to_dict() for tx in self.Txs]
        }
        return block_dict
    
    # --- NEW METHOD ---
    @classmethod
    def from_dict(cls, block_dict):
        """Creates a Block object from a dictionary representation."""
        try:
            # Reconstruct BlockHeader from its dictionary representation
            # Assumes BlockHeader.from_dict exists
            block_header = BlockHeader.from_dict(block_dict['BlockHeader'])

            # Reconstruct Transactions from their dictionary representations
            # Assumes Tx.from_dict exists
            transactions = [Tx.from_dict(tx_dict) for tx_dict in block_dict.get('Txs', [])]

            # Create the Block object
            return cls(
                Height=block_dict['Height'],
                Blocksize=block_dict['Blocksize'],
                BlockHeader=block_header,
                TxCount=block_dict['TxCount'], # Or use len(transactions) for consistency
                Txs=transactions
            )
        except KeyError as e:
            logger.error(f"Missing key in block_dict for Block.from_dict: {e}", exc_info=True)
            raise ValueError(f"Invalid block dictionary format: Missing key {e}") from e
        except Exception as e:
            logger.error(f"Error creating Block from dict: {e}", exc_info=True)
            raise # Re-raise other unexpected errors
    


    