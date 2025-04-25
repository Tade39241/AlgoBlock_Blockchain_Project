import json
import os, sys
from pathlib import Path

PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Add the parent directory to sys.path
sys.path.insert(0, PARENT_DIR)

# Now you can import from Blockchain as a package
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.core.Tx import Coinbase_tx
from Blockchain.Backend.util.util import merkle_root, target_to_bits, int_to_little_endian

def generate_genesis_block():
    """Generate a genesis block for the blockchain"""
    ZERO_HASH = '0' * 64
    VERSION = 1
    GENESIS_TIMESTAMP = 1600000000
    GENESIS_NONCE = 0
    GENESIS_BITS = target_to_bits(0x0000FFFF00000000000000000000000000000000000000000000000000000000)

    # 1. Create coinbase transaction
    coinbase_instance = Coinbase_tx(0)
    coinbase_tx = coinbase_instance.coinbase_transaction()

    # 2. Prepare block txs and merkle root
    txids = [bytes.fromhex(coinbase_tx.id())]
    merkle = merkle_root(txids)

    # 3. Create block header
    header = BlockHeader(
        VERSION,
        bytes.fromhex(ZERO_HASH),
        merkle,
        GENESIS_TIMESTAMP,
        GENESIS_BITS,
        int_to_little_endian(GENESIS_NONCE, 4)  # Convert integer to bytes  # Pass as integer, not bytes
    )
    header.blockHash = header.generateBlockHash()

    # 4. Create block with coinbase tx
    genesis_block = Block(
        0,  # Height
        80 + len(coinbase_tx.serialise()),  # Blocksize
        header,
        1,  # TxCount
        [coinbase_tx]
    )

    # Convert all Tx objects to dicts for JSON serialization
    block_dict = genesis_block.to_dict()
    block_dict["Txs"] = [tx.to_dict() for tx in genesis_block.Txs]

    return block_dict

def save_genesis_block(block_dict, output_path=None):
    """Save the genesis block to a JSON file"""
    if output_path is None:
        # Default to project root
        output_path = Path(__file__).parent.parent / "genesis_block.json"
    
    with open(output_path, 'w') as f:
        json.dump(block_dict, f, indent=2)  
        
    print(f"Genesis block saved to {output_path}")
    return output_path

if __name__ == "__main__":
    # Generate and save the genesis block
    genesis = generate_genesis_block()
    save_genesis_block(genesis)
    
    # Also print to console
    print(json.dumps(genesis, indent=2))