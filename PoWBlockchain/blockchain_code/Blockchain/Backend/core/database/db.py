import sqlite3
import json
import os
import logging
import re

# --- Configuration ---
# Assuming this script is in blockchain_code/Blockchain/Backend/core/database/
# Adjust if necessary to find the project root reliably
try:
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
except NameError:
    PROJECT_ROOT = os.path.abspath('.') # Fallback if __file__ is not defined

# Configure logging (consider moving to a central logging setup)
log_file = os.path.join(PROJECT_ROOT, 'database.log')
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)
logger = logging.getLogger(__name__)
print(f"DB Module: PROJECT_ROOT determined as: {PROJECT_ROOT}")
print(f"DB Module: Logging to: {log_file}")


# --- Helper Functions ---
def get_node_specific_path(filename, node_id=None):
    """Determines the absolute path for a node's database file."""
    if node_id is None:
        # Try to detect from CWD if running directly within a node_X folder
        cwd = os.getcwd()
        match = re.search(r'node_(\d+)', cwd)
        if match:
            node_id = int(match.group(1))
            # logger.info(f"Detected node_id {node_id} from CWD: {cwd}")
        else:
            # Default or error if node_id is crucial and not found/provided
            logger.warning(f"Node ID not provided and couldn't detect from CWD: {cwd}. Using default path.")
            # Use a non-node-specific path or raise error depending on requirements
            return os.path.join(PROJECT_ROOT, "data", filename) # Example default

    # Construct node-specific path
    node_data_dir = os.path.join(PROJECT_ROOT, "network_data", f"node_{node_id}", "data")
    return os.path.join(node_data_dir, filename)

def _make_serializable(obj):
    """Recursively converts bytes to hex strings for JSON."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(i) for i in obj]
    if isinstance(obj, bytes):
        return obj.hex()
    # Add handling for custom objects if needed
    # if hasattr(obj, 'to_dict'):
    #     return _make_serializable(obj.to_dict())
    return obj

# --- Base Class ---
class BaseDB:
    def __init__(self, filename, table_name, table_schema, node_id=None, explicit_path=None):
        """
        Initializes the database connection.

        Args:
            filename (str): The base name of the database file (e.g., "blockchain.db").
            table_name (str): The name of the primary table.
            table_schema (str): The SQL command to create the primary table.
            node_id (int, optional): The ID of the node for node-specific paths.
            explicit_path (str, optional): If provided, overrides node-specific path logic.
        """
        self.table_name = table_name
        self.node_id = node_id

        if explicit_path:
            self.filepath = os.path.abspath(explicit_path)
            # logger.info(f"[{type(self).__name__} {self.node_id}] Using explicit path: {self.filepath}")
        else:
            self.filepath = get_node_specific_path(filename, self.node_id)
            # logger.info(f"[{type(self).__name__} {self.node_id}] Resolved node-specific path: {self.filepath}")

        self.conn = None
        self.cursor = None

        try:
            self._ensure_dir()
            self.connect()
            self._create_table(table_schema) # Pass schema directly
        except Exception as e:
            logger.error(f"[{type(self).__name__} {self.node_id}] FAILED initialization for {self.filepath}: {e}", exc_info=True)
            # Depending on severity, you might want to raise e here

    def _ensure_dir(self):
        """Ensures the directory for the database file exists."""
        db_dir = os.path.dirname(self.filepath)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir)
                # logger.info(f"[{type(self).__name__} {self.node_id}] Created directory: {db_dir}")
            except OSError as e:
                logger.error(f"[{type(self).__name__} {self.node_id}] Error creating directory {db_dir}: {e}", exc_info=True)
                raise # Re-raise directory creation error

    def connect(self):
        """Establishes or reuses the database connection."""
        if self.conn is None:
            try:
                logger.debug(f"[{type(self).__name__} {self.node_id}] Attempting to connect to: {self.filepath}")
                # Use check_same_thread=False if accessed from multiple threads (common in web apps/multiprocessing)
                self.conn = sqlite3.connect(self.filepath, timeout=10, check_same_thread=False)
                self.cursor = self.conn.cursor()
                # Optional: WAL mode can improve concurrency but adds extra files
                # self.cursor.execute("PRAGMA journal_mode=WAL;")
                # logger.info(f"[{type(self).__name__} {self.node_id}] Successfully connected to {self.filepath}")
            except sqlite3.Error as e:
                logger.error(f"[{type(self).__name__} {self.node_id}] SQLite error connecting to {self.filepath}: {e}", exc_info=True)
                self.conn = None # Ensure conn is None on failure
                self.cursor = None
                raise # Re-raise connection error
            except Exception as e:
                logger.error(f"[{type(self).__name__} {self.node_id}] General error connecting to {self.filepath}: {e}", exc_info=True)
                self.conn = None
                self.cursor = None
                raise

    def _create_table(self, table_schema):
        """Creates the primary table if it doesn't exist."""
        if not self.conn or not self.cursor:
            logger.error(f"[{type(self).__name__} {self.node_id}] Cannot create table '{self.table_name}', connection not established.")
            return
        try:
            self.cursor.execute(table_schema)
            self.conn.commit()
            # logger.info(f"[{type(self).__name__} {self.node_id}] Table '{self.table_name}' ensured in {self.filepath}")
        except sqlite3.Error as e:
            logger.error(f"[{type(self).__name__} {self.node_id}] Error creating table '{self.table_name}': {e}", exc_info=True)
            raise # Re-raise table creation error

    def close(self):
        """Closes the database connection."""
        if self.conn:
            try:
                self.conn.close()
                # logger.info(f"[{type(self).__name__} {self.node_id}] Database connection closed for {self.filepath}")
            except Exception as e:
                logger.error(f"[{type(self).__name__} {self.node_id}] Error closing connection for {self.filepath}: {e}", exc_info=True)
            finally:
                self.conn = None
                self.cursor = None

    def __del__(self):
        """Ensures connection is closed when object is deleted."""
        self.close()

    # --- Methods for Pickling (Multiprocessing) ---
    def __getstate__(self):
        """Return state for pickling, excluding non-picklable connection."""
        state = self.__dict__.copy()
        state['conn'] = None
        state['cursor'] = None
        logger.debug(f"[{type(self).__name__} {self.node_id}] Getting state for pickling (filepath: {self.filepath})")
        return state

    def __setstate__(self, state):
        """Restore state from pickle and re-establish connection."""
        self.__dict__.update(state)
        logger.debug(f"[{type(self).__name__} {self.node_id}] Restoring state from pickle (filepath: {self.filepath}), reconnecting...")
        # Connection will be re-established on first use by connect()
        self.conn = None
        self.cursor = None
        # Optionally connect immediately: self.connect()


