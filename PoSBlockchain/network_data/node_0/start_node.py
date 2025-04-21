
import sys
import os
import time
import signal
import configparser
import sqlite3
import json
from multiprocessing import Process, Manager
from multiprocessing.managers import BaseManager

ZERO_HASH = "0" * 64


# Add paths
sys.path.append("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain")
sys.path.append("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/node_0")

# Store node ID as a variable inside this script
NODE_ID = 0

# Custom database paths - make them absolute paths
blockchain_db_path = os.path.join("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/node_0/data", "blockchain.db")
node_db_path = os.path.join("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/node_0/data", "node.db")
account_db_path = os.path.join("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/node_0/data", "account.db")

# Create data directory if needed
data_dir = os.path.join("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data/node_0", "data")
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# Import and patch database classes BEFORE importing the Blockchain class
sys.path.insert(0, "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/code_node2")
from code_node2.Blockchain.Backend.core.database.db import NodeDB, BlockchainDB, AccountDB

# Save original inits
original_nodedb_init = NodeDB.__init__
original_blockchaindb_init = BlockchainDB.__init__
original_accountdb_init = AccountDB.__init__

# Patch NodeDB
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

# Patch BlockchainDB
def patched_blockchaindb_init(self, db_path=None):
    self.filepath = blockchain_db_path if not db_path else db_path
    self.table_name = "blocks"  # <-- FIXED
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
    self.filepath = self.filename
    self.conn = None
    self.connect()
    self.table_schema = '''
    CREATE TABLE IF NOT EXISTS accounts
    (public_addr TEXT PRIMARY KEY,
    value TEXT NOT NULL)
    '''
    self._create_table()

# Test database connections
print(f"Testing database connections...")
try:
    conn = sqlite3.connect(node_db_path)
    print(f"  - Connected to node database: {node_db_path}")
    conn.close()
    
    conn = sqlite3.connect(blockchain_db_path)
    print(f"  - Connected to blockchain database: {blockchain_db_path}")
    conn.close()
    
    conn = sqlite3.connect(account_db_path)
    print(f"  - Connected to account database: {account_db_path}")
    conn.close()
except Exception as e:
    print(f"Error testing database connections: {e}")
    sys.exit(1)

# Now import components after patching
from code_node2.Blockchain.Backend.core.pos_blockchain import Blockchain
from code_node2.Blockchain.Backend.core.network.syncManager import syncManager
from code_node2.Blockchain.client.account import account
from code_node2.Blockchain.Frontend.run import main as web_main

# Create default account if it doesn't exist
def create_default_account():
    import json 
    addresses = [
        {
            'public_addr': '1DPPqS7kQNQMcn28du4sYJe8YKLUH8Jrig',
            'privateKey': '96535626569238604192129746772702330856431841702880282095447645155889990991526',
            'public_key': '0248c103d04cc26840fa000d9614301fa5aee9d79b3a972e61c0712367658530b4'
        },
        {
            'public_addr': '14yikjhubj1sepvqsvzpRv4H6LhMN43XGD',
            'privateKey': '101116694282830344663754055609096743199644277746685645606199809457638491163865',
            'public_key': '0387c964aa67e33f0b93d3221b1bdfce382746cc7772e7497ca2677826f58d901d'
        },
        {
            'public_addr': '1Lu9SwPPo7DJYrMVrZnkDXVw5y4aEeF1kz',
            'privateKey': '46707185248865296345366463593339102785859545093537333336358754291775493830931',
            'public_key': '035b605b121b0382b340dd55bb960bd73c19bb5b484d61837b41beb29b1e8341b1'
        }
    ]
    
    # Determine address based on NODE_ID
    node_id = NODE_ID
    addr_index = node_id % len(addresses)
    selected_address = addresses[addr_index]

    # Build the node's own account data
    account_data = {
        'privateKey': selected_address['privateKey'],
        'public_addr': selected_address['public_addr'],
        'staked': 100 * 100000000,
        'public_key': selected_address['public_key']
    }

    print("Account details: " + json.dumps(selected_address))

    # --- Insert ALL accounts into account.db ---
    try:
        import sys
        sys.path.append("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain")
        from reset_accounts import ACCOUNTS
        import sqlite3
        import json
        conn = sqlite3.connect(account_db_path)
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS account (public_addr TEXT PRIMARY KEY, value TEXT NOT NULL)')
        for addr, acc_data in ACCOUNTS.items():
            cursor.execute('INSERT OR REPLACE INTO account VALUES (?, ?)', (addr, json.dumps(acc_data)))
        # Also ensure the node's own account is present (in case you want to override any field)
        cursor.execute('INSERT OR REPLACE INTO account VALUES (?, ?)', (selected_address['public_addr'], json.dumps(account_data)))
        conn.commit()
        conn.close()
        print(f"All accounts written to DB at: {account_db_path}")
    except Exception as e:
        print(f"Error writing account data: {e}")

    class SimpleAccount:
        def __init__(self, data):
            for key, value in data.items():
                setattr(self, key, value)

    return SimpleAccount(account_data)

