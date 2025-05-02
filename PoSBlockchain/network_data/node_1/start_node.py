
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
logging.info(f"[PID {os.getpid()}] start_node.py script started. Logging configured.")



ZERO_HASH = "0" * 64


# Add paths
sys.path.append("/dcs/project/algoblock/MainCode/PoSBlockchain")
sys.path.append("/dcs/project/algoblock/MainCode/PoSBlockchain/network_data/node_1")

# Store node ID as a variable inside this script
NODE_ID = 1
NUM_NODES = 3

# --- DEFINE ABSOLUTE PATHS FIRST ---
# Use the absolute data_dir passed from the launcher
abs_data_dir = "/dcs/project/algoblock/MainCode/PoSBlockchain/network_data/node_1/data"
# Ensure the directory exists (using the absolute path)
if not os.path.exists(abs_data_dir):
    os.makedirs(abs_data_dir)

nested = os.path.join(abs_data_dir, "data")
if not os.path.exists(nested):
    try:
        os.symlink(abs_data_dir, nested)
        logging.info(f"[PID {os.getpid()}] symlinked {nested} → {abs_data_dir}")
    except FileExistsError:
        pass

# Define absolute paths for databases
blockchain_db_path = os.path.join(abs_data_dir, "blockchain.db")
node_db_path = os.path.join(abs_data_dir, "node.db")
account_db_path = os.path.join(abs_data_dir, "account.db")

# Create data directory if needed
data_dir = os.path.join("/dcs/project/algoblock/MainCode/PoSBlockchain/network_data/node_1", "data")
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# Import and patch database classes BEFORE importing the Blockchain class
sys.path.insert(0, "/dcs/project/algoblock/MainCode/PoSBlockchain/code_node2")
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
                logging.info(f"[PID {os.getpid()}] NodeDB set WAL mode and busy_timeout for {self.filepath}")
            except Exception as e_pragma:
                logging.warning(f"[PID {os.getpid()}] NodeDB FAILED to set WAL/busy_timeout for {self.filepath}: {e_pragma}")
        # --- END ADD ---
    except Exception as e_connect:
        logging.error(f"[PID {os.getpid()}] NodeDB FAILED to connect to: {self.filepath} - Error: {e_connect}")
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
    logging.info(f"[PID {os.getpid()}] BlockchainDB attempting to connect to: {self.filepath}")
    try:
        self.connect()
        logging.info(f"[PID {os.getpid()}] BlockchainDB connected successfully to: {self.filepath}")
        # --- ADD WAL and BUSY TIMEOUT ---
        if self.conn:
            try:
                self.conn.execute("PRAGMA journal_mode=WAL;")
                self.conn.execute("PRAGMA busy_timeout = 5000;") # Wait 5 seconds if locked
                logging.info(f"[PID {os.getpid()}] BlockchainDB set WAL mode and busy_timeout for {self.filepath}")
            except Exception as e_pragma:
                logging.warning(f"[PID {os.getpid()}] BlockchainDB FAILED to set WAL/busy_timeout for {self.filepath}: {e_pragma}")
        # --- END ADD ---
    except Exception as e_connect:
        logging.error(f"[PID {os.getpid()}] BlockchainDB FAILED to connect to: {self.filepath} - Error: {e_connect}")
        raise
    print(f"[DEBUG] BlockchainDB will use path: {self.filepath}")
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
                logging.info(f"[PID {os.getpid()}] AccountDB set WAL mode and busy_timeout for {self.filepath}")
            except Exception as e_pragma:
                logging.warning(f"[PID {os.getpid()}] AccountDB FAILED to set WAL/busy_timeout for {self.filepath}: {e_pragma}")
        # --- END ADD ---
    except Exception as e_connect:
        logging.error(f"[PID {os.getpid()}] AccountDB FAILED to connect to: {self.filepath} - Error: {e_connect}")
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
    print(f"  - Connected to node database: {node_db_path}")
    conn.close()
    db_files_to_chmod.append(node_db_path)
    
    conn = sqlite3.connect(blockchain_db_path)
    print(f"  - Connected to blockchain database: {blockchain_db_path}")
    conn.close()
    db_files_to_chmod.append(blockchain_db_path)
    
    conn = sqlite3.connect(account_db_path)
    print(f"  - Connected to account database: {account_db_path}")
    conn.close()
    db_files_to_chmod.append(account_db_path)
except Exception as e:
    print(f"Error testing database connections: {e}")
    sys.exit(1)