# --- Blockchain Database ---
class BlockchainDB(BaseDB):
    def __init__(self, db_path=None, node_id=None):
        schema = """
            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, -- Represents Height + 1 implicitly
                data TEXT NOT NULL
            )
        """
        # Pass explicit_path if db_path is provided
        super().__init__(filename="blockchain.db",
                         table_name="blocks",
                         table_schema=schema,
                         node_id=node_id,
                         explicit_path=db_path)

        # --- Create the Transaction Index Table ---
        try:
            self.connect() # Ensure connection
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS tx_index (
                       tx_hash TEXT PRIMARY KEY,
                       block_height INTEGER NOT NULL
                   )"""
            )
            self.cursor.execute(
                """CREATE INDEX IF NOT EXISTS idx_tx_block_height ON tx_index (block_height)"""
            )
            self.conn.commit()
            # logger.info(f"[BlockchainDB {self.node_id}] Transaction index table 'tx_index' ensured.")
        except Exception as e:
            logger.error(f"[BlockchainDB {self.node_id}] Error creating tx_index table: {e}", exc_info=True)
            # Decide if this is fatal, maybe raise e

    def write(self, block_dict):
        """Writes a block dict to the DB and updates the tx_index."""
        self.connect()
        block_height = block_dict.get('Height')
        if block_height is None:
             logger.error(f"[BlockchainDB {self.node_id}] Block dictionary missing 'Height'. Cannot write.")
             raise ValueError("Block dictionary missing 'Height'")

        try:
             # --- Log block hash before serialization ---
            log_block_hash = block_dict.get('BlockHeader', {}).get('blockHash', 'MISSING HASH')
            logger.info(f"[BlockchainDB {self.node_id}] Writing Block {block_height}. Hash in dict: {log_block_hash}")
            # --- End log ---
            serial = json.dumps(_make_serializable(block_dict))
            # --- Write Block ---
            self.cursor.execute("INSERT INTO blocks (data) VALUES (?)", (serial,))

            # --- Update Transaction Index ---
            tx_index_entries = []
            for tx in block_dict.get('Txs', []):
                tx_id = tx.get('TxId')
                if tx_id:
                    tx_index_entries.append((tx_id, block_height))

            if tx_index_entries:
                self.cursor.executemany(
                    "INSERT OR IGNORE INTO tx_index (tx_hash, block_height) VALUES (?, ?)",
                    tx_index_entries
                )

            self.conn.commit()
            # logger.info(f"[BlockchainDB {self.node_id}] Block {block_height} written successfully.")
        except Exception as e:
            logger.error(f"[BlockchainDB {self.node_id}] Error writing block {block_height}: {e}", exc_info=True)
            try:
                self.conn.rollback()
            except Exception as rb_e:
                 logger.error(f"[BlockchainDB {self.node_id}] Error during rollback after write failure: {rb_e}")
            raise

    def lastBlock(self):
        """Retrieve the last block dictionary."""
        self.connect()
        try:
            self.cursor.execute('SELECT data FROM blocks ORDER BY id DESC LIMIT 1')
            row = self.cursor.fetchone()
            if not row:
                # logger.info(f"[BlockchainDB {self.node_id}] No blocks found in DB.")
                return None
            return json.loads(row[0]) # Assumes data is valid JSON
        except Exception as e:
            logger.error(f"[BlockchainDB {self.node_id}] Error reading last block: {e}", exc_info=True)
            return None

    def read_all_blocks(self):
        """Reads all blocks as a list of dictionaries."""
        self.connect()
        blocks = []
        try:
            self.cursor.execute("SELECT data FROM blocks ORDER BY id ASC")
            for r in self.cursor.fetchall():
                try:
                    blocks.append(json.loads(r[0]))
                except json.JSONDecodeError as e:
                    logger.error(f"[BlockchainDB {self.node_id}] Error decoding JSON for a block during read_all: {e} - Data: {r[0][:100]}...")
                    # Decide whether to skip or raise
            return blocks
        except Exception as e:
            logger.error(f"[BlockchainDB {self.node_id}] Error reading all blocks: {e}", exc_info=True)
            return [] # Return empty list on error

    def get_height(self):
        """Returns the height of the last block in the chain (number of blocks - 1)."""
        conn = None # Use a local connection variable for safety in this method
        try:
            # Use the existing connect method logic, but manage connection locally
            if self.conn is None:
                 self.connect() # Ensure connection exists if not already connected

            # Use the class's cursor if available
            if self.cursor is None:
                 logger.error("Database cursor not available in get_height.")
                 return -2 # Indicate an internal error

            # Assuming your blocks table is named 'blocks'
            self.cursor.execute("SELECT COUNT(*) FROM blocks")
            result = self.cursor.fetchone()
            count = result[0] if result else 0
            # Height is typically 0-indexed (genesis block is height 0)
            height = count - 1
            # logger.debug(f"Calculated height: {height} (Count: {count})")
            return height
        except sqlite3.Error as e:
            logger.error(f"Error getting blockchain height: {e}")
            # Return -1 to indicate a DB query error
            return -1
        # Note: We don't close the connection here as it's managed by the class instance
    # --- END OF ADDED METHOD ---

    def read_block(self, height):
        """Reads a single block dictionary by its height."""
        target_id = height + 1 # Assuming id = Height + 1
        self.connect()
        try:
            self.cursor.execute("SELECT data FROM blocks WHERE id = ?", (target_id,))
            row = self.cursor.fetchone()
            if row:
                return json.loads(row[0])
            else:
                logger.debug(f"[BlockchainDB {self.node_id}] Block height {height} (id {target_id}) not found.")
                return None
        except Exception as e:
            logger.error(f"[BlockchainDB {self.node_id}] Error reading block height {height}: {e}", exc_info=True)
            return None

    def read_block_by_hash(self, block_hash_hex):
        """Reads a single block dictionary by its hash (SLOW SCAN)."""
        self.connect()
        logger.debug(f"[BlockchainDB {self.node_id}] Searching for block hash {block_hash_hex} (full scan)...")
        try:
            self.cursor.execute("SELECT data FROM blocks ORDER BY id DESC") # Scan recent first
            for r in self.cursor.fetchall():
                try:
                    obj = json.loads(r[0])
                    # Basic check, assumes BlockHeader exists
                    header = obj.get('BlockHeader', {})
                    current_hash = header.get('blockHash')
                    if current_hash == block_hash_hex:
                        logger.debug(f"[BlockchainDB {self.node_id}] Found block hash {block_hash_hex}.")
                        return obj
                except Exception: # Catch JSON errors or missing keys
                    continue # Skip malformed blocks during scan
            logger.debug(f"[BlockchainDB {self.node_id}] Block hash {block_hash_hex} not found.")
            return None
        except Exception as e:
            logger.error(f"[BlockchainDB {self.node_id}] Error reading block by hash {block_hash_hex}: {e}", exc_info=True)
            return None

    def delete_blocks_from_height(self, height):
        """Deletes blocks >= height and associated tx_index entries."""
        min_id_to_delete = height + 1
        min_height_to_delete = height
        self.connect()
        try:
            # Delete from tx_index first
            self.cursor.execute("DELETE FROM tx_index WHERE block_height >= ?", (min_height_to_delete,))
            deleted_index_count = self.cursor.rowcount
            # Delete from blocks
            self.cursor.execute("DELETE FROM blocks WHERE id >= ?", (min_id_to_delete,))
            deleted_block_count = self.cursor.rowcount
            self.conn.commit()
            # logger.info(f"[BlockchainDB {self.node_id}] Deleted {deleted_block_count} block(s) and {deleted_index_count} tx_index entries from height {height}.")
            return deleted_block_count
        except Exception as e:
            logger.error(f"[BlockchainDB {self.node_id}] Error deleting blocks from height {height}: {e}", exc_info=True)
            try:
                self.conn.rollback()
            except Exception as rb_e:
                 logger.error(f"[BlockchainDB {self.node_id}] Error during rollback after delete failure: {rb_e}")
            return 0

    def get_tx_block_height(self, tx_hash):
        """Finds the block height for a given transaction hash from the index."""
        self.connect()
        try:
            self.cursor.execute("SELECT block_height FROM tx_index WHERE tx_hash = ?", (tx_hash,))
            row = self.cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"[BlockchainDB {self.node_id}] Error querying tx_index for hash {tx_hash}: {e}", exc_info=True)
            return None

    def update(self, blockchain_data):
        """Replaces the entire blockchain and rebuilds the index (use with caution)."""
        self.connect()
        try:
            logger.warning(f"[BlockchainDB {self.node_id}] Replacing entire blockchain...")
            # Clear existing data
            self.cursor.execute(f"DELETE FROM {self.table_name}")
            self.cursor.execute("DELETE FROM tx_index") # Clear index too
            self.conn.commit()

            # Write new data and rebuild index
            count = 0
            for entry in blockchain_data:
                # Handle potential nesting if entry is list [block_dict]
                blk_dict = entry[0] if isinstance(entry, list) and len(entry) == 1 else entry
                if isinstance(blk_dict, dict):
                    self.write(blk_dict) # Use the write method to handle index update
                    count += 1
                else:
                    logger.warning(f"[DB Update {self.node_id}] Skipping invalid entry: type={type(blk_dict)}")

            # Commit might be redundant if write commits, but good for safety
            self.conn.commit()
            # logger.info(f"[BlockchainDB {self.node_id}] Wrote {count} blocks and rebuilt tx_index.")
            return True
        except Exception as e:
            logger.error(f"[BlockchainDB {self.node_id}] ERROR updating blockchain: {e}", exc_info=True)
            try:
                self.conn.rollback()
            except Exception as rb_e:
                 logger.error(f"[BlockchainDB {self.node_id}] Error during rollback after update failure: {rb_e}")
            return False


# --- Account Database ---
class AccountDB(BaseDB):
    def __init__(self, db_path=None, node_id=None):
        schema = """
            CREATE TABLE IF NOT EXISTS account (
                public_addr TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """
        super().__init__(filename="account.db",
                         table_name="account",
                         table_schema=schema,
                         node_id=node_id,
                         explicit_path=db_path)

    def read(self):
        """Reads all accounts as a list of dictionaries."""
        self.connect()
        accounts = []
        try:
            self.cursor.execute(f"SELECT value FROM {self.table_name}")
            for r in self.cursor.fetchall():
                try:
                    accounts.append(json.loads(r[0]))
                except json.JSONDecodeError as e:
                    logger.error(f"[AccountDB {self.node_id}] Error decoding JSON for an account: {e} - Data: {r[0][:100]}...")
            return accounts
        except Exception as e:
            logger.error(f"[AccountDB {self.node_id}] Error reading all accounts: {e}", exc_info=True)
            return []

    def write(self, addr, data):
        """Writes or updates a single account."""
        self.connect()
        try:
            j_data = json.dumps(_make_serializable(data))
            self.cursor.execute(f"""
                INSERT INTO {self.table_name} (public_addr, value) VALUES (?, ?)
                ON CONFLICT(public_addr) DO UPDATE SET value=excluded.value
            """, (addr, j_data))
            self.conn.commit()
            # logger.info(f"[AccountDB {self.node_id}] Account {addr} written/updated.")
        except Exception as e:
            logger.error(f"[AccountDB {self.node_id}] Error writing account {addr}: {e}", exc_info=True)
            try:
                self.conn.rollback()
            except Exception as rb_e:
                 logger.error(f"[AccountDB {self.node_id}] Error during rollback after write failure: {rb_e}")
            raise

    def read_account(self, addr):
        """Reads a single account dictionary by address."""
        self.connect()
        try:
            self.cursor.execute(f"SELECT value FROM {self.table_name} WHERE public_addr=?", (addr,))
            row = self.cursor.fetchone()
            if row:
                return json.loads(row[0])
            else:
                logger.debug(f"[AccountDB {self.node_id}] Account {addr} not found.")
                return None
        except Exception as e:
            logger.error(f"[AccountDB {self.node_id}] Error reading account {addr}: {e}", exc_info=True)
            return None


# --- Node Database ---
class NodeDB(BaseDB):
    def __init__(self, db_path=None, node_id=None):
        schema = """
            CREATE TABLE IF NOT EXISTS nodes (
                port INTEGER PRIMARY KEY
            )
        """
        # NodeDB often uses a shared path, but allow override
        # If explicit_path is None, it will use the node_id logic if available,
        # otherwise a default path. Adjust filename/default path if needed.
        super().__init__(filename="node.db",
                         table_name="nodes",
                         table_schema=schema,
                         node_id=node_id,
                         explicit_path=db_path)

    def write(self, port):
        """Adds a node port if it doesn't exist."""
        self.connect()
        try:
            self.cursor.execute(f"INSERT OR IGNORE INTO {self.table_name} (port) VALUES (?)", (port,))
            self.conn.commit()
            # logger.info(f"[NodeDB {self.node_id}] Port {port} added/ignored.")
        except Exception as e:
            logger.error(f"[NodeDB {self.node_id}] Error writing port {port}: {e}", exc_info=True)
            try:
                self.conn.rollback()
            except Exception as rb_e:
                 logger.error(f"[NodeDB {self.node_id}] Error during rollback after write failure: {rb_e}")
            raise

    def read_nodes(self):
        """Reads all known node ports as a list of integers."""
        self.connect()
        try:
            self.cursor.execute(f"SELECT port FROM {self.table_name}")
            # Ensure ports are integers
            ports = [int(r[0]) for r in self.cursor.fetchall() if r[0] is not None]
            return ports
        except Exception as e:
            logger.error(f"[NodeDB {self.node_id}] Error reading nodes: {e}", exc_info=True)
            return []
'''

**Key Changes & Simplifications:**

1.  **`BaseDB` Handles Paths:**
    *   `__init__` now takes `filename`, `table_name`, `table_schema`, optional `node_id`, and optional `explicit_path`.
    *   It uses `get_node_specific_path` helper if `explicit_path` is not given.
    *   It ensures the directory exists (`_ensure_dir`).
    *   It connects (`connect`) and creates the table (`_create_table`).
2.  **Subclasses Simplified:**
    *   `BlockchainDB`, `AccountDB`, `NodeDB` now primarily just call `super().__init__` with their specific `filename`, `table_name`, `table_schema`, and pass along `node_id` and `db_path` (as `explicit_path`).
    *   They don't need to manage `self.filepath` or connection details directly in `__init__` anymore (BaseDB does it).
3.  **Path Resolution:** `get_node_specific_path` is responsible for figuring out the correct `network_data/node_X/data/filename` path.
4.  **Connection Management:** `connect()` is called within `BaseDB.__init__` and also at the start of most read/write methods to ensure the connection is active (especially important after pickling/unpickling in multiprocessing).
5.  **Error Handling:** Basic `try...except` blocks are kept, logging errors. Critical errors (connection, table creation) are re-raised.
6.  **Pickling:** `__getstate__` and `__setstate__` remain in `BaseDB` to handle multiprocessing (clearing the connection before pickling).
7.  **Serialization:** `_make_serializable` helper moved outside classes for general use.
8.  **Cleaned Up:** Removed redundant code, commented-out sections, and excessive debug prints. Added INFO level logging for key operations.

**How to Use:**

*   When creating `BlockchainDB`, `AccountDB`, or `NodeDB` in your node-specific scripts (like `start_node.py`), pass the `node_id` and the correct `db_path` (absolute path to the specific file, e.g., `/path/to/network_data/node_0/data/blockchain.db`).
    ```python
    # In start_node.py for node 0
    blockchain_db_path = "/path/to/network_data/node_0/data/blockchain.db"
    node_id = 0
    blockchain_db = BlockchainDB(db_path=blockchain_db_path, node_id=node_id)
    ```
*   `BaseDB` will use the `db_path` you provide directly.

This structure should be much cleaner and easier to maintain while correctly handling node-specific database files. Remember to restart your nodes after applying these changes.# filepath: /Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoWBlockchain/blockchain_code/Blockchain/Backend/core/database/db.py
'''