def signal_handler(sig, frame):
    print(f"\\nShutting down node {NODE_ID} gracefully...")
    NodeDB.__init__ = original_nodedb_init
    BlockchainDB.__init__ = original_blockchaindb_init
    AccountDB.__init__ = original_accountdb_init
    sys.exit(0)

# ... inside create_node_script method ...

def simulate_random_transactions(volume, interval=30, tx_types="all"):

    # If volume is "none", don't start the simulator
    if volume == "none" or volume is None:
        print("[Sim] Transaction simulation disabled")
        return None
    
    import random
    import time
    import requests
    import threading
    import os # Import os for getpid
    import traceback # Import traceback for detailed error logging
    
    # Adjust interval based on volume
    if volume == "high":
        actual_interval = max(5, interval // 3)  # 3x more frequent
    elif volume == "low":
        actual_interval = interval * 2  # 2x less frequent
    elif volume == "medium": # medium
        actual_interval = interval
    else:
        volume = None
        
    # Set transaction type weights based on tx_types parameter
    if tx_types == "transfers":
        tx_weights = [1, 0, 0]  # Only transfers
    elif tx_types == "stake":
        tx_weights = [0, 1, 1]  # Only staking operations
    elif tx_types == "mixed":
        tx_weights = [2, 1, 1]  # More balanced mix
    else:  # "all" - default
        tx_weights = [5, 2, 1]  # 5:2:1:1 ratio for transfer:stake:unstake

    sim_account_db_path = account_db_path
    
    def transaction_loop():
        # Import necessary modules *inside* the thread function just in case
        from code_node2.Blockchain.Backend.core.database.db import AccountDB

        while True:
            
            
            
            try:
                # --- Add Debugging ---
                print(f"[Sim Debug 33999/{threading.get_ident()}] Creating AccountDB instance...")
                db_instance = AccountDB()
                print(f"[Sim Debug 33999/{threading.get_ident()}] Instance type: {type(db_instance)}")
                if hasattr(db_instance, 'table_name'):
                    print(f"[Sim Debug 33999/{threading.get_ident()}] Instance HAS table_name: '{db_instance.table_name}'")
                else:
                    print(f"[Sim Debug 33999/{threading.get_ident()}] Instance LACKS table_name attribute!")
                # --- End Debugging ---

                print(f"[Sim Debug 33999/{threading.get_ident()}] Calling db_instance.read()...")
                accounts = db_instance.read() # Use the instance we just checked
                print(f"[Sim Debug 33999/{threading.get_ident()}] db_instance.read() completed.")

                eligible_senders = [a for a in accounts if a.get('unspent', 0) > 0]

                if len(eligible_senders) < 2:
                    print("[Sim] Not enough accounts to simulate transactions")
                    time.sleep(actual_interval) # Use actual_interval
                    continue
                
                # Pick random sender and receiver
                sender = random.choice(eligible_senders)
                # Only pick receivers that are not the sender
                eligible_receivers = [a for a in accounts if a['public_addr'] != sender['public_addr']]
                receiver = random.choice(eligible_receivers)
                
                max_amount = min(sender.get('unspent', 0), 35)
                if max_amount < 1:
                    print(f"[Sim] Sender {sender['public_addr']} has insufficient funds.")
                    time.sleep(actual_interval)
                    continue
                    
                # Random amount (1 to 35 TDC) - Ensure amount is integer for wallet endpoint
                amount = int(random.uniform(1, max_amount))

                # Randomly select which node's web interface to use (e.g., 5900, 5901, 5902)
                # Assuming web_base_port is 5900 and num_nodes is 3
                web_ports = [5900 + i for i in range(3)] # Adjust range based on actual num_nodes if needed
                target_web_port = random.choice(web_ports)

                tx_type = random.choices(
                    ["transfer", "stake", "unstake"], 
                    weights=tx_weights, 
                    k=1
                )[0]

                if tx_type == "transfer":
                    # Prepare request parameters for the /wallet endpoint
                    params = {
                        "fromAddress": sender['public_addr'],
                        "toAddress": receiver['public_addr'],
                        "Amount": amount # Send the integer amount
                        
                    }

                    endpoint = f"http://localhost:{target_web_port}/wallet"

                elif tx_type == "stake":
                    params = {
                                "action": "stake", 
                                "fromAddress": sender['public_addr'], 
                                "amount": amount,
                                "lock_duration": random.randint(60*60, 60*60*24*30)  # 1 hour to 30 days in seconds
                            }

                    endpoint = f"http://localhost:{target_web_port}/stake"
                    print(f"[Sim] Sending {amount} TDC from {sender['public_addr']} to {receiver['public_addr']} via node on web port {target_web_port}")
                
                # elif tx_type == "claim":
                #     params = {
                #         "action": "claim", 
                #         "fromAddress": sender['public_addr'], 
                #         "amount_claim": amount
                #     }

                #     endpoint = f"http://localhost:{target_web_port}/stake"
                #     print(f"[Sim] Claiming {amount} TDC from {sender['public_addr']} via node on web port {target_web_port}")
                
                elif tx_type == "unstake":
                    params = {
                        "action": "unstake", 
                        "fromAddress": sender['public_addr'], 
                        "amount_unstake": amount
                    }

                    endpoint = f"http://localhost:{target_web_port}/stake"
                    print(f"[Sim] Unstaking {amount} TDC from {sender['public_addr']} via node on web port {target_web_port}")
                
                # Then send the request
                try:
                    res = requests.post(endpoint, data=params, timeout=10)
                    print(f"[Sim] {tx_type.capitalize()} submitted: {res.status_code} {res.text[:100]}")
                except Exception as e:
                    print(f"[Sim] Error submitting {tx_type}: {e}")
                

            except AttributeError as ae:
                 print(f"[Sim ATTRIBUTE ERROR 33999/{threading.get_ident()}] {ae}")
                 # Print attributes of the instance that caused the error if possible
                 try:
                     print(f"[Sim Debug] Attributes of db_instance: {db_instance.__dict__}")
                 except NameError:
                     print("[Sim Debug] db_instance not defined at point of error.")
                 except Exception as e_inner:
                     print(f"[Sim Debug] Could not inspect instance: {e_inner}")
                 time.sleep(actual_interval) # Wait before retrying

            except requests.exceptions.RequestException as re:
                print(f"[Sim] Network error during transaction simulation: {re}")
                time.sleep(actual_interval) # Wait before retrying network errors

            except Exception as e:
                print(f"[Sim] Unexpected error in transaction simulation: {e}")
                traceback.print_exc() # Print full traceback for unexpected errors
                time.sleep(actual_interval) # Wait before retrying general errors
                
            # Wait before next transaction using the calculated interval
            time.sleep(actual_interval)
    
    # Start simulation in a background thread
    sim_thread = threading.Thread(target=transaction_loop, daemon=True)
    sim_thread.start()
    print("[Sim] Transaction simulator started")
    return sim_thread

# Register the Blockchain class with BaseManager
class BlockchainManager(BaseManager):
    pass

# Must register BEFORE instantiating manager
BlockchainManager.register('Blockchain', Blockchain)
BlockchainManager.register('dict') # Register dict to create shared dictionaries


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    
    # Read config
    config = configparser.ConfigParser()
    config.read('config.ini')
    localHost = config['DEFAULT']['host']
    localHostPort = int(config['MINER']['port'])
    webport = int(config['Webhost']['port'])
    
    print(f"Starting node {NODE_ID} on port {localHostPort} with custom DB paths")
    
    # Get default account
    default_account = create_default_account()
    print(f"Account details: public_addr={getattr(default_account, 'public_addr', None)}, balance={getattr(default_account, 'balance', None)}")
    
    # HYBRID APPROACH: Use standard Manager for dicts, custom manager for Blockchain
    with Manager() as std_manager:
        # Create shared dictionaries with standard manager
        mem_pool = std_manager.dict()
        utxos = std_manager.dict()
        newBlockAvailable = std_manager.dict()
        secondaryChain = std_manager.dict()
        
        # Start the custom manager for Blockchain
        blockchain_manager = BlockchainManager()
        blockchain_manager.start()
        
        # Start web interface
        webapp = Process(target=web_main, args=(utxos, mem_pool, webport, localHostPort))
        webapp.start()
        
        # Initialize blockchain through the custom manager with CORRECT parameter order
        try:
            # FIXED: Using the correct parameter order per definition
            blockchain = blockchain_manager.Blockchain(
                utxos,                # First param: utxos
                mem_pool,             # Second param: mem_pool
                newBlockAvailable,    # Third param: newBlockAvailable (CORRECT ORDER)
                secondaryChain,       # Fourth param: secondaryChain (CORRECT ORDER)
                localHostPort, 
                localHost
            )

            blockchain.ZERO_HASH = ZERO_HASH  # Explicitly add ZERO_HASH attribute

            
            # Set properties directly
            blockchain.host = localHost
            blockchain.localHostPort = localHostPort
            blockchain.my_public_addr = default_account.public_addr
            
            print(f"Setting blockchain public address to: {blockchain.my_public_addr}")
            blockchain.setup_node()
            print("Blockchain initialized successfully through BlockchainManager")
            
        except Exception as e:
            print(f"Error initializing blockchain: {e}")
            import traceback
            traceback.print_exc()
            blockchain = None
        
        # Create syncManager with the manager-created blockchain
        sync = syncManager(
            localHost,                  # host
            localHostPort,              # port
            mem_pool,                   # MemoryPool: your shared mem_pool dict
            blockchain,                 # blockchain: your custom Blockchain proxy
            localHostPort,              # localHostPort (again)
            newBlockAvailable,          # newBlockAvailable
            secondaryChain,             # secondaryChain
            my_public_addr=default_account.public_addr  # my_public_addr
        )
        
        # Start server process
        startServer = Process(target=sync.spinUpServer)
        startServer.start()
        print(f"Server started on port {localHostPort}")

        # WAIT FOR FLASK TO BE READY
        import requests
        wait_url = f"http://localhost:{webport}"
        print(f"Waiting for web UI at {wait_url}…")
        while True:
            try:
                r = requests.get(wait_url, timeout=1)
                if r.status_code == 200:
                    print("Web UI up, starting simulation")
                    break
                
            except Exception:
                pass
            time.sleep(1)

        if "none" != "none" and "none":
            print(f"[Sim] Starting transaction simulation: volume={"none"}, interval={"30"}, tx_types={all}")
            simulate_random_transactions(
                volume="none",
                interval=30,
                tx_types="all"
            )
        else:
            print("[Sim] Transaction simulation is disabled for this node.")
        # Node idles, waiting for instructions
        try:
            while True:
                time.sleep(10)
                print(f"Node {NODE_ID} active on port {localHostPort}, web: {webport}")
                
        except KeyboardInterrupt:
            webapp.terminate()
            startServer.terminate()
