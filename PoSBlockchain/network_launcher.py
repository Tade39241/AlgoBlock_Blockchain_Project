import logging
import os
import random
import re
import socket
import sqlite3
import sys
import time
import signal
import subprocess
import configparser
import shutil
from pathlib import Path
import argparse
import json
from multiprocessing import Process, Manager
from reset_accounts import ACCOUNTS

import requests
from reset_accounts import find_node_dirs
# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(PROJECT_ROOT)

# Import validator node selector
sys.path.append(os.path.join(PROJECT_ROOT, 'validatorNode'))

# --- Add this basic configuration near the top ---
# Configure logging for this module/process
log_format = '%(message)s'
# Log INFO level messages and above to standard error
logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stderr)
# You could also configure a FileHandler here if you want logs in a separate file per process
# --- End configuration ---

# Get a logger for this module
logger = logging.getLogger('network_launcher')

class NetworkLauncher:
    def __init__(self, num_nodes=3, base_port=9000, web_base_port=5900, data_dir="network_data",
                 sim_volume=None, sim_interval=30, sim_tx_types="all"):
        self.num_nodes = num_nodes
        self.base_port = base_port
        self.web_base_port = web_base_port
        self.data_dir = os.path.join(PROJECT_ROOT, data_dir)
        self.nodes = []
        self.validator_process = None
        self.node_info = []
        self.host = "127.0.0.1"

            # Add simulation parameters
        self.sim_volume = sim_volume
        self.sim_interval = sim_interval
        self.sim_tx_types = sim_tx_types
        
        # Create data directory if it doesn't exist
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    # def setup_node_directories(self):
    #     """Create directories for each node with appropriate configuration"""
    #     print(f"Setting up {self.num_nodes} node directories...")
        
    #     for i in range(self.num_nodes):
    #         node_dir = os.path.join(self.data_dir, f"node_{i}")
    #         if not os.path.exists(node_dir):
    #             os.makedirs(node_dir)
                
    #         # Copy necessary files from code_node2 as template
    #         template_dir = os.path.join(PROJECT_ROOT, "code_node2")
            
    #         # Copy Blockchain directory structure
    #         blockchain_dir = os.path.join(node_dir, "Blockchain")
    #         if not os.path.exists(blockchain_dir):
    #             shutil.copytree(
    #                 os.path.join(template_dir, "Blockchain"), 
    #                 blockchain_dir,
    #                 symlinks=False,
    #                 ignore=shutil.ignore_patterns('*.pyc', '__pycache__', '*.db')
    #             )
            
    #         # Generate config.ini
    #         self.generate_config(i, node_dir)
            
    #         # Record node information
    #         node_port = self.base_port + i
    #         self.node_info.append({
    #             "id": i,
    #             "dir": node_dir,
    #             "port": node_port,
    #             "web_port": self.web_base_port + i,
    #             "host": self.host
    #         })
            
    #         print(f"Node {i} set up at {node_dir} with port {node_port}")

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
            'simulateBTC': 'True'
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

    def start_validator_node(self):
        """Start the validator node as a separate process"""
        validator_port = self.base_port + self.num_nodes  # Use a port after all nodes
        validator_dir = os.path.join(self.data_dir, "validator_node")
        if not os.path.exists(validator_dir):
            os.makedirs(validator_dir)

        logs_dir = os.path.join(validator_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        stdout_log = open(os.path.join(logs_dir, "stdout.log"), "w")
        stderr_log = open(os.path.join(logs_dir, "stderr.log"), "w")
        
        # Use a common data directory for all validator databases
        validator_data_dir = os.path.join(validator_dir, "data")
        if not os.path.exists(validator_data_dir):
            os.makedirs(validator_data_dir, exist_ok=True)
            print(f"Created data directory: {validator_data_dir}")
        
        import sqlite3
        for db_name in ["node.db", "blockchain.db", "account.db"]:
            db_path = os.path.join(validator_data_dir, db_name)
            conn = sqlite3.connect(db_path)
            conn.close()
            print(f"Created validator database: {db_path}")

         # 1. Populate node.db with all node ports
        node_db_path = os.path.join(validator_data_dir, "node.db")
        conn = sqlite3.connect(node_db_path)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS nodes")
        cursor.execute("CREATE TABLE IF NOT EXISTS nodes (port INTEGER PRIMARY KEY)")
        for node in self.node_info:
            cursor.execute("INSERT OR IGNORE INTO nodes (port) VALUES (?)", (node["port"],))
        conn.commit()
        conn.close()
        print(f"Validator node.db populated with all node ports.")

        # 2. Populate account.db with all accounts
        account_db_path = os.path.join(validator_data_dir, "account.db")
        conn = sqlite3.connect(account_db_path)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS account")
        cursor.execute("CREATE TABLE IF NOT EXISTS account (public_addr TEXT PRIMARY KEY, value TEXT NOT NULL)")
        for addr, account_data in list(ACCOUNTS.items())[:self.num_nodes]:
            cursor.execute("INSERT OR REPLACE INTO account VALUES (?, ?)", (addr, json.dumps(account_data)))
        conn.commit()
        conn.close()
        print(f"Validator account.db populated with all accounts.")
        
        peer_list = [(node["host"], node["port"]) for node in self.node_info]
        print(f"Starting validator node on port {validator_port} with peers: {peer_list}")
        
        env = os.environ.copy()
        env["VALIDATOR_DB_DIR"] = validator_data_dir
        self.create_validator_script(validator_dir, validator_port, peer_list)
        
        validator_script = os.path.join(validator_dir, "run_validator.py")
        validator_process = subprocess.Popen(
            [sys.executable, validator_script],
            cwd=validator_dir,
            env=env,
            stdout=stdout_log,
            stderr=stderr_log,
            text=True
        )
        self.validator_process = validator_process
        print(f"Validator node started with PID {self.validator_process.pid}")
        
    def create_validator_script(self, validator_dir, validator_port, peer_list):
        import os
        script_path = os.path.join(validator_dir, "run_validator.py")
        PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
        abs_valid_dir = os.path.abspath(validator_dir)
        abs_data_dir = os.path.join(abs_valid_dir, "data")
    
        script_content = f"""

# Add paths


import sys
import os
import time
import signal
import json
import sqlite3
import threading
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', stream=sys.stderr)
logger = logging.getLogger(__name__) # Use logger
log_format = '%(asctime)s %(levelname)s: %(message)s'
# Log INFO level messages and above specifically to stderr (which gets redirected)
logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stderr)
# Keep the file handler if you still want transaction.log
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_file_path = os.path.join(project_root, "network_data", "transaction.log")
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
file_handler = logging.FileHandler(log_file_path, mode='w')
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
file_handler.setFormatter(formatter)
logging.getLogger().addHandler(file_handler)

# Add a test log message right after setup
logging.info(f"[PID {{os.getpid()}}] start_node.py script started. Logging configured.")

sys.path.append("{PROJECT_ROOT}")
sys.path.append("{validator_dir}")
sys.path.insert(0, "{PROJECT_ROOT}/code_node2")

from Blockchain.Backend.core.network.connection import Node
from Blockchain.Backend.core.network.network import NetworkEnvelope

NUM_NODES = {self.num_nodes}

# Custom database paths
data_dir = os.path.join(r"{validator_dir}", "data")
os.makedirs(data_dir, exist_ok=True)

nested = os.path.join(data_dir, "data")
if not os.path.exists(nested):
    try:
        os.symlink(data_dir, nested)
        print(f"[Validator] symlinked {{nested}} → {{data_dir}}")
    except FileExistsError:
        pass
        
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
    self.filename = blockchain_db_path if not db_path else db_path
    self.filepath = blockchain_db_path if not db_path else db_path
    self.table_name = "blocks"
    self.conn = None
    logging.info(f"[PID {{os.getpid()}}] BlockchainDB attempting to connect to: {{self.filepath}}")
    try:
        self.connect()
        logging.info(f"[PID {{os.getpid()}}] BlockchainDB connected successfully to: {{self.filepath}}")
    except Exception as e:
        logging.error(f"[PID {{os.getpid()}}] BlockchainDB FAILED to connect to: {{self.filepath}} - Error: {{e}}")
        raise # Re-raise the exception
    print(f"[DEBUG] BlockchainDB will use path: {{self.filepath}}")
    # self.connect()
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
    self.table_name = "account"
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
    print(f"  - Connected to validator node database: {{node_db_path}}")
    conn.close()
    conn = sqlite3.connect(blockchain_db_path)
    print(f"  - Connected to validator blockchain database: {{blockchain_db_path}}")
    conn.close()
    conn = sqlite3.connect(account_db_path)
    print(f"  - Connected to validator account database: {{account_db_path}}")
    conn.close()
except Exception as e:
    print(f"Error testing validator database connections: {{e}}")
    sys.exit(1)

# Node addresses map - helps validator identify nodes by their addresses
node_addresses = {{
    '1DPPqS7kQNQMcn28du4sYJe8YKLUH8Jrig': 0,  # Node 0
    '1Lu9SwPPo7DJYrMVrZnkDXVw5y4aEeF1kz': 1,  # Node 1
    '14yikjhubj1sepvqsvzpRv4H6LhMN43XGD': 2,  # Node 2
    '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh': 3,  # Reserve node
}}

# Create validator account with stake
def create_validator_account():
    default_addr = '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh'
    account_data = {{
        'public_addr': default_addr,
        'privateKey': '90285630861639623347665892885049342176040030896554662509747065762830918365196',
        'public_key': '0428492a0256e1d7114ec48663516a44213f201afa16f425abb512339cc7bfed3964fc3d26e22a61f6aa0e3dc6549526a76be4f7fbdb9f57e0ef526c3b4ccc1913',
        'staked': 100 * 100000000
    }}
    try:
        conn = sqlite3.connect(account_db_path)
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS account (public_addr TEXT PRIMARY KEY, value TEXT NOT NULL)')
        account_json = json.dumps(account_data)
        cursor.execute('INSERT OR REPLACE INTO account VALUES (?, ?)', (default_addr, account_json))
        conn.commit()
        conn.close()
        print(f"Created validator account with stake: {{default_addr}}")
        # Verify the account was written
        conn = sqlite3.connect(account_db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM account WHERE public_addr = ?', (default_addr,))
        result = cursor.fetchone()
        if result:
            print(f"Validator account verified with data: {{result[0][:30]}}...")
        else:
            print("WARNING: Validator account not found after writing!")
        conn.close()
    except Exception as e:
        print(f"Error creating validator account: {{e}}")

create_validator_account()

print("[Validator][DEBUG] account.db contains:")
conn = sqlite3.connect(account_db_path)
for public_addr, value in conn.execute("SELECT public_addr, value FROM account"):
    print("   ", public_addr)
conn.close()

from code_node2.Blockchain.Backend.core.database.db import BlockchainDB
from code_node2.Blockchain.Backend.util.util import decode_base58, encode_base58, hash256
from code_node2.Blockchain.Backend.core.tx import Tx, TxOut
from code_node2.Blockchain.Backend.core.script import Script

# --- SyncManager for receiving blocks ---
def start_sync_server(host, port):
    from code_node2.Blockchain.Backend.core.network.syncManager import syncManager
    from code_node2.Blockchain.Backend.core.pos_blockchain import Blockchain
    # Use dummy shared dicts for mempool/utxos (not used by validator)
    mem_pool = {{}}
    utxos = {{}}
    newBlockAvailable = {{}}
    secondaryChain = {{}}
    blockchain = Blockchain(utxos, mem_pool, newBlockAvailable, secondaryChain, port, host)
    sync = syncManager(host, port, mem_pool, blockchain=blockchain)
    sync.spinUpServer()

# Start sync server in background thread
def launch_sync_thread(host, port):
    t = threading.Thread(target=start_sync_server, args=(host, port), daemon=True)
    t.start()
    print(f"[Validator] Sync server started on {{host}}:{{port}}")

def build_utxos_from_blocks(blocks):
    utxos = {{}}
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
    staked = {{}}
    for (txid, idx), tx_out in utxo_set.items():
        cmds = tx_out.script_publickey.cmds
        if len(cmds) == 3 and cmds[0] == b'\\x00':
            h160 = cmds[1]
            addr = encode_base58(b'\\x00' + h160 + hash256(b'\\x00' + h160)[:4])
            staked[addr] = staked.get(addr, 0) + tx_out.amount
    return staked

class ValidatorSelector:
    def __init__(self, host, port, peer_list):
        self.host = host
        self.port = port
        self.peer_list = peer_list[:NUM_NODES]

    def select_validator(self, utxo_set):
        import random
        staked = get_staked_balances_from_utxos(utxo_set)

        validators = [(addr, amt) for addr, amt in staked.items() if amt > 0 and addr != VALIDATOR_ADDRESS]
        logger.info(f"Available validators (excluding {{VALIDATOR_ADDRESS}}): {{[addr for addr, _ in validators]}}")
        if not validators:
            logger.warning("ERROR: No eligible validators found with stake!")
            return None
        total_stake = sum(amt for addr, amt in validators)
        selection = random.uniform(0, total_stake)
        cumulative = 0
        for addr, amt in validators:
            cumulative += amt
            if selection <= cumulative:
                logger.info(f"Selected validator {{addr}} based on weighted random (stake: {{amt}})")
                return addr
        logger.warning(f"Fallback selection: {{validators[-1][0]}}")
        return validators[-1][0]

    def broadcast_selection(self, selected_validator):
        message_dict = {{
            "type": "validator_selection",
            "selected_validator": selected_validator
        }}
        payload = json.dumps(message_dict).encode()
        envelope = NetworkEnvelope(b'valselect', payload)
        
        for peer in self.peer_list:
            try:
                peer_host = peer[0]
                peer_port = int(peer[1])  # Convert port to integer if necessary.
                node = Node(self.host, peer_port)
                sock = node.connect(peer_port)
                print(f"Connecting to peer {{peer_host}}:{{peer_port}} to broadcast selection...")
                sock.sendall(envelope.serialise())
                sock.close()
                print(f"[ValidatorSelector] Successfully sent validator selection to {{(peer_host, peer_port)}}")
            except Exception as e:
                print(f"[ValidatorSelector] Error sending selection to {{(peer_host, peer_port)}}: {{e}}")


    def run(self):
        while True:
            try:
                utxo_set = get_latest_utxo_set()
                selected_validator = self.select_validator(utxo_set)
                if selected_validator:
                    staked = get_staked_balances_from_utxos(utxo_set)
                    logger.info(f"[ValidatorSelector] Selected Validator: {{selected_validator}} with stake {{staked[selected_validator]}}")
                    self.broadcast_selection(selected_validator)
                else:
                    logger.error("[ValidatorSelector] No eligible validator found.")
                logger.debug(f"Validator sleeping for 15 seconds.")
                time.sleep(20)
            except Exception as e:
                logger.error(f"!!!!!!!! Exception in ValidatorSelector run loop !!!!!!!!: {{e}}", exc_info=True)
                # Sleep longer on error to avoid spamming logs
                time.sleep(30)

def signal_handler(sig, frame):
    print("\\nShutting down validator node gracefully...")
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    host = "{self.host}"
    port = {validator_port}
    peer_list = {peer_list}
    print(f"Starting validator node on port {{port}} with custom DB paths")

    from code_node2.Blockchain.Backend.core.pos_blockchain import Blockchain
    utxos = {{}}
    mem_pool = {{}}
    newBlockAvailable = {{}}
    secondaryChain = {{}}

    validator_lock = threading.Lock()

    blockchain = Blockchain(utxos, mem_pool, newBlockAvailable, secondaryChain, port, host,validator_lock)
    if blockchain.fetch_last_block() is None:
        from reset_accounts import ACCOUNTS
        ACCOUNTS = dict(list(ACCOUNTS.items())[:NUM_NODES])
        print("[VALIDATOR]", ACCOUNTS)
        print("[Validator] No blocks found, creating genesis block...")
        blockchain.GenesisBlock()
        print("[Validator] Genesis block created and broadcast.")
    else:
        print("[Validator] Blockchain already initialized.")

    validator = ValidatorSelector(host, port, peer_list)
    validator.run()
    """
    
        with open(script_path, 'w') as f:
            f.write(script_content)
    
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
        abs_node_dir = os.path.abspath(node_dir)
        node_id = node_info["id"]
        data_dir = os.path.join(node_dir, "data")
        abs_data_dir = os.path.join(abs_node_dir, "data")
        script_path = os.path.join(node_dir, "start_node.py")
        
        script_content = rf"""
import sys
import os
import logging
import time
import signal
import configparser
import sqlite3
import json
import stat
from multiprocessing import Process, Manager
from multiprocessing.managers import BaseManager
from reset_accounts import ACCOUNTS

log_format = '%(asctime)s %(levelname)s: %(message)s'
# Log INFO level messages and above specifically to stderr (which gets redirected)
logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stderr)
# Keep the file handler if you still want transaction.log
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_file_path = os.path.join(project_root, "network_data", "transaction.log")
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
file_handler = logging.FileHandler(log_file_path, mode='w')
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
file_handler.setFormatter(formatter)
logging.getLogger().addHandler(file_handler)

# Add a test log message right after setup
logging.info(f"[PID {{os.getpid()}}] start_node.py script started. Logging configured.")



ZERO_HASH = "0" * 64


# Add paths
sys.path.append("{PROJECT_ROOT}")
sys.path.append("{abs_node_dir}")

# Store node ID as a variable inside this script
NODE_ID = {node_id}
NUM_NODES = {self.num_nodes}

# --- DEFINE ABSOLUTE PATHS FIRST ---
# Use the absolute data_dir passed from the launcher
abs_data_dir = "{abs_data_dir}"
# Ensure the directory exists (using the absolute path)
if not os.path.exists(abs_data_dir):
    os.makedirs(abs_data_dir)

nested = os.path.join(abs_data_dir, "data")
if not os.path.exists(nested):
    try:
        os.symlink(abs_data_dir, nested)
        logging.info(f"[PID {{os.getpid()}}] symlinked {{nested}} → {{abs_data_dir}}")
    except FileExistsError:
        pass

# Define absolute paths for databases
blockchain_db_path = os.path.join(abs_data_dir, "blockchain.db")
node_db_path = os.path.join(abs_data_dir, "node.db")
account_db_path = os.path.join(abs_data_dir, "account.db")

# Create data directory if needed
data_dir = os.path.join("{node_dir}", "data")
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# Import and patch database classes BEFORE importing the Blockchain class
sys.path.insert(0, "{PROJECT_ROOT}/code_node2")
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
    try:
        self.connect()
        # --- ADD WAL and BUSY TIMEOUT ---
        if self.conn:
            try:
                self.conn.execute("PRAGMA journal_mode=WAL;")
                self.conn.execute("PRAGMA busy_timeout = 5000;") # Wait 5 seconds if locked
                logging.info(f"[PID {{os.getpid()}}] NodeDB set WAL mode and busy_timeout for {{self.filepath}}")
            except Exception as e_pragma:
                logging.warning(f"[PID {{os.getpid()}}] NodeDB FAILED to set WAL/busy_timeout for {{self.filepath}}: {{e_pragma}}")
        # --- END ADD ---
    except Exception as e_connect:
        logging.error(f"[PID {{os.getpid()}}] NodeDB FAILED to connect to: {{self.filepath}} - Error: {{e_connect}}")
        raise
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
    # self.connect()
    logging.info(f"[PID {{os.getpid()}}] BlockchainDB attempting to connect to: {{self.filepath}}")
    try:
        self.connect()
        logging.info(f"[PID {{os.getpid()}}] BlockchainDB connected successfully to: {{self.filepath}}")
        # --- ADD WAL and BUSY TIMEOUT ---
        if self.conn:
            try:
                self.conn.execute("PRAGMA journal_mode=WAL;")
                self.conn.execute("PRAGMA busy_timeout = 5000;") # Wait 5 seconds if locked
                logging.info(f"[PID {{os.getpid()}}] BlockchainDB set WAL mode and busy_timeout for {{self.filepath}}")
            except Exception as e_pragma:
                logging.warning(f"[PID {{os.getpid()}}] BlockchainDB FAILED to set WAL/busy_timeout for {{self.filepath}}: {{e_pragma}}")
        # --- END ADD ---
    except Exception as e_connect:
        logging.error(f"[PID {{os.getpid()}}] BlockchainDB FAILED to connect to: {{self.filepath}} - Error: {{e_connect}}")
        raise
    print(f"[DEBUG] BlockchainDB will use path: {{self.filepath}}")
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
    try:
        self.connect()
        # --- ADD WAL and BUSY TIMEOUT ---
        if self.conn:
            try:
                self.conn.execute("PRAGMA journal_mode=WAL;")
                self.conn.execute("PRAGMA busy_timeout = 5000;") # Wait 5 seconds if locked
                logging.info(f"[PID {{os.getpid()}}] AccountDB set WAL mode and busy_timeout for {{self.filepath}}")
            except Exception as e_pragma:
                logging.warning(f"[PID {{os.getpid()}}] AccountDB FAILED to set WAL/busy_timeout for {{self.filepath}}: {{e_pragma}}")
        # --- END ADD ---
    except Exception as e_connect:
        logging.error(f"[PID {{os.getpid()}}] AccountDB FAILED to connect to: {{self.filepath}} - Error: {{e_connect}}")
        raise
    self.table_name = "account"
    self.table_schema = '''
    CREATE TABLE IF NOT EXISTS account
    (public_addr TEXT PRIMARY KEY,
    value TEXT NOT NULL)
    '''
    self._create_table()

# Test database connections
print(f"Testing database connections...")
db_files_to_chmod = []
try:
    conn = sqlite3.connect(node_db_path)
    print(f"  - Connected to node database: {{node_db_path}}")
    conn.close()
    db_files_to_chmod.append(node_db_path)
    
    conn = sqlite3.connect(blockchain_db_path)
    print(f"  - Connected to blockchain database: {{blockchain_db_path}}")
    conn.close()
    db_files_to_chmod.append(blockchain_db_path)
    
    conn = sqlite3.connect(account_db_path)
    print(f"  - Connected to account database: {{account_db_path}}")
    conn.close()
    db_files_to_chmod.append(account_db_path)
except Exception as e:
    print(f"Error testing database connections: {{e}}")
    sys.exit(1)

# Set permissions for database files
print(f"Setting permissions for database files...")
for db_file in db_files_to_chmod:
    try:
        # Set permissions: Owner rw, Group rw, Others ---
        os.chmod(db_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)
        print(f"  - Set permissions for {{db_file}} to 660")
    except OSError as e:
        print(f"Warning: Could not set permissions for {{db_file}}: {{e}}")



# Now import components after patching
from code_node2.Blockchain.Backend.core.pos_blockchain import Blockchain
from code_node2.Blockchain.Backend.core.network.syncManager import syncManager
from code_node2.Blockchain.client.account import account
from code_node2.Blockchain.Frontend.run import main as web_main
from reset_accounts import ACCOUNTS
import sqlite3, json

# Create default account if it doesn't exist
def create_default_account():
    from reset_accounts import ACCOUNTS
    import json
    import sqlite3


    addresses = list(ACCOUNTS.values())
    
    # Determine address based on NODE_ID
    node_id = NODE_ID
    addr_index = node_id % len(addresses)
    selected_address = addresses[addr_index]

    # Build the node's own account data
    account_data = {{
        'privateKey': selected_address['privateKey'],
        'public_addr': selected_address['public_addr'],
        'staked': 0 * 100000000,
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

        for addr, acc_data in list(ACCOUNTS.items())[:NUM_NODES]:
            cursor.execute(
                'INSERT OR REPLACE INTO account VALUES (?, ?)',
                (addr, json.dumps(acc_data))
            )
        
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
    print(f"\\nShutting down node {{NODE_ID}} gracefully...")
    NodeDB.__init__ = original_nodedb_init
    BlockchainDB.__init__ = original_blockchaindb_init
    AccountDB.__init__ = original_accountdb_init
    sys.exit(0)

# ... inside create_node_script method ...

def simulate_random_transactions(volume, interval=30, tx_types="all",num_nodes=3):


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
        target_network_tps = 6    # e.g. 4 transactions/sec total
        actual_interval = max(
            1,
            int({self.num_nodes} / target_network_tps)
        )
    elif volume == "medium":
        actual_interval = interval
    elif volume == "low":
        actual_interval = interval * 2
    else:
        actual_interval = None
        
    # Set transaction type weights based on tx_types parameter
    if tx_types == "transfers":
        tx_weights = [1, 0]  # Only transfers
    elif tx_types == "stake":
        tx_weights = [0, 1]  # Only staking operations
    elif tx_types == "mixed":
        tx_weights = [2, 1]  # More balanced mix
    else:  # "all" - default
        tx_weights = [5, 3]  # 5:2:1 ratio for transfer:stake:unstake

    sim_account_db_path = account_db_path

    my_address = default_account.public_addr
    my_web_port = webport
    
    def transaction_loop():
        # Import necessary modules *inside* the thread function just in case
        from code_node2.Blockchain.Backend.core.database.db import AccountDB
        from code_node2.Blockchain.Backend.core.database.db import AccountDB, BlockchainDB
        from code_node2.Blockchain.client.account import account
        from code_node2.Blockchain.Backend.util.util import decode_base58
        from code_node2.Blockchain.Backend.core.tx import TxOut

        # def get_utxo_set():
        #     blockchain_db = BlockchainDB()
        #     blocks = blockchain_db.read_all_blocks()
        #     utxos = {{}}
        #     spent = set()
        #     for block in blocks:
        #         txs = block[0]['Txs'] if isinstance(block, list) else block['Txs']
        #         for tx_dict in txs:
        #             txid = tx_dict['TxId']
        #             for txin in tx_dict['tx_ins']:
        #                 spent.add((txin['prev_tx'], txin['prev_index']))
        #             for idx, tx_out in enumerate(tx_dict['tx_outs']):
        #                 key = (txid, idx)
        #                 if key not in spent:
        #                     utxos[key] = TxOut.from_dict(tx_out)
        #     for key in spent:
        #         utxos.pop(key, None)
        #     return utxos

        while True:
            try:

                # # --- Add Debugging ---
                # print(f"[Sim Debug {os.getpid()}/{{threading.get_ident()}}] Creating AccountDB instance...")
                # db_instance = AccountDB()
                # print(f"[Sim Debug {os.getpid()}/{{threading.get_ident()}}] Instance type: {{type(db_instance)}}")
                # if hasattr(db_instance, 'table_name'):
                #     print(f"[Sim Debug {os.getpid()}/{{threading.get_ident()}}] Instance HAS table_name: '{{db_instance.table_name}}'")
                # else:
                #     print(f"[Sim Debug {os.getpid()}/{{threading.get_ident()}}] Instance LACKS table_name attribute!")
                # # --- End Debugging ---

                # if acct is None:
                #     print(f"[Sim] Account {{my_address}} not found.")
                #     time.sleep(actual_interval)
                #     continue
                
                # print("[DEBUG][SIM] UTXO set for account", acct.public_addr)
                # for (txid, idx), tx_out in utxos.items():
                #     print(f"  {{txid}}:{{idx}} amount={{tx_out.amount}} cmds={{tx_out.script_publickey.cmds}}")

                # spendable, staked = acct.get_balance(utxos)
                # print(f"[DEBUG][SIM] Account {{acct.public_addr}} spendable={{spendable}} staked={{staked}}")
                # for (txid, idx), tx_out in utxos.items():
                #     print(f"[DEBUG][SIM] UTXO {{txid}}:{{idx}} amount={{tx_out.amount}} cmds={{tx_out.script_publickey.cmds}}")
                # if spendable <= 0 and tx_types != "unstake":
                #     print(f"[Sim] My address {{my_address}} has no spendable funds.")
                #     time.sleep(actual_interval)
                #     continue
                    
                # if staked <= 0 and tx_types == "unstake":
                #     print(f"[Sim] My address {{my_address}} has no staked funds to unstake.")
                #     time.sleep(actual_interval)
                #     continue
                    
                tx_type = random.choices(
                    ["transfer", "stake"], 
                    weights=tx_weights, 
                    k=1
                )[0]


                
                # max_amount = min(spendable, 35 * 100000000) if tx_type != "unstake" else min(staked, 35 * 100000000)
                # if max_amount < 1:
                #     print(f"[Sim] My address {{my_address}} has insufficient funds for {{tx_type}}.")
                #     time.sleep(actual_interval)
                #     continue
                # amount = int(random.uniform(1 * 100000000, max_amount))
                
                amount_tdc = random.uniform(0.1, 35.0)
                target_web_port = my_web_port

                if tx_type == "transfer":
                    # Pick a random receiver (not myself)
                    db_instance = AccountDB()
                    accounts = db_instance.read()
                    eligible_receivers = [a for a in accounts if a['public_addr'] != my_address]
                    if not eligible_receivers:
                        print("[Sim] No eligible receivers for transfer.")
                        time.sleep(actual_interval)
                        continue
                    receiver = random.choice(eligible_receivers)
                    params = {{
                        "fromAddress": my_address,
                        "toAddress": receiver['public_addr'],
                        "Amount": amount_tdc
                    }}
                    endpoint = f"http://localhost:{{target_web_port}}/wallet"
                    print(f"[Sim] Attempting to Send {{amount_tdc}} TDC from {{my_address}} to {{receiver['public_addr']}} via node on web port {{target_web_port}}")
                    logging.info(f"[Sim] Attempting to Send  {{amount_tdc}} TDC from {{my_address}} to {{receiver['public_addr']}} via node on web port {{target_web_port}}")

                elif tx_type == "stake":
                    params = {{
                        "action": "stake",
                        "fromAddress": my_address,
                        "amount": amount_tdc,
                        "lock_duration": random.randint(60*60, 60*60*24*30)
                    }}
                    endpoint = f"http://localhost:{{target_web_port}}/stake"
                    print(f"[Sim] Attempting to stake {{amount_tdc}} TDC from {{my_address}} via node on web port {{target_web_port}}")
                    logging.info(f"[Sim] Attempting to stake {{amount_tdc}} TDC from {{my_address}} via node on web port {{target_web_port}}")
                
                # elif tx_type == "unstake":
                #     params = {{
                #         "action": "unstake",
                #         "fromAddress": my_address,
                #         "amount_unstake": amount_tdc
                #     }}
                #     endpoint = f"http://localhost:{{target_web_port}}/stake"
                #     print(f"[Sim] Attempting to unstake {{amount_tdc}} TDC from {{my_address}} via node on web port {{target_web_port}}")
                #     logging.info(f"[Sim] Attempting to unstake  {{amount_tdc}} TDC from {{my_address}} via node on web port {{target_web_port}}")
                
                # Then send the request
                try:
                    res = requests.post(endpoint, json=params, timeout=10)
                    print(f"[Sim] {{tx_type.capitalize()}} submitted: {{res.status_code}} {{res.text[:100]}}")
                    logging.info(f"[Sim] {{tx_type.capitalize()}} submitted: {{res.status_code}} {{res.text[:100]}}")
                except Exception as e:
                    print(f"[Sim] Error submitting {{tx_type}}: {{e}}")
                

            except AttributeError as ae:
                 print(f"[Sim ATTRIBUTE ERROR {os.getpid()}/{{threading.get_ident()}}] {{ae}}")
                 # Print attributes of the instance that caused the error if possible
                 try:
                     print(f"[Sim Debug] Attributes of db_instance: {{db_instance.__dict__}}")
                 except NameError:
                     print("[Sim Debug] db_instance not defined at point of error.")
                 except Exception as e_inner:
                     print(f"[Sim Debug] Could not inspect instance: {{e_inner}}")
                 time.sleep(actual_interval) # Wait before retrying

            except requests.exceptions.RequestException as re:
                print(f"[Sim] Network error during transaction simulation: {{re}}")
                time.sleep(actual_interval) # Wait before retrying network errors

            except Exception as e:
                print(f"[Sim] Unexpected error in transaction simulation: {{e}}")
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
BlockchainManager.register('dict') # Register dict to create shared dictionaries
BlockchainManager.register('Blockchain',
                            Blockchain,exposed=(
                                        'buildUTXOS',
                                        'get_utxos',      # <<< --- ADD THIS LINE --- >>>
                                        'startSync',
                                        'setup_node',
                                        'utxos',          # Note: Exposing 'utxos' directly gives the attribute, not a method call
                                        'write_on_disk',
                                        'update_utxo_set',
                                        'clean_mempool',
                                        'addBlock',
                                        'get_height',
                                        'get_tip_hash'
                                        )
                                    )

if __name__ == '__main__':
    from threading import Lock # Or multiprocessing.Lock if needed cross-process

    # Create the lock *before* the manager starts or objects are created
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
    print(f"Account details: public_addr={{getattr(default_account, 'public_addr', None)}}, balance={{getattr(default_account, 'balance', None)}}")
    
    # HYBRID APPROACH: Use standard Manager for dicts, custom manager for Blockchain
    with Manager() as std_manager:
        # Create shared dictionaries with standard manager
        mem_pool = std_manager.dict()
        utxos = std_manager.dict()
        newBlockAvailable = std_manager.dict()
        secondaryChain = std_manager.dict()
        shared_state_lock = std_manager.Lock()
        
        # Start the custom manager for Blockchain
        blockchain_manager = BlockchainManager()
        blockchain_manager.start()

        try:
            # FIXED: Using the correct parameter order per definition
            blockchain = blockchain_manager.Blockchain(
                utxos,                # First param: utxos
                mem_pool,             # Second param: mem_pool
                newBlockAvailable,    # Third param: newBlockAvailable (CORRECT ORDER)
                secondaryChain,       # Fourth param: secondaryChain (CORRECT ORDER)
                localHostPort, 
                localHost,
                shared_state_lock
            )

            blockchain.ZERO_HASH = ZERO_HASH  # Explicitly add ZERO_HASH attribute

            
            # Set properties directly
            blockchain.host = localHost
            blockchain.localHostPort = localHostPort
            blockchain.my_public_addr = default_account.public_addr
            
            print(f"Setting blockchain public address to: {{blockchain.my_public_addr}}")
            blockchain.setup_node()
            print("Blockchain initialized successfully through BlockchainManager")
            
        except Exception as e:
            print(f"Error initializing blockchain: {{e}}")
            import traceback
            traceback.print_exc()
            blockchain = None
        
        # Start web interface
        webapp_process = Process(
        target=web_main, # Target the main function in run.py
        args=(
            utxos,               # 1. Corresponds to utxos
            mem_pool,            # 2. Corresponds to mem_pool
            webport,             # 3. Corresponds to port (Web UI Port)
            localHostPort,       # 4. Corresponds to localPort (Node's Network Port)
            blockchain,           # 6. Corresponds to a *new* blockchain_proxy parameter (add this to frontend/run.py main signature)
            shared_state_lock   # 5. Corresponds to shared_state_lock
            
        ),
        daemon=True
    )
        webapp_process.start()
        
        
        # Create syncManager with the manager-created blockchain
        sync = syncManager(
            localHost,                  # host
            localHostPort,              # port
            mem_pool,                   # MemoryPool: your shared mem_pool dict
            blockchain,                 # blockchain: your custom Blockchain proxy
            localHostPort,              # localHostPort (again)
            newBlockAvailable,          # newBlockAvailable
            secondaryChain,             # secondaryChain
            my_public_addr=default_account.public_addr,  # my_public_addr
            shared_lock=shared_state_lock
        )
        
        # Start server process
        startServer = Process(target=sync.spinUpServer)
        startServer.start()
        print(f"Server started on port {{localHostPort}}")
        time.sleep(2)  # Give it a moment to start

        logging.info(f"[Startup] Node {{NODE_ID}} initiating sync with peers...")
        try:
            # Call startSync via the proxy, without arguments to trigger download
            blockchain.startSync()
            logging.info(f"[Startup] Node {{NODE_ID}} initial sync process finished.")
            # Note: startSync itself might block or run in background threads depending on implementation
        except Exception as e_sync:
            logging.error(f"[Startup] Node {{NODE_ID}} initial sync failed: {{e_sync}}", exc_info=True)



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

        required_height = 10

        # Wait for the blockchain to reach the required height
        while True:
            try:
                current_height = blockchain.get_height()
                print(f"Current blockchain height: {{current_height}}")
                if current_height >= required_height:
                    print(f"Blockchain has reached the required height of {{required_height}}")
                    break
            except Exception as e:
                print(f"Error fetching blockchain height: {{e}}")
            time.sleep(5)

        if "{self.sim_volume}" != "none" and "{self.sim_volume}":
            print(f"[Sim] Starting transaction simulation: volume='{self.sim_volume}', interval={self.sim_interval}, tx_types='{self.sim_tx_types}'")
            simulate_random_transactions(
                volume="{self.sim_volume}",
                interval={self.sim_interval},
                tx_types="{self.sim_tx_types}",
                num_nodes={self.num_nodes}
            )
        else:
            print("[Sim] Transaction simulation is disabled for this node.")
        # Node idles, waiting for instructions
        try:
            while True:
                time.sleep(10)
                print(f"Node {{NODE_ID}} active on port {{localHostPort}}, web: {{webport}}")
                
        except KeyboardInterrupt:
            webapp_process.terminate()
            startServer.terminate()
"""
        with open(script_path, 'w') as f:
            f.write(script_content)
    

    def start_network(self):
        """Start all nodes and the validator"""
        print("Starting blockchain network...")
        
        try:
            # First make sure node directories are set up
            self.setup_node_directories()
            
            # Import database classes directly
            sys.path.insert(0, os.path.join(PROJECT_ROOT, 'code_node2'))
            from code_node2.Blockchain.Backend.core.database.db import NodeDB, BlockchainDB, AccountDB
            from code_node2.Blockchain.Backend.core.pos_blockchain import Blockchain

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
            # Check if all nodes are running

            running_nodes = [p for p in self.nodes if p.poll() is None]
            if len(running_nodes) != len(self.nodes):
                print(f"WARNING: Only {len(running_nodes)}/{len(self.nodes)} nodes are running")
            
            # Start validator node
            self.start_validator_node()
            
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
        
        # Collect logs before stopping
        try:
            self.collect_logs()
        except Exception as e:
            print(f"Error collecting logs: {e}")
        
        # Stop validator
        if self.validator_process:
            self.validator_process.terminate()
            print("Validator node stopped")
        
        # Stop all nodes
        for i, node in enumerate(self.nodes):
            node.terminate()
            print(f"Node {i} stopped")
        
        print("Network shutdown complete")

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
