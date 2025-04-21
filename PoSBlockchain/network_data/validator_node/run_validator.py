

# Add paths


import sys
import os
import time
import signal
import json
import sqlite3
import threading

sys.path.append("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain")
sys.path.append("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/validator_node")
sys.path.insert(0, "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/code_node2")

from Blockchain.Backend.core.network.connection import Node
from Blockchain.Backend.core.network.network import NetworkEnvelope

# Custom database paths
data_dir = os.path.join("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/validator_node", "data")
if not os.path.exists(data_dir):
    os.makedirs(data_dir, exist_ok=True)
blockchain_db_path = os.path.join(data_dir, "blockchain.db")
node_db_path = os.path.join(data_dir, "node.db")
account_db_path = os.path.join(data_dir, "account.db")

# Patch database classes for correct paths
from code_node2.Blockchain.Backend.core.database.db import NodeDB, BlockchainDB, AccountDB

VALIDATOR_ADDRESS = '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh'

def patched_nodedb_init(self, db_path=None):
    self.filename = node_db_path if not db_path else db_path
    self.filepath = self.filename
    self.conn = None
    self.connect()
    self.table_schema = '''
    CREATE TABLE IF NOT EXISTS nodes
    (port INTEGER PRIMARY KEY)
    '''
    self._create_table()
NodeDB.__init__ = patched_nodedb_init

def patched_blockchaindb_init(self, db_path=None):
    self.filename = node_db_path if not db_path else db_path
    self.filepath = blockchain_db_path if not db_path else db_path
    self.table_name = "blocks"
    self.conn = None
    print(f"[DEBUG] BlockchainDB will use path: {self.filepath}")
    self.connect()
    self.table_schema = '''
    CREATE TABLE IF NOT EXISTS blocks
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL)
    '''
    self._create_table()
BlockchainDB.__init__ = patched_blockchaindb_init

def patched_accountdb_init(self, db_path=None):
    effective_path = db_path if db_path else account_db_path
    self.filename = effective_path
    self.filepath = self.filename
    self.conn = None
    self.connect()
    self.table_schema = '''
    CREATE TABLE IF NOT EXISTS account
    (public_addr TEXT PRIMARY KEY,
    value TEXT NOT NULL)
    '''
    self._create_table()
AccountDB.__init__ = patched_accountdb_init

# Test database connections
print(f"Testing validator database connections...")
try:
    conn = sqlite3.connect(node_db_path)
    print(f"  - Connected to validator node database: {node_db_path}")
    conn.close()
    conn = sqlite3.connect(blockchain_db_path)
    print(f"  - Connected to validator blockchain database: {blockchain_db_path}")
    conn.close()
    conn = sqlite3.connect(account_db_path)
    print(f"  - Connected to validator account database: {account_db_path}")
    conn.close()
except Exception as e:
    print(f"Error testing validator database connections: {e}")
    sys.exit(1)

# Node addresses map - helps validator identify nodes by their addresses
node_addresses = {
    '1DPPqS7kQNQMcn28du4sYJe8YKLUH8Jrig': 0,  # Node 0
    '1Lu9SwPPo7DJYrMVrZnkDXVw5y4aEeF1kz': 1,  # Node 1
    '14yikjhubj1sepvqsvzpRv4H6LhMN43XGD': 2,  # Node 2
    '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh': 3,  # Reserve node
}