# Set permissions for database files
print(f"Setting permissions for database files...")
for db_file in db_files_to_chmod:
    try:
        # Set permissions: Owner rw, Group rw, Others ---
        os.chmod(db_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)
        print(f"  - Set permissions for {db_file} to 660")
    except OSError as e:
        print(f"Warning: Could not set permissions for {db_file}: {e}")



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
    account_data = {
        'privateKey': selected_address['privateKey'],
        'public_addr': selected_address['public_addr'],
        'staked': 0 * 100000000,
        'public_key': selected_address['public_key']
    }

    print("Account details: " + json.dumps(selected_address))

    # --- Insert ALL accounts into account.db ---
    try:
        import sys
        sys.path.append("/dcs/project/algoblock/MainCode/PoSBlockchain")
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
            int(3 / target_network_tps)
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
        #     utxos = {}
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
                # print(f"[Sim Debug 766099/{threading.get_ident()}] Creating AccountDB instance...")
                # db_instance = AccountDB()
                # print(f"[Sim Debug 766099/{threading.get_ident()}] Instance type: {type(db_instance)}")
                # if hasattr(db_instance, 'table_name'):
                #     print(f"[Sim Debug 766099/{threading.get_ident()}] Instance HAS table_name: '{db_instance.table_name}'")
                # else:
                #     print(f"[Sim Debug 766099/{threading.get_ident()}] Instance LACKS table_name attribute!")
                # # --- End Debugging ---

                # if acct is None:
                #     print(f"[Sim] Account {my_address} not found.")
                #     time.sleep(actual_interval)
                #     continue
                
                # print("[DEBUG][SIM] UTXO set for account", acct.public_addr)
                # for (txid, idx), tx_out in utxos.items():
                #     print(f"  {txid}:{idx} amount={tx_out.amount} cmds={tx_out.script_publickey.cmds}")

                # spendable, staked = acct.get_balance(utxos)
                # print(f"[DEBUG][SIM] Account {acct.public_addr} spendable={spendable} staked={staked}")
                # for (txid, idx), tx_out in utxos.items():
                #     print(f"[DEBUG][SIM] UTXO {txid}:{idx} amount={tx_out.amount} cmds={tx_out.script_publickey.cmds}")
                # if spendable <= 0 and tx_types != "unstake":
                #     print(f"[Sim] My address {my_address} has no spendable funds.")
                #     time.sleep(actual_interval)
                #     continue
                    
                # if staked <= 0 and tx_types == "unstake":
                #     print(f"[Sim] My address {my_address} has no staked funds to unstake.")
                #     time.sleep(actual_interval)
                #     continue
                    
                tx_type = random.choices(
                    ["transfer", "stake"], 
                    weights=tx_weights, 
                    k=1
                )[0]


                
                # max_amount = min(spendable, 35 * 100000000) if tx_type != "unstake" else min(staked, 35 * 100000000)
                # if max_amount < 1:
                #     print(f"[Sim] My address {my_address} has insufficient funds for {tx_type}.")
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
                    params = {
                        "fromAddress": my_address,
                        "toAddress": receiver['public_addr'],
                        "Amount": amount_tdc
                    }
                    endpoint = f"http://localhost:{target_web_port}/wallet"
                    print(f"[Sim] Attempting to Send {amount_tdc} TDC from {my_address} to {receiver['public_addr']} via node on web port {target_web_port}")
                    logging.info(f"[Sim] Attempting to Send  {amount_tdc} TDC from {my_address} to {receiver['public_addr']} via node on web port {target_web_port}")

                elif tx_type == "stake":
                    params = {
                        "action": "stake",
                        "fromAddress": my_address,
                        "amount": amount_tdc,
                        "lock_duration": random.randint(60*60, 60*60*24*30)
                    }
                    endpoint = f"http://localhost:{target_web_port}/stake"
                    print(f"[Sim] Attempting to stake {amount_tdc} TDC from {my_address} via node on web port {target_web_port}")
                    logging.info(f"[Sim] Attempting to stake {amount_tdc} TDC from {my_address} via node on web port {target_web_port}")
                
                # elif tx_type == "unstake":
                #     params = {
                #         "action": "unstake",
                #         "fromAddress": my_address,
                #         "amount_unstake": amount_tdc
                #     }
                #     endpoint = f"http://localhost:{target_web_port}/stake"
                #     print(f"[Sim] Attempting to unstake {amount_tdc} TDC from {my_address} via node on web port {target_web_port}")
                #     logging.info(f"[Sim] Attempting to unstake  {amount_tdc} TDC from {my_address} via node on web port {target_web_port}")
                
                # Then send the request
                try:
                    res = requests.post(endpoint, json=params, timeout=10)
                    print(f"[Sim] {tx_type.capitalize()} submitted: {res.status_code} {res.text[:100]}")
                    logging.info(f"[Sim] {tx_type.capitalize()} submitted: {res.status_code} {res.text[:100]}")
                except Exception as e:
                    print(f"[Sim] Error submitting {tx_type}: {e}")
                

            except AttributeError as ae:
                 print(f"[Sim ATTRIBUTE ERROR 766099/{threading.get_ident()}] {ae}")
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
            
            print(f"Setting blockchain public address to: {blockchain.my_public_addr}")
            blockchain.setup_node()
            print("Blockchain initialized successfully through BlockchainManager")
            
        except Exception as e:
            print(f"Error initializing blockchain: {e}")
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
        print(f"Server started on port {localHostPort}")
        time.sleep(2)  # Give it a moment to start

        logging.info(f"[Startup] Node {NODE_ID} initiating sync with peers...")
        try:
            # Call startSync via the proxy, without arguments to trigger download
            blockchain.startSync()
            logging.info(f"[Startup] Node {NODE_ID} initial sync process finished.")
            # Note: startSync itself might block or run in background threads depending on implementation
        except Exception as e_sync:
            logging.error(f"[Startup] Node {NODE_ID} initial sync failed: {e_sync}", exc_info=True)



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

        required_height = 10

        # Wait for the blockchain to reach the required height
        while True:
            try:
                current_height = blockchain.get_height()
                print(f"Current blockchain height: {current_height}")
                if current_height >= required_height:
                    print(f"Blockchain has reached the required height of {required_height}")
                    break
            except Exception as e:
                print(f"Error fetching blockchain height: {e}")
            time.sleep(5)

        if "none" != "none" and "none":
            print(f"[Sim] Starting transaction simulation: volume='none', interval=30, tx_types='all'")
            simulate_random_transactions(
                volume="none",
                interval=30,
                tx_types="all",
                num_nodes=3
            )
        else:
            print("[Sim] Transaction simulation is disabled for this node.")
        # Node idles, waiting for instructions
        try:
            while True:
                time.sleep(10)
                print(f"Node {NODE_ID} active on port {localHostPort}, web: {webport}")
                
        except KeyboardInterrupt:
            webapp_process.terminate()
            startServer.terminate()
