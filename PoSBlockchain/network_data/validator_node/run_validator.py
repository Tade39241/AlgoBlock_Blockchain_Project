
import sys
import os
import time
import signal
import json

# Add paths
sys.path.append("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain")
sys.path.append("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/validator_node")

data_dir = os.path.join("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/validator_node", "data")
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# Custom database paths
blockchain_db_path = os.path.join(data_dir, "blockchain.db")
node_db_path = os.path.join(data_dir, "node.db")
account_db_path = os.path.join(data_dir, "account.db")

# --- Add this block ---
# Ensure validator directory exists before trying to access DBs
validator_base_dir = os.path.dirname(account_db_path)
if not os.path.exists(validator_base_dir):
    os.makedirs(validator_base_dir, exist_ok=True)
    print(f"Created validator directory: {validator_base_dir}")
# --- End added block ---

# Set up important paths
sys.path.insert(0, "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/code_node2")

# Create a complete fixed validator module
with open('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/validator_node/fixed_validator.py', 'w') as f:
    with open('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/validatorNode/main.py', 'r') as src:
        validator_code = src.read()
        
        # Fix all network-related imports
        replacements = [
            ('from network.connection import Node', 
             'from code_node2.Blockchain.Backend.core.network.connection import Node'),
            ('from network.network import NetworkEnvelope', 
             'from code_node2.Blockchain.Backend.core.network.network import NetworkEnvelope'),
            ('from database.db import', 
             'from code_node2.Blockchain.Backend.core.database.db import'),
            ('import network.', 
             'import code_node2.Blockchain.Backend.core.network.'),
            ('from network.', 
             'from code_node2.Blockchain.Backend.core.network.'),
            ('import database.', 
             'import code_node2.Blockchain.Backend.core.database.'),
            ('from database.', 
             'from code_node2.Blockchain.Backend.core.database.')
        ]
        
        for old, new in replacements:
            validator_code = validator_code.replace(old, new)
            
        f.write(validator_code)

# Patch database classes to use custom paths
from code_node2.Blockchain.Backend.core.database.db import NodeDB, BlockchainDB, AccountDB

# Save original inits
original_nodedb_init = NodeDB.__init__
original_blockchaindb_init = BlockchainDB.__init__
original_accountdb_init = AccountDB.__init__

# Patch NodeDB with absolute paths
def patched_nodedb_init(self, db_path=None):
    self.filepath = node_db_path if not db_path else db_path
    self.table_name = "nodes"  # Add table_name attribute
    self.conn = None
    self.connect()
    self.table_schema = '''
    CREATE TABLE IF NOT EXISTS nodes
    (port INTEGER PRIMARY KEY)
    '''
    self._create_table()
NodeDB.__init__ = patched_nodedb_init

def patched_blockchaindb_init(self, db_path=None):
    self.filepath = blockchain_db_path if not db_path else db_path
    self.table_name = "blocks"
    self.conn = None
    self.connect()
    self.table_schema = '''
    CREATE TABLE IF NOT EXISTS blocks
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL)
    '''
    self._create_table()
BlockchainDB.__init__ = patched_blockchaindb_init

# Patch AccountDB
def patched_accountdb_init(self, db_path=None):
    effective_path = db_path if db_path else account_db_path
    self.filename = effective_path
    self.table_name = 'account'
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
    import sqlite3
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

# Import our fixed validator module
sys.path.insert(0, "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/validator_node")
from fixed_validator import ValidatorSelector

# Create validator account with stake
def create_validator_account():
    default_addr = '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh'
    
    # Account data structure with stake 
    account_data = {
        'public_addr': default_addr,
        'privateKey': '90285630861639623347665892885049342176040030896554662509747065762830918365196',
        'public_key': '0428492a0256e1d7114ec48663516a44213f201afa16f425abb512339cc7bfed3964fc3d26e22a61f6aa0e3dc6549526a76be4f7fbdb9f57e0ef526c3b4ccc1913'
    }
    
    # Write directly using SQL
    try:
        import sqlite3
        import json  # Make sure json is imported
        conn = sqlite3.connect(account_db_path)
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS account (public_addr TEXT PRIMARY KEY, value TEXT NOT NULL)')
        account_json = json.dumps(account_data)
        cursor.execute('INSERT OR REPLACE INTO account VALUES (?, ?)', 
                    (default_addr, account_json))
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

# Create the validator account before running validator
create_validator_account()

# Node addresses map - helps validator identify nodes by their addresses
node_addresses = {
    '1DPPqS7kQNQMcn28du4sYJe8YKLUH8Jrig': 0,  # Node 0
    '1Lu9SwPPo7DJYrMVrZnkDXVw5y4aEeF1kz': 1,  # Node 1
    '14yikjhubj1sepvqsvzpRv4H6LhMN43XGD': 2,  # Node 2
    '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh': 3,  # Reserve node
}

# Enhanced validator selection function that rotates through addresses
def select_validator(available_accounts):
    import random
    
    # Define the staking/validator address that should NEVER be selected
    VALIDATOR_ADDRESS = '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh'
    
    # Filter accounts with stake AND exclude the validator address
    staked_accounts = [acc for acc in available_accounts 
                     if acc.get('staked', 0) > 0 
                     and acc.get('public_addr') != VALIDATOR_ADDRESS]
    
    print(f"Available validators (excluding {VALIDATOR_ADDRESS}): {[acc.get('public_addr') for acc in staked_accounts]}")
    
    if not staked_accounts:
        print("ERROR: No eligible validators found with stake!")
        return None
        
    # Select randomly based on stake weight
    total_stake = sum(acc['staked'] for acc in staked_accounts)
    selection = random.uniform(0, total_stake)
    
    cumulative = 0
    for account in staked_accounts:
        cumulative += account['staked']
        if selection <= cumulative:
            print(f"Selected validator {account['public_addr']} based on weighted random (stake: {account['staked']})")
            return account
            
    # Fallback to last account
    print(f"Fallback selection: {staked_accounts[-1]['public_addr']}")
    return staked_accounts[-1]

# Create a complete fixed validator module
with open('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/validator_node/fixed_validator.py', 'w') as f:
    with open('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/validatorNode/main.py', 'r') as src:
        validator_code = src.read()

def signal_handler(sig, frame):
    print("\\nShutting down validator node gracefully...")
    # Restore original init methods
    NodeDB.__init__ = original_nodedb_init
    BlockchainDB.__init__ = original_blockchaindb_init
    AccountDB.__init__ = original_accountdb_init
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    
    host = "127.0.0.1"
    port = 9003
    peer_list = [('127.0.0.1', 9000), ('127.0.0.1', 9001), ('127.0.0.1', 9002)]
    
    print(f"Starting validator node on port {port} with custom DB paths")
    
    # Create and run validator
    validator = ValidatorSelector(host, port, peer_list)
    validator.run()