# Create validator account with stake
def create_validator_account():
    default_addr = '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh'
    account_data = {
        'public_addr': default_addr,
        'privateKey': '90285630861639623347665892885049342176040030896554662509747065762830918365196',
        'public_key': '0428492a0256e1d7114ec48663516a44213f201afa16f425abb512339cc7bfed3964fc3d26e22a61f6aa0e3dc6549526a76be4f7fbdb9f57e0ef526c3b4ccc1913',
        'staked': 100 * 100000000
    }
    try:
        conn = sqlite3.connect(account_db_path)
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS account (public_addr TEXT PRIMARY KEY, value TEXT NOT NULL)')
        account_json = json.dumps(account_data)
        cursor.execute('INSERT OR REPLACE INTO account VALUES (?, ?)', (default_addr, account_json))
        conn.commit()
        conn.close()
        print(f"Created validator account with stake: {default_addr}")
        # Verify the account was written
        conn = sqlite3.connect(account_db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM account WHERE public_addr = ?', (default_addr,))
        result = cursor.fetchone()
        if result:
            print(f"Validator account verified with data: {result[0][:30]}...")
        else:
            print("WARNING: Validator account not found after writing!")
        conn.close()
    except Exception as e:
        print(f"Error creating validator account: {e}")

create_validator_account()

from code_node2.Blockchain.Backend.core.database.db import BlockchainDB
from code_node2.Blockchain.Backend.util.util import decode_base58, encode_base58, hash256
from code_node2.Blockchain.Backend.core.tx import Tx, TxOut
from code_node2.Blockchain.Backend.core.script import Script

# --- SyncManager for receiving blocks ---
def start_sync_server(host, port):
    from code_node2.Blockchain.Backend.core.network.syncManager import syncManager
    from code_node2.Blockchain.Backend.core.pos_blockchain import Blockchain
    # Use dummy shared dicts for mempool/utxos (not used by validator)
    mem_pool = {}
    utxos = {}
    newBlockAvailable = {}
    secondaryChain = {}
    blockchain = Blockchain(utxos, mem_pool, newBlockAvailable, secondaryChain, port, host)
    sync = syncManager(host, port, mem_pool, blockchain=blockchain)
    sync.spinUpServer()

# Start sync server in background thread
def launch_sync_thread(host, port):
    t = threading.Thread(target=start_sync_server, args=(host, port), daemon=True)
    t.start()
    print(f"[Validator] Sync server started on {host}:{port}")

def build_utxos_from_blocks(blocks):
    utxos = {}
    spent = set()
    for block in blocks:
        txs = block[0]['Txs'] if isinstance(block, list) else block['Txs']
        for tx_dict in txs:
            tx = Tx.to_obj(tx_dict)
            txid = tx.TxId if hasattr(tx, 'TxId') else tx.id()
            for tx_in in tx.tx_ins:
                spent.add((tx_in.prev_tx.hex(), tx_in.prev_index))
            for idx, tx_out in enumerate(tx.tx_outs):
                key = (txid, idx)
                if key not in spent:
                    utxos[key] = tx_out
    for key in spent:
        utxos.pop(key, None)
    return utxos

def get_latest_utxo_set():
    blockchain_db = BlockchainDB(blockchain_db_path)
    blocks = blockchain_db.read_all_blocks()
    return build_utxos_from_blocks(blocks)

def get_staked_balances_from_utxos(utxo_set):
    staked = {}
    for (txid, idx), tx_out in utxo_set.items():
        cmds = tx_out.script_publickey.cmds
        if len(cmds) == 3 and cmds[0] == b'\x00':
            h160 = cmds[1]
            addr = encode_base58(b'\x00' + h160 + hash256(b'\x00' + h160)[:4])
            staked[addr] = staked.get(addr, 0) + tx_out.amount
    return staked

class ValidatorSelector:
    def __init__(self, host, port, peer_list):
        self.host = host
        self.port = port
        self.peer_list = peer_list

    def select_validator(self, utxo_set):
        import random
        staked = get_staked_balances_from_utxos(utxo_set)
        validators = [(addr, amt) for addr, amt in staked.items() if amt > 0 and addr != VALIDATOR_ADDRESS]
        print(f"Available validators (excluding {VALIDATOR_ADDRESS}): {[addr for addr, _ in validators]}")
        if not validators:
            print("ERROR: No eligible validators found with stake!")
            return None
        total_stake = sum(amt for addr, amt in validators)
        selection = random.uniform(0, total_stake)
        cumulative = 0
        for addr, amt in validators:
            cumulative += amt
            if selection <= cumulative:
                print(f"Selected validator {addr} based on weighted random (stake: {amt})")
                return addr
        print(f"Fallback selection: {validators[-1][0]}")
        return validators[-1][0]

    def broadcast_selection(self, selected_validator):
        message_dict = {
            "type": "validator_selection",
            "selected_validator": selected_validator
        }
        payload = json.dumps(message_dict).encode()
        envelope = NetworkEnvelope(b'valselect', payload)
        
        for peer in self.peer_list:
            try:
                peer_host = peer[0]
                peer_port = int(peer[1])  # Convert port to integer if necessary.
                node = Node(self.host, peer_port)
                sock = node.connect(peer_port)
                print(f"Connecting to peer {peer_host}:{peer_port} to broadcast selection...")
                sock.sendall(envelope.serialise())
                sock.close()
                print(f"[ValidatorSelector] Successfully sent validator selection to {(peer_host, peer_port)}")
            except Exception as e:
                print(f"[ValidatorSelector] Error sending selection to {(peer_host, peer_port)}: {e}")


    def run(self):
        while True:
            utxo_set = get_latest_utxo_set()
            selected_validator = self.select_validator(utxo_set)
            if selected_validator:
                staked = get_staked_balances_from_utxos(utxo_set)
                print(f"[ValidatorSelector] Selected Validator: {selected_validator} with stake {staked[selected_validator]}")
                self.broadcast_selection(selected_validator)
            else:
                print("[ValidatorSelector] No eligible validator found.")
            time.sleep(60)

def signal_handler(sig, frame):
    print("\nShutting down validator node gracefully...")
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    host = "127.0.0.1"
    port = 9003
    peer_list = [('127.0.0.1', 9000), ('127.0.0.1', 9001), ('127.0.0.1', 9002)]
    print(f"Starting validator node on port {port} with custom DB paths")

    from code_node2.Blockchain.Backend.core.pos_blockchain import Blockchain
    utxos = {}
    mem_pool = {}
    newBlockAvailable = {}
    secondaryChain = {}

    blockchain = Blockchain(utxos, mem_pool, newBlockAvailable, secondaryChain, port, host)
    if blockchain.fetch_last_block() is None:
        print("[Validator] No blocks found, creating genesis block...")
        blockchain.GenesisBlock()
        print("[Validator] Genesis block created and broadcast.")
    else:
        print("[Validator] Blockchain already initialized.")

    validator = ValidatorSelector(host, port, peer_list)
    validator.run()
    