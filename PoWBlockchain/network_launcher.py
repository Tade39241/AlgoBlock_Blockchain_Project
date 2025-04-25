import configparser
import json
import os
import sys
import time
import socket
import argparse
import subprocess
from multiprocessing import Process

import requests
from blockchain_code.Blockchain.genesis_block_generator import generate_genesis_block, save_genesis_block

PROJECT_ROOT  = os.path.dirname(os.path.abspath(__file__))
CODE_ROOT    = os.path.join(PROJECT_ROOT, "blockchain_code")
if CODE_ROOT not in sys.path:
    sys.path.insert(0, CODE_ROOT)
ENTRY_SCRIPT  = os.path.join(
    PROJECT_ROOT,
    "code", "Blockchain", "Backend", "core", "blockchain.py"
)


import shutil
import sqlite3
import configparser
from pathlib import Path

class NetworkLauncher:
    def __init__(self, num_nodes=3, base_port=9000, web_base_port=5900,data_dir="network_data",
                 sim_volume=None, sim_interval=30, sim_tx_types="all"):
        self.num_nodes = num_nodes
        self.base_port = base_port
        self.web_base_port = web_base_port
        self.data_dir = os.path.join(PROJECT_ROOT, data_dir)
        self.nodes = []
        self.node_info = []
        self.host = '127.0.0.1'

        # Add simulation parameters
        self.sim_volume = sim_volume
        self.sim_interval = sim_interval
        self.sim_tx_types = sim_tx_types
        
        # Ensure network_data directory exists
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def setup_node_directories(self):
        """Create directories for each node with just config & start script."""
        print(f"Setting up {self.num_nodes} node directories...")
        
        for i in range(self.num_nodes):
            node_port = self.base_port + i
            web_port = self.web_base_port + i

            node_dir = os.path.join(self.data_dir, f"node_{i}")
            os.makedirs(node_dir, exist_ok=True)

            # Ensure a 'data' subfolder
            data_dir = os.path.join(node_dir, "data")
            os.makedirs(data_dir, exist_ok=True)

            # Generate config.ini
            self.generate_config(i, node_dir)

            # Record node metadata for later
            info = {
                "id":       i,
                "dir":      node_dir,
                "port":     node_port,
                "web_port": web_port,
                "host":     self.host
            }
            self.node_info.append(info)

            # Emit the start_node.py tailored to this node
            self.create_node_script(info)

            print(f"Node {i} set up at {node_dir} with port {node_port}")

    def generate_config(self, node_id, node_dir):
        """Generate config.ini for a specific node"""
        config = configparser.ConfigParser()
        
        config['DEFAULT'] = {
            'host': self.host
        }
        
        config['MINER'] = {
            'port': str(self.base_port + node_id),
        }
        
        config['Webhost'] = {
            'port': str(self.web_base_port + node_id)
        }
        
        # Write config to file
        with open(os.path.join(node_dir, 'config.ini'), 'w') as configfile:
            config.write(configfile)

    def update_node_db(self):
        """Initialize/reset each nodes node.db with the full list of ports."""
        import sqlite3

        for node in self.node_info:
            # Ensure data directory exists
            data_dir = os.path.join(node["dir"], "data")
            os.makedirs(data_dir, exist_ok=True)

            node_db_path = os.path.join(data_dir, "node.db")
            print(f"Updating node DB at {node_db_path!r}")

            conn = None
            try:
                # Open with timeout and WAL mode for safe concurrency
                conn = sqlite3.connect(node_db_path, timeout=5)
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA busy_timeout=5000;")

                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS nodes")
                cursor.execute("CREATE TABLE IF NOT EXISTS nodes (port INTEGER PRIMARY KEY)")

                # Insert every node’s port into each node.db
                for info in self.node_info:
                    cursor.execute(
                        "INSERT OR IGNORE INTO nodes (port) VALUES (?)",
                        (info["port"],)
                    )

                conn.commit()
                print(f"✅ node.db updated for node {node['id']}")
            except sqlite3.OperationalError as e:
                print(f"Error updating node.db for node {node['id']}: {e}")
            finally:
                if conn:
                    conn.close()

    def wait_for_all_web_uis(self):
        print("Waiting for all node web UIs to be ready...")
        all_ready = False
        while not all_ready:
            all_ready = True
            for node in self.node_info:
                url = f"http://{node['host']}:{node['web_port']}"
                try:
                    r = requests.get(url, timeout=1)
                    if r.status_code != 200:
                        all_ready = False
                        break
                except Exception:
                    all_ready = False
                    break
            if not all_ready:
                time.sleep(1)
        print("All node web UIs are up!")


    def wait_for_all_network_ports(self):
        print("Waiting for all node network ports to be ready...")
        all_ready = False
        while not all_ready:
            all_ready = True
            for node in self.node_info:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.settimeout(1)
                    s.connect((node['host'], node['port']))
                    s.sendall(b'PORTCHECK')
                    s.close()
                except Exception:
                    all_ready = False
                    break
            if not all_ready:
                time.sleep(1)
        print("All node network ports are up!")

    
    def start_node(self, node_info):
        """Start a single node process"""
        node_dir = node_info["dir"]
        node_script = os.path.join(node_dir, "start_node.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{PROJECT_ROOT}:{env.get('PYTHONPATH', '')}"

        logs_dir = os.path.join(node_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)


        stdout_log = open(os.path.join(logs_dir, "stdout.log"), "w")
        stderr_log = open(os.path.join(logs_dir, "stderr.log"), "w")
        
        # Create start script if it doesn't exist
        self.create_node_script(node_info)
        
        node_process = subprocess.Popen(
            [sys.executable, node_script],
            cwd=node_dir,
            env=env,
            stdout=stdout_log,
            stderr=stderr_log,
            text=True
        )
        
        print(f"Node {node_info['id']} started with PID {node_process.pid}")
        return node_process

    def create_node_script(self, node_info):
        node_dir = node_info["dir"]
        node_id = node_info["id"]
        data_dir = os.path.join(node_dir, "data")
        script_path = os.path.join(node_dir, "start_node.py")
        
        script_content = rf"""

import sys
import os
import logging

# Setup logging to the shared transaction log
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_file_path = os.path.join(project_root, "network_data", "transaction.log")
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
file_handler = logging.FileHandler(log_file_path, mode='w')
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
file_handler.setFormatter(formatter)
logging.getLogger().addHandler(file_handler)
logging.basicConfig(level=logging.INFO)

import time
import signal
import configparser
import sqlite3
import json
from multiprocessing import Process, Manager
from multiprocessing.managers import BaseManager
import multiprocessing
from threading import Thread 

try:
    multiprocessing.set_start_method('fork')
except RuntimeError:
    pass

ZERO_HASH = "0" * 64

# Add paths
sys.path.append("{PROJECT_ROOT}")
sys.path.append("{node_dir}")

# Store node ID as a variable inside this script
NODE_ID = {node_id}

# Add both code/ and blockchain_code/ directories to the path
sys.path.insert(0, os.path.join("{PROJECT_ROOT}", 'blockchain_code'))

# Custom database paths - make them absolute paths
blockchain_db_path = os.path.join("{data_dir}", "blockchain.db")
node_db_path = os.path.join("{data_dir}", "node.db")
account_db_path = os.path.join("{data_dir}", "account.db")

# Create data directory if needed
data_dir = os.path.join("{node_dir}", "data")
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# Import and patch database classes BEFORE importing the Blockchain class
sys.path.insert(0, "{PROJECT_ROOT}/blockchain_code")
from blockchain_code.Blockchain.Backend.core.database.db import NodeDB, BlockchainDB, AccountDB

# Import blockchain components
from blockchain_code.Blockchain.Backend.core.blockchain import Blockchain
from blockchain_code.Blockchain.Backend.core.network.syncManager import syncManager
from blockchain_code.Blockchain.Frontend.run import main


def miner_entry(utxos, mem_pool, newBlockAvailable, secondaryChain,localHostPort, localHost, node_id, db_path,my_public_addr):
            bc = Blockchain(utxos, mem_pool, newBlockAvailable, secondaryChain,localHostPort, localHost, node_id=node_id, db_path=db_path, my_public_addr=my_public_addr)
            bc.main()

# Test database connections
print(f"Testing database connections...")
try:
    conn = sqlite3.connect(node_db_path)
    print(f"  - Connected to node database: {{node_db_path}}")
    conn.close()
    
    conn = sqlite3.connect(blockchain_db_path)
    print(f"  - Connected to blockchain database: {{blockchain_db_path}}")
    conn.close()
    
    conn = sqlite3.connect(account_db_path)
    print(f"  - Connected to account database: {{account_db_path}}")
    conn.close()
except Exception as e:
    print(f"Error testing database connections: {{e}}")
    sys.exit(1)

# Now import components after patching
from blockchain_code.Blockchain.Backend.core.blockchain import Blockchain
from blockchain_code.Blockchain.Backend.core.network.syncManager import syncManager
from blockchain_code.Blockchain.client.account import account
from blockchain_code.Blockchain.Frontend.run import main as web_main

def create_default_account():
    import json 
    addresses = [
        {{
            'public_addr': '1DPPqS7kQNQMcn28du4sYJe8YKLUH8Jrig',
            'privateKey': '96535626569238604192129746772702330856431841702880282095447645155889990991526',
            'public_key': '0248c103d04cc26840fa000d9614301fa5aee9d79b3a972e61c0712367658530b4'
        }},
        {{
            'public_addr': '14yikjhubj1sepvqsvzpRv4H6LhMN43XGD',
            'privateKey': '101116694282830344663754055609096743199644277746685645606199809457638491163865',
            'public_key': '0387c964aa67e33f0b93d3221b1bdfce382746cc7772e7497ca2677826f58d901d'
        }},
        {{
            'public_addr': '1Lu9SwPPo7DJYrMVrZnkDXVw5y4aEeF1kz',
            'privateKey': '46707185248865296345366463593339102785859545093537333336358754291775493830931',
            'public_key': '035b605b121b0382b340dd55bb960bd73c19bb5b484d61837b41beb29b1e8341b1'
        }}
    ]
    
    # Determine address based on NODE_ID
    node_id = NODE_ID
    addr_index = node_id % len(addresses)
    selected_address = addresses[addr_index]

    # Build the node's own account data
    account_data = {{
        'privateKey': selected_address['privateKey'],
        'public_addr': selected_address['public_addr'],
        'public_key': selected_address['public_key']
    }}

    print("Account details: " + json.dumps(selected_address))

    # --- Insert ALL accounts into account.db ---
    try:
        import sys
        sys.path.append("{PROJECT_ROOT}")
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
        print(f"All accounts written to DB at: {{account_db_path}}")
    except Exception as e:
        print(f"Error writing account data: {{e}}")


    class SimpleAccount:
        def __init__(self, data):
            for key, value in data.items():
                setattr(self, key, value)

    return SimpleAccount(account_data)

def signal_handler(sig, frame):
    print(f"\\nShutting down node NODE_ID gracefully...")
    sys.exit(0)

# def simulate_random_transactions(volume, interval=30, tx_types="all",num_nodes=3):


#     # If volume is "none", don't start the simulator
#     if volume == "none" or volume is None:
#         print("[Sim] Transaction simulation disabled")
#         return None
    
#     import random
#     import time
#     import requests
#     import threading
#     import os # Import os for getpid
#     import traceback # Import traceback for detailed error logging
    
#     # Adjust interval based on volume
#     if volume == "high":
#         target_network_tps = 10    # e.g. 10 transactions/sec total
#         actual_interval = max(
#             1,
#             int({self.num_nodes} / target_network_tps)
#         )
#     elif volume == "medium":
#         actual_interval = interval
#     elif volume == "low":
#         actual_interval = interval * 2
#     else:
#         actual_interval = None
        
#     # Set transaction type weights based on tx_types parameter
#     if tx_types == "transfers":
#         tx_weights = [1, 0, 0]  # Only transfers
#     elif tx_types == "stake":
#         tx_weights = [0, 1, 1]  # Only staking operations
#     elif tx_types == "mixed":
#         tx_weights = [2, 1, 1]  # More balanced mix
#     else:  # "all" - default
#         tx_weights = [5, 2, 1]  # 5:2:1:1 ratio for transfer:stake:unstake

#     sim_account_db_path = account_db_path

#     my_address = default_account.public_addr
#     my_web_port = webport

#     def transaction_loop():
#         # Import necessary modules *inside* the thread function just in case
#         from code_node2.Blockchain.Backend.core.database.db import AccountDB
#         from code_node2.Blockchain.Backend.core.database.db import AccountDB, BlockchainDB
#         from code_node2.Blockchain.client.account import account
#         from code_node2.Blockchain.Backend.util.util import decode_base58
#         from code_node2.Blockchain.Backend.core.tx import TxOut

#         def get_utxo_set():
#             blockchain_db = BlockchainDB()
#             blocks = blockchain_db.read_all_blocks()
#             utxos = {{}}
#             spent = set()
#             for block in blocks:
#                 txs = block[0]['Txs'] if isinstance(block, list) else block['Txs']
#                 for tx_dict in txs:
#                     txid = tx_dict['TxId']
#                     for txin in tx_dict['tx_ins']:
#                         spent.add((txin['prev_tx'], txin['prev_index']))
#                     for idx, tx_out in enumerate(tx_dict['tx_outs']):
#                         key = (txid, idx)
#                         if key not in spent:
#                             utxos[key] = TxOut.from_dict(tx_out)
#             for key in spent:
#                 utxos.pop(key, None)
#             return utxos

#         while True:
#             try:
#                 utxos = get_utxo_set()

#                 # Merge in pending mempool transactions so simulator  sees change outputs immediately
#                 for tx in mem_pool.values():
#                     update_utxo_set(tx, utxos)
#                 # ← END ADD

#                 acct = account.get_account(my_address)

#                 # # --- Add Debugging ---
#                 # print(f"[Sim Debug {os.getpid()}/{{threading.get_ident()}}] Creating AccountDB instance...")
#                 # db_instance = AccountDB()
#                 # print(f"[Sim Debug {os.getpid()}/{{threading.get_ident()}}] Instance type: {{type(db_instance)}}")
#                 # if hasattr(db_instance, 'table_name'):
#                 #     print(f"[Sim Debug {os.getpid()}/{{threading.get_ident()}}] Instance HAS table_name: '{{db_instance.table_name}}'")
#                 # else:
#                 #     print(f"[Sim Debug {os.getpid()}/{{threading.get_ident()}}] Instance LACKS table_name attribute!")
#                 # # --- End Debugging ---

#                 if acct is None:
#                     print(f"[Sim] Account {{my_address}} not found.")
#                     time.sleep(actual_interval)
#                     continue
                
#                 print("[DEBUG][SIM] UTXO set for account", acct.public_addr)
#                 for (txid, idx), tx_out in utxos.items():
#                     print(f"  {{txid}}:{{idx}} amount={{tx_out.amount}} cmds={{tx_out.script_publickey.cmds}}")

#                 spendable, staked = acct.get_balance(utxos)
#                 print(f"[DEBUG][SIM] Account {{acct.public_addr}} spendable={{spendable}} staked={{staked}}")
#                 for (txid, idx), tx_out in utxos.items():
#                     print(f"[DEBUG][SIM] UTXO {{txid}}:{{idx}} amount={{tx_out.amount}} cmds={{tx_out.script_publickey.cmds}}")
#                 if spendable <= 0 and tx_types != "unstake":
#                     print(f"[Sim] My address {{my_address}} has no spendable funds.")
#                     time.sleep(actual_interval)
#                     continue
                    
#                 if staked <= 0 and tx_types == "unstake":
#                     print(f"[Sim] My address {{my_address}} has no staked funds to unstake.")
#                     time.sleep(actual_interval)
#                     continue
                    
#                 tx_type = random.choices(
#                     ["transfer", "stake", "unstake"], 
#                     weights=tx_weights, 
#                     k=1
#                 )[0]

                
#                 max_amount = min(spendable, 35 * 100000000) if tx_type != "unstake" else min(staked, 35 * 100000000)
#                 if max_amount < 1:
#                     print(f"[Sim] My address {{my_address}} has insufficient funds for {{tx_type}}.")
#                     time.sleep(actual_interval)
#                     continue
#                 amount = int(random.uniform(1 * 100000000, max_amount))

#                 target_web_port = my_web_port

#                 if tx_type == "transfer":
#                     # Pick a random receiver (not myself)
#                     db_instance = AccountDB()
#                     accounts = db_instance.read()
#                     eligible_receivers = [a for a in accounts if a['public_addr'] != my_address]
#                     if not eligible_receivers:
#                         print("[Sim] No eligible receivers for transfer.")
#                         time.sleep(actual_interval)
#                         continue
#                     receiver = random.choice(eligible_receivers)
#                     params = {{
#                         "fromAddress": my_address,
#                         "toAddress": receiver['public_addr'],
#                         "Amount": amount / 100000000 # Convert to TDC for API
#                     }}
#                     endpoint = f"http://localhost:{{target_web_port}}/wallet"
#                     print(f"[Sim] Attempting to Send {{amount/100000000}} TDC from {{my_address}} to {{receiver['public_addr']}} via node on web port {{target_web_port}}")
#                     logging.info(f"[Sim] Attempting to Send  {{amount/100000000}} TDC from {{my_address}} to {{receiver['public_addr']}} via node on web port {{target_web_port}}")

#                 elif tx_type == "stake":
#                     params = {{
#                         "action": "stake",
#                         "fromAddress": my_address,
#                         "amount": amount / 100000000,
#                         "lock_duration": random.randint(60*60, 60*60*24*30)
#                     }}
#                     endpoint = f"http://localhost:{{target_web_port}}/stake"
#                     print(f"[Sim] Attempting to stake {{amount/100000000}} TDC from {{my_address}} via node on web port {{target_web_port}}")
#                     logging.info(f"[Sim] Attempting to stake {{amount/100000000}} TDC from {{my_address}} via node on web port {{target_web_port}}")

        
                
#                 # elif tx_type == "claim":
#                 #     params = {{
#                 #         "action": "claim", 
#                 #         "fromAddress": sender['public_addr'], 
#                 #         "amount_claim": amount
#                 #     }}

#                 #     endpoint = f"http://localhost:{{target_web_port}}/stake"
#                 #     print(f"[Sim] Claiming {{amount}} TDC from {{sender['public_addr']}} via node on web port {{target_web_port}}")
                
#                 elif tx_type == "unstake":
#                     params = {{
#                         "action": "unstake",
#                         "fromAddress": my_address,
#                         "amount_unstake": amount / 100000000
#                     }}
#                     endpoint = f"http://localhost:{{target_web_port}}/stake"
#                     print(f"[Sim] Attempting to unstake {{amount/100000000}} TDC from {{my_address}} via node on web port {{target_web_port}}")
#                     logging.info(f"[Sim] Attempting to unstake  {{amount/100000000}} TDC from {{my_address}} via node on web port {{target_web_port}}")
                
#                 # Then send the request
#                 try:
#                     res = requests.post(endpoint, json=params, timeout=10)
#                     print(f"[Sim] {{tx_type.capitalize()}} submitted: {{res.status_code}} {{res.text[:100]}}")
#                     logging.info(f"[Sim] {{tx_type.capitalize()}} submitted: {{res.status_code}} {{res.text[:100]}}")
#                 except Exception as e:
#                     print(f"[Sim] Error submitting {{tx_type}}: {{e}}")
                

#             except AttributeError as ae:
#                  print(f"[Sim ATTRIBUTE ERROR {os.getpid()}/{{threading.get_ident()}}] {{ae}}")
#                  # Print attributes of the instance that caused the error if possible
#                  try:
#                      print(f"[Sim Debug] Attributes of db_instance: {{db_instance.__dict__}}")
#                  except NameError:
#                      print("[Sim Debug] db_instance not defined at point of error.")
#                  except Exception as e_inner:
#                      print(f"[Sim Debug] Could not inspect instance: {{e_inner}}")
#                  time.sleep(actual_interval) # Wait before retrying

#             except requests.exceptions.RequestException as re:
#                 print(f"[Sim] Network error during transaction simulation: {{re}}")
#                 time.sleep(actual_interval) # Wait before retrying network errors

#             except Exception as e:
#                 print(f"[Sim] Unexpected error in transaction simulation: {{e}}")
#                 traceback.print_exc() # Print full traceback for unexpected errors
#                 time.sleep(actual_interval) # Wait before retrying general errors
                
#             # Wait before next transaction using the calculated interval
#             time.sleep(actual_interval)
    
#     # Start simulation in a background thread
#     sim_thread = threading.Thread(target=transaction_loop, daemon=True)
#     sim_thread.start()
#     print("[Sim] Transaction simulator started")
#     return sim_thread


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

    print(f"Starting node {{NODE_ID}} on port {{localHostPort}} with custom DB paths")
    
    # Get default account
    default_account = create_default_account()
    print(f"Account details: public_addr={{getattr(default_account, 'public_addr', None)}}, balance=None")

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

        os.environ["BLOCKCHAIN_DB_PATH"] = blockchain_db_path  # blockchain_db_path is your node-specific path
        webapp = Process(target=web_main, args=(utxos, mem_pool, webport, localHostPort,NODE_ID, default_account.public_addr))
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
                localHost,
                NODE_ID,
                blockchain_db_path,
                default_account.public_addr
            )

            blockchain.ZERO_HASH = ZERO_HASH  # Explicitly add ZERO_HASH attribute

            # Set properties directly
            # blockchain.host = localHost
            # blockchain.localHostPort = localHostPort
            # blockchain.my_public_addr = default_account.public_addr
            # blockchain.node_id = NODE_ID

        except Exception as e:
            print(f"Error initializing blockchain: {{e}}")
            import traceback
            traceback.print_exc()
            blockchain = None

        # --- ADD DEBUG LOG (Before creating syncManager) ---
        print(f"[start_node {{NODE_ID}} DEBUG] Blockchain object before syncManager init: {{blockchain}} (Type: {{type(blockchain)}})", flush=True)
        if blockchain:
            print(f"[start_node {{NODE_ID}} DEBUG] Blockchain has 'db' attribute: {{hasattr(blockchain, 'db')}}", flush=True)
            if hasattr(blockchain, 'db'):
                print(f"[start_node {{NODE_ID}} DEBUG] Blockchain.db object: {{blockchain.db}} (Type: {{type(blockchain.db)}})", flush=True)
        # --- END DEBUG LOG ---

        # Create syncManager with the manager-created blockchain
        sync = syncManager(
            localHost,                  # host
            localHostPort,              # port
            mem_pool,                   # MemoryPool: your shared mem_pool dict
            blockchain,                 # blockchain: your custom Blockchain proxy
            localHostPort,              # localHostPort (again)
            newBlockAvailable,          # newBlockAvailable
            secondaryChain,             # secondaryChain
            my_public_addr=default_account.public_addr, # my_public_addr
            node_id=NODE_ID,
            db_path=blockchain_db_path
        )

        # Start server process
        startServer = Thread(target=sync.spinUpServer, daemon=True)
        startServer.start()
        print(f"Server started on port {{localHostPort}}")
        time.sleep(2)  # Give it a moment to start

        # Do an initial download of the chain from peers
        print(f"[Startup] Node {{NODE_ID}} syncing blockchain …")
        try:
            blockchain.startSync()      # <— pulls blocks from peers into your DB
            print(f"[Startup] Node {{NODE_ID}} sync complete")
        except Exception as e:
            print(f"[Startup] Node {{NODE_ID}} sync failed: {{e}}")

        # WAIT FOR FLASK TO BE READY
        import requests
        wait_url = f"http://localhost:{{webport}}"
        print(f"Waiting for web UI at {{wait_url}}…")
        while True:
            try:
                r = requests.get(wait_url, timeout=1)
                if r.status_code == 200:
                    print("Web UI up, starting simulation")
                    break
                
            except Exception:
                pass
            time.sleep(1)

        # Pass NODE_ID to the blockchain object so it knows which database to use

        mining_process = Process(
            target=miner_entry,
            # Add blockchain_db_path to the args tuple
            args=(utxos, mem_pool, newBlockAvailable, secondaryChain,
                localHostPort, localHost, NODE_ID, blockchain_db_path, default_account.public_addr)
        )

        mining_process.daemon = True  # Set as daemon so it terminates with the main process
        mining_process.start()
        print(f"Mining process started on node {{NODE_ID}}")

        # if "{self.sim_volume}" != "none" and "{self.sim_volume}":
        #         print(f"[Sim] Starting transaction simulation: volume={{"{self.sim_volume}"}}, interval={{"{self.sim_interval}"}}, tx_types={{{self.sim_tx_types}}}")
        #         simulate_random_transactions(
        #             volume="{self.sim_volume}",
        #             interval={self.sim_interval},
        #             tx_types="{self.sim_tx_types}",
        #             num_nodes={self.num_nodes}
        #         )
        # else:
        #     print("[Sim] Transaction simulation is disabled for this node.")
        # Node idles, waiting for instructions
        try:
            while True:
                time.sleep(10)
                print(f"Node {{NODE_ID}} active on port {{localHostPort}}, web: {{webport}}")
                
        except KeyboardInterrupt:
            webapp.terminate()
            startServer.terminate()

"""
        
        with open(script_path, 'w') as f:
            f.write(script_content)
        print(f"Created start script for node_{node_id}")

    def copy_genesis_block(self):
        """Copy genesis block to all nodes"""
        # Define the primary genesis block path
        primary_genesis_path = os.path.join(PROJECT_ROOT, "blockchain_code", "genesis_block.json")
        
        # Check if primary path exists, otherwise look in alternative locations
        if os.path.exists(primary_genesis_path):
            genesis_path = primary_genesis_path
            print(f"Using existing genesis block from {genesis_path}")
        else:
            # Fallback paths if main path doesn't exist
            fallback_paths = [
                os.path.join(PROJECT_ROOT, "genesis_block.json"),
                os.path.join(os.path.dirname(PROJECT_ROOT), "blockchain_code", "genesis_block.json")
            ]
            
            genesis_path = None
            for path in fallback_paths:
                if os.path.exists(path):
                    genesis_path = path
                    print(f"Using fallback genesis block from {genesis_path}")
                    break
        
        if not genesis_path:
            print("No genesis block found at expected locations.")
            print(f"Expected primary path: {primary_genesis_path}")
            
            # Generate a new genesis block if none exists
            if input("Would you like to generate a new genesis block? (y/n): ").lower() == 'y':
                new_genesis_path = os.path.join(PROJECT_ROOT, "blockchain_code", "genesis_block.json")
                os.makedirs(os.path.dirname(new_genesis_path), exist_ok=True)
                
                from blockchain_code.Blockchain.genesis_block_generator import generate_genesis_block, save_genesis_block
                genesis_block = generate_genesis_block()
                save_genesis_block(genesis_block, new_genesis_path)
                
                print(f"Generated new genesis block at {new_genesis_path}")
                genesis_path = new_genesis_path
            else:
                return False
        
        # 1. Read the genesis block from the JSON file
        print(f"Reading genesis block from {genesis_path}")
        genesis_data = None
        try:
            with open(genesis_path, 'r') as f:
                genesis_data = json.load(f)
                # --- DEBUG START ---
                print("--- DEBUG: Data loaded from genesis_block.json ---")
                print(f"Type: {type(genesis_data)}")
                print(f"Content sample: {str(genesis_data)[:200]}...") # Print first 200 chars
                # --- CHANGE THIS CHECK ---
                # OLD CHECK: if not isinstance(genesis_data, list):
                if not isinstance(genesis_data, dict): # NEW CHECK: Expect a dictionary
                    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                    # Update the error message
                    print("ERROR: genesis_data IS NOT A DICTIONARY AFTER LOADING!")
                    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                    return False # Stop if format is wrong
                # --- END CHANGE ---
        except Exception as e:
            print(f"Error reading or parsing genesis block file {genesis_path}: {e}")
            return False
        
        if genesis_data is None:
             print("Failed to load genesis_data.")
             return False
        
        print(f"Initializing {self.num_nodes} blockchain databases with genesis block...")
        
        # 2. Write to each node's blockchain.db
        for i in range(self.num_nodes):
            # Copy the JSON file first
            node_data_dir = os.path.join(self.data_dir, f"node_{i}", "data")
            os.makedirs(node_data_dir, exist_ok=True)
            shutil.copy(genesis_path, os.path.join(node_data_dir, "genesis_block.json"))
            
            # Now initialize the blockchain.db
            db_path = os.path.join(node_data_dir, "blockchain.db")
            
            try:
                # Ensure the DB exists with the right schema
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS blocks
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL)
                ''')
                
                # Check if genesis block already exists
                cursor.execute("SELECT COUNT(*) FROM blocks")
                if cursor.fetchone()[0] == 0:
                    # --- DEBUG START (for node_0) ---
                    data_to_insert_str = json.dumps(genesis_data)
                    if i == 0:
                        print(f"--- DEBUG node_0: Inserting Genesis Block ---")
                        print(f"Type of data before dumps: {type(genesis_data)}")
                        print(f"String to insert: {data_to_insert_str[:200]}...")
                        if not data_to_insert_str.startswith('{'):
                             print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                             print("ERROR: node_0 INSERT STRING DOES NOT START WITH '{'!")
                             print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                    # --- DEBUG END ---

                    # Insert genesis block as the first block
                    cursor.execute(
                        "INSERT INTO blocks (data) VALUES (?)",
                        (json.dumps(genesis_data),)
                    )
                    conn.commit()
                    print(f"  - Initialized blockchain.db for node_{i}")
                else:
                    # --- DEBUG START (for node_0) ---
                    if i == 0:
                         print(f"--- DEBUG node_0: DB already contains data, SKIPPING initialization ---")
                    # --- DEBUG END ---
                    print(f"  - blockchain.db for node_{i} already contains data, skipping initialization")
                    
                conn.close()
            except Exception as e:
                print(f"Error initializing blockchain.db for node_{i}: {e}")
                return False
        
        print("All nodes' blockchain databases initialized with genesis block")
        return True

    def start_network(self):
        """Start all nodes in the network"""
        print("Starting blockchain network...")

        try:
            # First make sure node directories are set up
            self.setup_node_directories()

             # Copy and initialize genesis block
            if not self.copy_genesis_block():
                print("Failed to initialize genesis block")
                return False


            # Import database classes directly
            sys.path.insert(0, os.path.join(PROJECT_ROOT, 'blockchain_code'))
            from blockchain_code.Blockchain.Backend.core.database.db import NodeDB, BlockchainDB, AccountDB
            from blockchain_code.Blockchain.Backend.core.blockchain import Blockchain

            # Update NodeDB with all nodes
            self.update_node_db()

            # Start each node
            for node_info in self.node_info:
                node_process = self.start_node(node_info)
                self.nodes.append(node_process)
                # Give each node a moment to initialize
                time.sleep(2)
                # print(f"Node {node_info['id']} started successfully on port {node_info['port']}")
                print("Node {} started successfully on port {}".format(node_info['id'], node_info['port']))

            self.wait_for_all_web_uis()
            self.wait_for_all_network_ports()

            running_nodes = [p for p in self.nodes if p.poll() is None]
            if len(running_nodes) != len(self.nodes):
                print(f"WARNING: Only {len(running_nodes)}/{len(self.nodes)} nodes are running")

            print(f"Network of {self.num_nodes} nodes is now running")

             # Save network configuration for reference
            self.save_network_config()

        except Exception as e:
            print(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            self.stop_network()
            sys.exit(1)
    
    def save_network_config(self):
        """Save the network configuration to a JSON file"""
        config = {
            "num_nodes": self.num_nodes,
            "base_port": self.base_port,
            "web_base_port": self.web_base_port,
            "host": self.host,
            "nodes": self.node_info,
            "validator_port": self.base_port + self.num_nodes
        }
        
        config_path = os.path.join(self.data_dir, "network_config.json")
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"Network configuration saved to {config_path}")

    def collect_logs(self):
        """Collect logs from all nodes"""
        log_dir = os.path.join(self.data_dir, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        for node in self.nodes:
            stdout, stderr = node.communicate(timeout=1)
            
            with open(os.path.join(log_dir, f"node_{node.pid}.stdout.log"), 'w') as f:
                f.write(stdout)
            
            with open(os.path.join(log_dir, f"node_{node.pid}.stderr.log"), 'w') as f:
                f.write(stderr)

    def stop_network(self):
        """Stop all nodes and the validator"""
        print("Stopping blockchain network...")

        try:
            self.collect_logs()
        except Exception as e:
            print(f"Error collecting logs: {e}")
    
        # Stop all nodes
        for i, node in enumerate(self.nodes):
            node.terminate()
            print(f"Node {i} stopped")
        
        print("Network shutdown complete")
    
# Main function to run the network launcher
def main():
    parser = argparse.ArgumentParser(description='Launch a PoS blockchain network with multiple nodes')
    parser.add_argument('--nodes', type=int, default=3, help='Number of nodes to launch')
    parser.add_argument('--base-port', type=int, default=9000, help='Base port for nodes')
    parser.add_argument('--web-base-port', type=int, default=5900, help='Base port for web interfaces')
    parser.add_argument('--data-dir', type=str, default='network_data', help='Directory for node data')

    # Add simulation parameters
    parser.add_argument('--sim-volume', type=str, choices=['high', 'medium', 'low', 'none'], 
                      default='none', help='Transaction simulation volume')
    parser.add_argument('--sim-interval', type=int, default=30, 
                      help='Base interval between simulated transactions (seconds)')
    parser.add_argument('--sim-tx-types', type=str, default='all',
                      choices=['all', 'transfers', 'stake', 'mixed'],
                      help='Types of transactions to simulate')
    
    args = parser.parse_args()
   
    # Create and run the network launcher
    launcher = NetworkLauncher(
        num_nodes=args.nodes,
        base_port=args.base_port,
        web_base_port=args.web_base_port,
        data_dir=args.data_dir,
        sim_volume=args.sim_volume,
        sim_interval=args.sim_interval,
        sim_tx_types=args.sim_tx_types
    )


    
    try:
        launcher.start_network()
        print("Network is running. Press Ctrl+C to stop...")
        
        # Keep the main process running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down network...")
        launcher.stop_network()
    except Exception as e:
        print(f"Error: {e}")
        launcher.stop_network()

if __name__ == "__main__":
    main()