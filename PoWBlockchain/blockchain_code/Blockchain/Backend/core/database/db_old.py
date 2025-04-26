# import re
# import sqlite3
# import json
# import os
# import logging

# # Configure logging
# logging.basicConfig(
#     filename='database.log',
#     level=logging.INFO,
#     format='%(asctime)s %(levelname)s:%(message)s'
# )
# logger = logging.getLogger(__name__)


# def resolve_db_path(filename, node_id=None):
#     """Try to resolve the correct absolute path for a DB file."""
#     cwd = os.getcwd()
#     project_root = None
    
#     # Try to identify project root from current path
#     match = re.search(r'(.*?PoWBlockchain)', cwd)
#     if match:
#         project_root = match.group(1)
    
#     db_paths = []
#     if node_id is not None and project_root:
#         db_paths.append(os.path.join(
#             project_root, "network_data",
#             f"node_{node_id}/data/{filename}"
#         ))

#     # Add the default paths 
#     db_paths.extend([
#         os.path.join("data", filename),
#         filename,
#         os.path.join(cwd, "data", filename),
#         os.path.join(cwd, filename)
#     ])
#     for path in db_paths:
#         if os.path.exists(path):
#             return path
#     # If not found, return the preferred path (even if it doesn't exist yet)
#     return db_paths[0] if db_paths else filename

# def _detect_node_id():
#     cwd = os.getcwd()
#     m = re.search(r'node_(\d+)', cwd)
#     return int(m.group(1)) if m else 0

# class BaseDB:
#     def __init__(self, filename, table_name , table_schema, node_id=None):
#         if node_id is None:
#             node_id = _detect_node_id()

#         path = resolve_db_path(filename, node_id=node_id)
#         os.makedirs(os.path.dirname(path), exist_ok=True)

#         self.filepath = path
#         self.table_name = table_name
#         self.table_schema = table_schema
#         self.conn = None
#         self.cursor = None
        
#         self._create_table()
    
#     def connect(self):
#         if self.conn is None:
#             self.conn = sqlite3.connect(self.filepath, timeout=30)
#             self.cursor = self.conn.cursor()
#             self.cursor.execute("PRAGMA journal_mode=WAL;")
#         # if self.conn is None:
#         #     self.conn = sqlite3.connect(self.filepath)
#         #     self.cursor = self.conn.cursor()
        

#     def _create_table(self):
#         self.connect()
#         self.cursor.execute(self.table_schema)
#         self.conn.commit()
#         logger.info(f"Ensured table exists in {self.filepath}")

#     def read(self):
#         self.connect()
#         self.cursor.execute(f'SELECT * FROM {self.table_name}')
#         rows = self.cursor.fetchall()
#         if len(rows) > 0:
#             return [json.loads(row[1]) for row in rows]
#         else:
#             return []
        
#     def update(self, data):
#         self.connect()
#         self.cursor.execute('DELETE FROM blocks')
#         self.conn.commit()
#         for item in data:
#             public_addr = item.get('public_addr')
#             if public_addr is None:
#                 logger.error("Missing 'public_addr' in data item.")
#                 continue
#             self.write(public_addr, item)

#     def write(self, public_addr, data):
#         self.connect()
#         try:
#             self.cursor.execute('''
#                 INSERT INTO accounts (public_addr, data)
#                 VALUES (?, ?)
#                 ON CONFLICT(public_addr) DO UPDATE SET data=excluded.data
#             ''', (public_addr, json.dumps(data)))
#             self.conn.commit()
#             logger.info(f"Account {public_addr} written/updated successfully.")
#         except Exception as e:
#             logger.error(f"Error writing account {public_addr} to DB: {e}")
#             raise

#     def __getstate__(self):
#         # Remove non-picklable objects
#         state = self.__dict__.copy()
#         state['conn'] = None
#         state['cursor'] = None
#         return state

#     def __setstate__(self, state):
#         self.__dict__.update(state)
#         # Reinitialize the connection when unpickled.
#         self.connect()

#     def __del__(self):
#         if self.conn:
#             self.conn.close()



# class BlockchainDB(BaseDB):
#     def __init__(self, db_path=None, node_id=None):
#         if db_path:
#             # allow override if explicitly passed
#             super().__init__(os.path.basename(db_path), "blocks", """
#                 CREATE TABLE IF NOT EXISTS blocks
#                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)
#             """)
#             self.filepath = db_path
#         else:
#             super().__init__("blockchain.db", "blocks", """
#                 CREATE TABLE IF NOT EXISTS blocks
#                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)
#             """)
#         self.table_name = 'blocks'
#         self.filename = db_path if db_path else 'blockchain.db'
#         table_schema = '''
#             CREATE TABLE IF NOT EXISTS blocks (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 data TEXT NOT NULL
#             )
#         '''
#         self.conn = None
#         self.cursor = None
#         # Use resolve_db_path to get the correct path
#         resolved_path = resolve_db_path(self.filename, node_id=node_id)
#         super().__init__(resolved_path, table_schema)
#         self.filepath = resolved_path  # Ensure absolute path is used

#     def connect(self):
#         if self.conn is None:
#             self.conn = sqlite3.connect(self.filepath)
#             self.cursor = self.conn.cursor()

#     def write(self, block):
#         """
#         Insert a block into the blocks table.
#         """
#         self.connect()
#         try:
#             # Ensure all bytes in the block dict are converted to hex strings
#             block_serializable = self.make_serializable(block)
#             data_json = json.dumps(block_serializable)
#             self.cursor.execute('''
#                 INSERT INTO blocks (data)
#                 VALUES (?)
#             ''', (data_json,))
#             self.conn.commit()
#             logger.info(f"Block written successfully.")
#         except Exception as e:
#             logger.error(f"Error writing block to DB: {e}")
#             raise

#     def lastBlock(self):
#         """Retrieve the last block in the blockchain"""
#         self.connect()
#         self.cursor.execute('SELECT data FROM blocks ORDER BY id DESC LIMIT 1')
#         row = self.cursor.fetchone()
#         if row:
#             return json.loads(row[0])
#         else:
#             return None

#     def read_all_blocks(self):
#         """Read all blocks from the blocks table"""
#         self.connect()
#         self.cursor.execute('SELECT data FROM blocks ORDER BY id ASC')
#         rows = self.cursor.fetchall()
#         if rows:
#             # Return the data as a list of dictionaries (blocks)
#             return [json.loads(row[0]) for row in rows]
#         else:
#             return []

#     def make_serializable(self, obj):
        
#         """Recursively convert bytes to hex strings in the object"""
#         if isinstance(obj, dict):
#             return {k: self.make_serializable(v) for k, v in obj.items()}
#         elif isinstance(obj, list):
#             return [self.make_serializable(item) for item in obj]
#         elif isinstance(obj, bytes):
#             return obj.hex()
#         else:
#             return obj
    
#     def __getstate__(self):
#         # Remove non-picklable objects
#         state = self.__dict__.copy()
#         state['conn'] = None
#         state['cursor'] = None
#         return state

#     def __setstate__(self, state):
#         self.__dict__.update(state)
#         # Reinitialize the connection when unpickled.
#         self.connect()
        
# class AccountDB(BaseDB):
#     def __init__(self, db_path=None): # Allow optional db_path override
#         if db_path:
#             super().__init__(os.path.basename(db_path), "account", """
#                 CREATE TABLE IF NOT EXISTS account
#                 (public_addr TEXT PRIMARY KEY, value TEXT NOT NULL)
#             """)
#             self.filepath = db_path
#         else:
#             super().__init__("account.db", "account", """
#                 CREATE TABLE IF NOT EXISTS account
#                 (public_addr TEXT PRIMARY KEY, value TEXT NOT NULL)
#             """)
#         self.table_name = 'account'  # *** SET THE CORRECT TABLE NAME HERE ***
#         self.filename = "account.db"
#         # *** USE THE CORRECT TABLE NAME IN THE SCHEMA ***
#         table_schema = '''
#             CREATE TABLE IF NOT EXISTS account (  
#                 public_addr TEXT PRIMARY KEY,
#                 value TEXT NOT NULL
#             )
#         '''
#         self.conn = None
#         self.cursor = None
#         # Handle explicit db_path if provided, otherwise use default logic
#         effective_filename = db_path if db_path else self.filename
#         # Call BaseDB init AFTER setting table_name and schema
#         # BaseDB needs filename and schema, but uses self.filepath internally
#         # We need to adjust how BaseDB gets the path if overridden
#         super().__init__(effective_filename, table_schema)
#         # Override filepath if db_path was given, as BaseDB defaults to data/ subdir
#         if db_path:
#             self.filepath = db_path # Ensure filepath is the absolute one provided
        
#         print(f"[DEBUG] AccountDB using path: {self.filepath}")


#     def read_account(self, address):
#         """
#         Retrieve a single account dict from DB by its public address.
#         Returns None if not found.
#         """
#         # Connect if needed
#         if not hasattr(self, 'conn') or self.conn is None:
#             if hasattr(self, 'connect'):
#                 self.connect()
#             else:
#                 import sqlite3
#                 self.conn = sqlite3.connect(self.db_path if hasattr(self, 'db_path') else 
#                                         (self.filename if hasattr(self, 'filename') else 'account.db'))
#                 self.cursor = self.conn.cursor()
        
#         # First try the correct table name and column name
#         self.cursor.execute('SELECT value FROM account WHERE public_addr = ?', (address,))
#         row = self.cursor.fetchone()
#         if row:
#             import json
#             return json.loads(row[0])
            
#         # If not found, try legacy table/column names
#         try:
#             self.cursor.execute('SELECT data FROM accounts WHERE public_addr = ?', (address,))
#             row = self.cursor.fetchone()
#             if row:
#                 import json
#                 return json.loads(row[0])
#         except:
#             pass
            
#         return None

#     def write_account(self, account_data):
#         """
#         Write or update a single account dict in the DB.
#         """
#         public_addr = account_data.get('public_addr')
#         if public_addr is None:
#             raise ValueError("Account data must include 'public_addr'.")
        
#         if not hasattr(self, 'conn') or self.conn is None:
#             if hasattr(self, 'connect'):
#                 self.connect()
#             else:
#                 import sqlite3
#                 self.conn = sqlite3.connect(self.db_path if hasattr(self, 'db_path') else 
#                                         (self.filename if hasattr(self, 'filename') else 'account.db'))
#                 self.cursor = self.conn.cursor()
        
#         import json
#         data_json = json.dumps(account_data)
        
#         # Create the account table if it doesn't exist
#         self.cursor.execute('''
#             CREATE TABLE IF NOT EXISTS account
#             (public_addr TEXT PRIMARY KEY, value TEXT)
#         ''')
        
#         # First try the correct table name and column name
#         try:
#             self.cursor.execute('''
#                 INSERT INTO account (public_addr, value)
#                 VALUES (?, ?)
#                 ON CONFLICT(public_addr) DO UPDATE SET value=excluded.value
#             ''', (public_addr, data_json))
#             self.conn.commit()
#             return True
#         except Exception as e:
#             print(f"Error writing to account table: {e}")
            
#             # Try legacy table format as fallback
#             try:
#                 self.cursor.execute('''
#                     CREATE TABLE IF NOT EXISTS accounts
#                     (public_addr TEXT PRIMARY KEY, data TEXT NOT NULL)
#                 ''')
                
#                 self.cursor.execute('''
#                     INSERT INTO accounts (public_addr, data)
#                     VALUES (?, ?)
#                     ON CONFLICT(public_addr) DO UPDATE SET data=excluded.data
#                 ''', (public_addr, data_json))
#                 self.conn.commit()
#                 return True
#             except Exception as e2:
#                 print(f"Error writing to accounts table: {e2}")
#                 raise

#     def update_account(self, address, data_json):
#         """Update an account with provided data"""
#         try:
#             # Connect to the database
#             conn = sqlite3.connect(self.filepath)
#             cursor = conn.cursor()

#             if isinstance(data_json, dict):
#                 data_json = json.dumps(data_json)
            
#             # Check if the account already exists
#             cursor.execute("""
#                 SELECT COUNT(*) FROM account WHERE public_addr = ?
#             """, (address,))
#             exists = cursor.fetchone()[0] > 0
            
#             if exists:
#                 # Update the existing account
#                 cursor.execute("""
#                     UPDATE account SET value = ? WHERE public_addr = ?
#                 """, (data_json, address))
#             else:
#                 # Insert a new account
#                 cursor.execute("""
#                     INSERT INTO account (public_addr, value) VALUES (?, ?)
#                 """, (address, data_json))
            
#             # Commit and close
#             conn.commit()
#             conn.close()
#             return True
#         except Exception as e:
#             print(f"Error in update_account: {e}")
#         return False
    
#     def __getstate__(self):
#         # Remove non-picklable objects
#         state = self.__dict__.copy()
#         state['conn'] = None
#         state['cursor'] = None
#         return state

#     def __setstate__(self, state):
#         self.__dict__.update(state)
#         # Reinitialize the connection when unpickled.
#         self.connect()

# class NodeDB(BaseDB):
#     def __init__(self, db_path=None):
#         if db_path:
#             super().__init__(os.path.basename(db_path), "nodes", """
#                 CREATE TABLE IF NOT EXISTS nodes
#                 (port INTEGER PRIMARY KEY)
#             """)
#             self.filepath = db_path
#         else:
#             super().__init__("node.db", "nodes", """
#                 CREATE TABLE IF NOT EXISTS nodes
#                 (port INTEGER PRIMARY KEY)
#             """)
#         self.filename = "node.db"
#         self.table_name = 'nodes'
#         table_schema = '''
#             CREATE TABLE IF NOT EXISTS nodes (
#                 port INTEGER PRIMARY KEY
#            )
#        '''
#         self.conn = None  # Don't open the connection here.
#         self.cursor = None
#         super().__init__(self.filename, table_schema)
    
#     def write(self, item):
#         """Write a new block (item) to the blockchain_data table"""
#         self.connect()
#         # Convert the item to JSON before writing it to the database
#         self.cursor.execute(
#             'INSERT OR IGNORE INTO nodes (port) VALUES (?)',
#             (item,)
#         )
#         self.conn.commit()
        

#     def read_nodes(self):
#         """Read all nodes from the node table"""
#         self.connect()
#         self.cursor.execute('SELECT port FROM nodes')
#         rows = self.cursor.fetchall()
#         if rows:
#             return [row[0] for row in rows]
#         else:
#             return []
        
#     def __getstate__(self):
#         # Remove non-picklable objects
#         state = self.__dict__.copy()
#         state['conn'] = None
#         state['cursor'] = None
#         return state

#     def __setstate__(self, state):
#         self.__dict__.update(state)
#         # Reinitialize the connection when unpickled.
#         self.connect()

import re
import sqlite3
import json
import os
import logging

CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_FILE_DIR, "../../../../../.."))

# Configure logging
logging.basicConfig(
    filename='database.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)
logger = logging.getLogger(__name__)

def resolve_db_path(filename, node_id=None):
    """Try to resolve the correct absolute path for a DB file."""
    cwd = os.getcwd()
    project_root = None
    m = re.search(r'(.*?PoWBlockchain)', cwd)
    if m:
        project_root = m.group(1)

    # Candidate paths
    db_paths = []
    if node_id is not None and project_root:
        db_paths.append(os.path.join(
            project_root, "network_data",
            f"node_{node_id}", "data", filename
        ))
    db_paths += [
        os.path.join("data", filename),
        filename,
        os.path.join(cwd, "data", filename),
        os.path.join(cwd, filename),
    ]
    for p in db_paths:
        if os.path.exists(p):
            return p
    # fallback to first candidate
    return db_paths[0] if db_paths else filename

def _detect_node_id():
    cwd = os.getcwd()
    m = re.search(r'node_(\d+)', cwd)
    return int(m.group(1)) if m else None

class BaseDB:
    def __init__(self,db_path ,filepath, table_name, create_table_sql, node_id=None):
         # --- ADD DEBUG ---
        print(f"[BaseDB Init DEBUG] Received db_path='{db_path}', table='{table_name}', node_id={node_id}", flush=True)
        # --- Use the provided db_path directly ---
        self.filepath = db_path # Assume db_path is the full, correct path
        self.table_name = table_name
        self.node_id = node_id
        self.conn = None
        self.cursor = None
        print(f"[BaseDB Init DEBUG] Set self.filepath='{self.filepath}'. Calling connect...", flush=True)
        # --- END DEBUG ---
        try:
            self.connect()
            if self.conn: # Check connection before creating table
                self._create_table(create_table_sql)
            else:
                print(f"[BaseDB Init {self.node_id}] Connection failed, cannot create table '{self.table_name}'.")
        except Exception as e:
             print(f"[BaseDB Init {self.node_id}] Error during initialization for {self.filepath}: {e}", flush=True)

        # os.makedirs(os.path.dirname(filepath), exist_ok=True)
        # self.filepath = filepath
        # self.table_name = table_name
        # self.conn = None
        # self.cursor = None

        # self.connect()
        # try:
        #     self.cursor.execute(create_table_sql)
        #     self.conn.commit()
        # except Exception as e:
        #     logger.error(f"[{type(self).__name__}] Error creating table {self.table_name}: {e}")
        #     raise # Re-raise critical error
        # # self._create_table()

    # def connect(self):
    #     if not self.conn:
    #         try:
    #             self.conn = sqlite3.connect(self.filepath, timeout=30) # Use self.filepath
    #             self.cursor = self.conn.cursor()
    #             self.cursor.execute("PRAGMA journal_mode=WAL;") # Optional: WAL mode
    #             logger.debug(f"[{type(self).__name__}] Connected to DB: {self.filepath}")
    #         except Exception as e:
    #             logger.error(f"[{type(self).__name__}] FAILED to connect to DB: {self.filepath} - {e}", exc_info=True)
    #             raise

    def connect(self):
        """Establish database connection."""
        if not self.conn:
            # --- ADD DEBUG ---
            print(f"[BaseDB Connect DEBUG {self.node_id}] Attempting to connect to filepath: '{self.filepath}'", flush=True)
            # --- Check for empty path ---
            if not self.filepath:
                logger.error(f"[BaseDB Connect {self.node_id}] Filepath is empty! Cannot connect.")
                print(f"[BaseDB Connect ERROR {self.node_id}] Filepath is empty!", flush=True)
                # Optionally raise an error here or just return to prevent connect attempt
                # raise ValueError("Database filepath cannot be empty")
                return # Prevent connection attempt with empty path
            # --- END DEBUG / CHECK ---
            try:
                # Ensure directory exists
                db_dir = os.path.dirname(self.filepath)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir)
                    logger.info(f"[BaseDB Connect {self.node_id}] Created directory: {db_dir}")

                self.conn = sqlite3.connect(self.filepath, timeout=10, check_same_thread=False)
                self.cursor = self.conn.cursor()
                logger.info(f"[BaseDB Connect {self.node_id}] Successfully connected to {self.filepath}")
                print(f"[BaseDB Connect DEBUG {self.node_id}] Connection successful to '{self.filepath}'", flush=True)
            except sqlite3.Error as e:
                print(f"[BaseDB Connect ERROR {self.node_id}] SQLite error connecting to '{self.filepath}': {e}", flush=True)
                self.conn = None # Ensure conn is None on failure
                self.cursor = None
                # raise # Re-raise if callers should handle connection failure explicitly
            except Exception as e: # Catch other potential errors like OS errors
                print(f"[BaseDB Connect ERROR {self.node_id}] General error connecting to '{self.filepath}': {e}", flush=True)
                self.conn = None
                self.cursor = None

    def _create_table(self):
        self.connect()
        self.cursor.execute(self.table_schema)
        self.conn.commit()
        logger.info(f"Ensured table '{self.table_name}' in {self.filepath}")

    def __getstate__(self):
        st = self.__dict__.copy()
        st['conn'] = None
        st['cursor'] = None
        return st

    def __setstate__(self, st):
        self.__dict__.update(st)
        self.connect()

    def __del__(self):
         if hasattr(self, 'conn') and self.conn:
            self.conn.close()
    
    def read(self):
        self.connect()
        self.cursor.execute(f'SELECT * FROM {self.table_name}')
        rows = self.cursor.fetchall()
        if len(rows) > 0:
            return [json.loads(row[1]) for row in rows]
        else:
            return []

class BlockchainDB(BaseDB):
    def __init__(self, db_path=None, node_id=None):
        db_filename = "blockchain.db" # Default filename
        determined_filepath = None # Variable to hold the final path

        if db_path:
            print(f"[DEBUG] BlockchainDB using explicit path: {db_path}")
            # Use the explicitly passed path (should be absolute)
            determined_filepath = os.path.abspath(db_path)
            logger.info(f"[BlockchainDB] Using explicit db_path: {determined_filepath}")
            print(f"[DEBUG] BlockchainDB using path: {determined_filepath}")

        elif node_id is not None:
            # Fallback: Construct path based on node_id relative to project root (less reliable if PROJECT_ROOT isn't defined correctly here)
            # This relies on resolve_db_path or similar logic finding the project root
            # For simplicity, let's assume PROJECT_ROOT is defined globally in db.py if this fallback is needed
            if 'PROJECT_ROOT' in globals():
                 determined_filepath = os.path.join(PROJECT_ROOT, "network_data", f"node_{node_id}", "data", db_filename)
                 logger.warning(f"[BlockchainDB] No explicit db_path. Using node_id {node_id}. Constructed path: {determined_filepath}")
            else:
                 # Last resort: relative to CWD (likely wrong)
                 determined_filepath = os.path.abspath(os.path.join("data", f"Node_{node_id}", db_filename)) # Example CWD-relative path
                 logger.error(f"[BlockchainDB] CRITICAL: No explicit db_path and PROJECT_ROOT not defined. Defaulting to potentially incorrect CWD path: {determined_filepath}")

        else:
             # Absolute last resort if neither db_path nor node_id is given
             determined_filepath = os.path.abspath(db_filename)
             logger.error(f"[BlockchainDB] CRITICAL: No db_path/node_id provided. Defaulting to CWD path: {determined_filepath}")

        # Log the final path being used before calling super()
        logger.info(f"[BlockchainDB] Final determined path for BaseDB: {determined_filepath}")

        # --- ADD create_table_sql ARGUMENT ---
        create_blocks_table_sql = """
            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )
        """
        # --- END ADD ---

        # Initialize BaseDB with the determined absolute filepath
        super().__init__(
            filepath=determined_filepath,
            db_path=determined_filepath,
            table_name="blocks",
            create_table_sql=create_blocks_table_sql, # Pass the SQL string
            node_id=node_id
        )
        logger.info(f"[BlockchainDB {node_id}] Initialized with DB path: {self.filepath}")

        # --- Create the Transaction Index Table ---
        try:
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
            logger.info(f"[BlockchainDB] Transaction index table 'tx_index' ensured in {self.filepath}.")
        except Exception as e:
            logger.error(f"[BlockchainDB] Error creating tx_index table in {self.filepath}: {e}", exc_info=True)
            raise

        # Ensure connection is established (BaseDB should handle this)
        # self.connect() # Might be redundant
        logger.info(f"[BlockchainDB] Initialized successfully with DB file: {self.filepath}")

        # db_filename = "blockchain.db" # Default filename
        # determined_filepath = None
        
        # if db_path:
        #     determined_filepath = os.path.abspath(db_path)
        #     logger.info(f"[BlockchainDB] Using explicit db_path: {determined_filepath}")
        #     # Ensure directory exists
        #     os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

        # elif node_id is not None:
        #     # Construct path based on node_id
        #     data_dir = os.path.join(os.getcwd(), "data", f"Node_{node_id}")
        #     os.makedirs(data_dir, exist_ok=True)
        #     self.filepath = os.path.join(data_dir, db_filename)

        # else:
        #     # Default path if no path or node_id provided
        #     self.filepath = os.path.join(os.getcwd(), db_filename)
        
        # logger.info(f"[BlockchainDB] Initializing DB at: {self.filepath}")

        # # Initialize BaseDB with the determined path/filename
        # super().__init__(self.filepath, "blocks", # Pass full path to BaseDB
        #     """CREATE TABLE IF NOT EXISTS blocks (
        #            id INTEGER PRIMARY KEY AUTOINCREMENT, -- Represents Height + 1
        #            data TEXT NOT NULL
        #        )""",
        #     node_id=None # BaseDB doesn't need node_id if full path is given
        # )

        # # --- Create the Transaction Index Table ---
        # try:
        #     self.cursor.execute(
        #         """CREATE TABLE IF NOT EXISTS tx_index (
        #                tx_hash TEXT PRIMARY KEY,
        #                block_height INTEGER NOT NULL
        #            )"""
        #     )
        #     # Optional: Add an index for faster block_height lookups during deletion
        #     self.cursor.execute(
        #         """CREATE INDEX IF NOT EXISTS idx_tx_block_height ON tx_index (block_height)"""
        #     )
        #     self.conn.commit()
        #     logger.info(f"[BlockchainDB] Transaction index table 'tx_index' ensured.")
        # except Exception as e:
        #     logger.error(f"[BlockchainDB] Error creating tx_index table: {e}", exc_info=True)
        #     raise # Re-raise critical error
            
            
        # Ensure connection is established after super init if BaseDB doesn't do it
        # self.connect()

    def write(self, block_dict):
        """Writes a block dict to the DB and updates the tx_index."""
        self.connect()
        block_height = block_dict.get('Height')
        if block_height is None:
             logger.error("[BlockchainDB.write] Block dictionary missing 'Height'. Cannot write.")
             raise ValueError("Block dictionary missing 'Height'")

        try:
            # Assuming block is a dict or object that _make_serializable handles
            serial = json.dumps(self._make_serializable(block_dict))
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
                # Using INSERT OR IGNORE assumes tx_hash is unique across blocks,
                # which should be true. If a tx appears in multiple blocks (reorg scenario),
                # this will keep the first entry. This might need adjustment depending
                # on how reorgs are fully handled (e.g., delete first).

            self.conn.commit()
            logger.info(f"[BlockchainDB.write] Block {block_height} written successfully to {self.filepath}.")
        except Exception as e:
            logger.error(f"[BlockchainDB.write] Error writing block {block_height} to DB {self.filepath}: {e}", exc_info=True)
            self.conn.rollback()
            raise

    # def update(self, data):
    #     self.connect()
    #     self.cursor.execute('DELETE FROM blocks')
    #     self.conn.commit()
    #     for item in data:
    #         public_addr = item.get('public_addr')
    #         if public_addr is None:
    #             logger.error("Missing 'public_addr' in data item.")
    #             continue
    #         self.write(public_addr, item)

    # def update(self, blockchain_data):
    #     # 1) Log the raw argument
    #     print(f"[BlockchainDB.update] received: type={type(blockchain_data)} repr={repr(blockchain_data)[:200]}")
    #     # 2) If it’s a proxy or single object, try to unwrap
    #     if not isinstance(blockchain_data, (list, tuple)):
    #         try:
    #             print("→ Not a list/tuple, attempting to call .read_all_blocks() on it …")
    #             blockchain_data = blockchain_data.read_all_blocks()
    #             print(f"→ Unwrapped to list: {blockchain_data}")
    #         except Exception as e:
    #             print("→ Could not unwrap:", e)

    #     # 3) Inspect a few items
    #     for i, item in enumerate(blockchain_data):
    #         if i >= 5: break
    #         print(f"[BlockchainDB.update] item {i}: type={type(item)} repr={repr(item)[:200]}")

    #     # 4) Now do the real update
    #     self.connect()
    #     try:
    #         self.cursor.execute(f"DELETE FROM {self.table_name}")
    #         self.conn.commit()
    #         for entry in blockchain_data:
    #             blk = entry[0] if isinstance(entry, list) else entry
    #             self.write(blk)
    #         print(f"[BlockchainDB.update] wrote {len(blockchain_data)} blocks")
    #         return True
    #     except Exception as e:
    #         print("[BlockchainDB.update] ERROR writing blocks:", e)
    #         import traceback; traceback.print_exc()
    #         return False

    def update(self, blockchain_data):
        """Replaces the entire blockchain and rebuilds the index."""
        self.connect()
        try:
            logger.warning(f"[BlockchainDB.update] Replacing entire blockchain in {self.filepath}...")
            # --- Clear existing data ---
            self.cursor.execute(f"DELETE FROM {self.table_name}")
            self.conn.commit()

            # --- Write new data and rebuild index ---
            count = 0
            tx_index_entries = []
            for entry in blockchain_data:
                # Handle potential nesting if entry is list [block_dict]
                blk_dict = entry[0] if isinstance(entry, list) and len(entry) == 1 else entry
                if isinstance(blk_dict, dict): # Basic check
                    block_height = blk_dict.get('Height')
                    if block_height is None:
                         logger.warning(f"[DB Update] Skipping entry without Height: {blk_dict.get('BlockHeader', {}).get('blockHash', 'N/A')}")
                         continue
                    
                    # Write block
                    serial = json.dumps(self._make_serializable(blk_dict))
                    self.cursor.execute("INSERT INTO blocks (data) VALUES (?)", (serial,))
                    count += 1

                    # Collect index entries
                    for tx in blk_dict.get('Txs', []):
                        tx_id = tx.get('TxId')
                        if tx_id:
                            tx_index_entries.append((tx_id, block_height))
                else:
                    logger.warning(f"[DB Update] Skipping invalid entry: type={type(blk_dict)}")

                # --- Bulk insert index entries ---
                if tx_index_entries:
                    self.cursor.executemany(
                        "INSERT OR IGNORE INTO tx_index (tx_hash, block_height) VALUES (?, ?)",
                        tx_index_entries
                    )

            self.conn.commit()
            logger.info(f"[BlockchainDB.update] Wrote {count} blocks and rebuilt tx_index in {self.filepath}")
            return True
        except Exception as e:
            logger.error(f"[BlockchainDB.update] ERROR updating blockchain in {self.filepath}: {e}", exc_info=True)
            self.conn.rollback()
            return False
                    
        #             self.write(blk) # Call the instance write method
        #             count += 1
        #         else:
        #              logger.warning(f"[DB Update] Skipping invalid entry: type={type(blk)}")

        #     logger.info(f"[BlockchainDB.update] wrote {count} blocks to {self.filepath}")
        #     return True
        # except Exception as e:
        #     logger.error(f"[BlockchainDB.update] ERROR writing blocks to {self.filepath}: {e}")
        #     self.conn.rollback()
        #     import traceback; traceback.print_exc()
        #     return False

    def lastBlock(self):
        """Retrieve the last block in the blockchain"""
        self.connect()
        try:
            self.cursor.execute('SELECT data FROM blocks ORDER BY id DESC LIMIT 1')
            row = self.cursor.fetchone()
            if not row:
                print("[BlockchainDB.lastBlock] No blocks found.")
                return None
            
            raw = row[0]
            obj = json.loads(raw)
            # print(f"[DEBUG lastBlock] raw JSON   = {raw!r}")
            # print(f"[DEBUG lastBlock] loaded obj = {obj!r} (type={type(obj)})")
            
            # --- Unwrapping Logic ---
            # Handle accidental [[{...}]]
            if isinstance(obj, list) and obj and isinstance(obj[0], list):
                obj = obj[0]
                logger.warning("[BlockchainDB.lastBlock] Unwrapped nested list [[dict]].")
            # Handle accidental [{...}]
            if isinstance(obj, list) and len(obj) == 1 and isinstance(obj[0], dict):
                 obj = obj[0]
                 logger.warning("[BlockchainDB.lastBlock] Unwrapped list [dict].")
            # --- End Unwrapping ---

            # Final check if it's a dictionary
            if not isinstance(obj, dict):
                 logger.error(f"[BlockchainDB.lastBlock] Loaded object is not a dictionary after unwrapping: type={type(obj)}")
                 return None # Or raise error
            
            return obj
        except json.JSONDecodeError as e:
            logger.error(f"[BlockchainDB.lastBlock] ERROR decoding JSON for last block: {e} - Data: {raw[:100]}...")
            return None
        except Exception as e:
            logger.error(f"[BlockchainDB.lastBlock] ERROR reading last block: {e}", exc_info=True) # Use exc_info
            # import traceback; traceback.print_exc() # Remove if using logger exc_info
            return None

    # def read_all_blocks(self):
    #     self.connect()
    #     self.cursor.execute("SELECT data FROM blocks ORDER BY id ASC")
    #     return [json.loads(r[0]) for r in self.cursor.fetchall()]

    def read_all_blocks(self):
        self.connect()
        try: # Added try block
            self.cursor.execute("SELECT data FROM blocks ORDER BY id ASC")
            # Use list comprehension, handle potential JSON errors if needed
            blocks = []
            for r in self.cursor.fetchall():
                try:
                    obj = json.loads(r[0])
                    # --- Unwrapping Logic ---
                    if isinstance(obj, list) and len(obj) == 1 and isinstance(obj[0], dict):
                        obj = obj[0]
                        logger.warning("[DB ReadAll] Unwrapped list [dict] for a block.")
                    # --- End Unwrapping ---

                    if isinstance(obj, dict):
                        blocks.append(obj)
                    else:
                         logger.error(f"[DB ReadAll] Skipping non-dictionary object found in DB: type={type(obj)}")

                except json.JSONDecodeError as e:
                    logger.error(f"[DB ReadAll] Error decoding JSON: {e} - Data: {r[0][:100]}...")
            return blocks
        except Exception as e:
            logger.error(f"[DB ReadAll] Error reading all blocks from {self.filepath}: {e}")
            return [] # Return empty list on error
        
    
    def delete_blocks_from_height(self, height):
        """
        Deletes blocks with Height >= specified height from 'blocks'
        and corresponding entries from 'tx_index'.
        Assumes id = Height + 1.
        """
        min_id_to_delete = height + 1
        min_height_to_delete = height

        self.connect()
        deleted_block_count = 0
        deleted_index_count = 0
        try:
            # --- Delete from tx_index first (or use foreign keys if supported/desired) ---
            self.cursor.execute("DELETE FROM tx_index WHERE block_height >= ?", (min_height_to_delete,))
            deleted_index_count = self.cursor.rowcount

            # --- Delete from blocks ---
            self.cursor.execute("DELETE FROM blocks WHERE id >= ?", (min_id_to_delete,))
            deleted_block_count = self.cursor.rowcount

            self.conn.commit()
            logger.info(f"[DB Reorg] Deleted {deleted_block_count} block(s) (id >= {min_id_to_delete}) and {deleted_index_count} tx_index entries (height >= {min_height_to_delete}) from {self.filepath}")
            return deleted_block_count # Return block count as before
        except Exception as e:
            logger.error(f"[DB Reorg] Error deleting blocks from height {height} in {self.filepath}: {e}", exc_info=True)
            self.conn.rollback()
            return 0

    def read_block(self, height):
        """
        Reads a single block by its height.
        Assumes id = Height + 1.
        """
        target_id = height + 1
        self.connect()
        try:
            self.cursor.execute("SELECT data FROM blocks WHERE id = ?", (target_id,))
            row = self.cursor.fetchone()
            if row:
                try:
                    obj = json.loads(row[0])
                    # --- Unwrapping Logic ---
                    if isinstance(obj, list) and len(obj) == 1 and isinstance(obj[0], dict):
                        obj = obj[0]
                        logger.warning(f"[DB ReadBlock] Unwrapped list [dict] for block height {height}.")
                    # --- End Unwrapping ---

                    if not isinstance(obj, dict):
                         logger.error(f"[DB ReadBlock] Loaded object is not a dictionary for height {height}: type={type(obj)}")
                         return None

                    return obj # Return single dict
                except json.JSONDecodeError as e:
                    logger.error(f"[DB ReadBlock] Error decoding JSON for block height {height} (id {target_id}): {e} - Data: {row[0][:100]}...")
                    return None
            else:
                logger.info(f"[DB ReadBlock] Block height {height} (id {target_id}) not found in {self.filepath}.")
                return None # Block not found
        except Exception as e:
            logger.error(f"[DB ReadBlock] Error reading block height {height} (id {target_id}) from {self.filepath}: {e}")
            return None # Return None on error
        
    # --- NEW METHOD to query the transaction index ---
    def get_tx_block_height(self, tx_hash):
        """Finds the block height containing the given transaction hash."""
        self.connect()
        try:
            self.cursor.execute("SELECT block_height FROM tx_index WHERE tx_hash = ?", (tx_hash,))
            row = self.cursor.fetchone()
            if row:
                return row[0] # Return the block height
            else:
                logger.debug(f"[DB Index] Transaction hash {tx_hash} not found in tx_index.")
                return None # Not found
        except Exception as e:
            logger.error(f"[DB Index] Error querying tx_index for hash {tx_hash}: {e}", exc_info=True)
            return None

    def _make_serializable(self, obj):
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k,v in obj.items()}
        if isinstance(obj, list):
            return [self._make_serializable(i) for i in obj]
        if isinstance(obj, bytes):
            return obj.hex()
        if hasattr(obj, 'to_dict'): # Example: If objects have a to_dict method
             return self._make_serializable(obj.to_dict())
        return obj
    
    # --- NEW METHOD to read a block by its hash ---
    def read_block_by_hash(self, block_hash_hex):
        """Reads a single block dictionary from the DB using its hash."""
        self.connect()
        # This is inefficient as it requires scanning and parsing all blocks.
        # A block_hash index would be much better if performance is critical.
        logger.debug(f"[DB ReadByHash] Searching for block hash {block_hash_hex} (full scan)...")
        try:
            self.cursor.execute("SELECT data FROM blocks ORDER BY id DESC") # Search recent blocks first
            for r in self.cursor.fetchall():
                try:
                    obj = json.loads(r[0])
                    # Unwrapping logic (ensure consistency with other read methods)
                    if isinstance(obj, list) and len(obj) == 1 and isinstance(obj[0], dict):
                        obj = obj[0]

                    if isinstance(obj, dict):
                        # Extract block hash from the dictionary
                        # Handle potential variations in key names
                        header = obj.get('BlockHeader', {})
                        current_block_hash = header.get('blockHash') or obj.get('blockHash')

                        if current_block_hash == block_hash_hex:
                            logger.debug(f"[DB ReadByHash] Found block hash {block_hash_hex}.")
                            return obj # Return the dictionary
                    else:
                        logger.warning(f"[DB ReadByHash] Skipping non-dict object during scan.")

                except json.JSONDecodeError as e:
                    logger.warning(f"[DB ReadByHash] Error decoding JSON during scan: {e} - Data: {r[0][:100]}...")
                except Exception as inner_e:
                     logger.warning(f"[DB ReadByHash] Error processing row during scan: {inner_e}")


            logger.debug(f"[DB ReadByHash] Block hash {block_hash_hex} not found in DB.")
            return None # Not found after scanning all blocks
        except Exception as e:
            logger.error(f"[DB ReadByHash] Error reading block by hash {block_hash_hex}: {e}", exc_info=True)
            return None


class AccountDB(BaseDB):
    def __init__(self, db_path=None, node_id=None):
        fname = os.path.basename(db_path) if db_path else "account.db"
        super().__init__(fname, "account",
            """CREATE TABLE IF NOT EXISTS account (
                   public_addr TEXT PRIMARY KEY,
                   value TEXT NOT NULL
               )""",
            node_id=node_id
        )
        if db_path:
            self.filepath = db_path

    def read(self):
        self.connect()
        self.cursor.execute("SELECT value FROM account")
        return [json.loads(r[0]) for r in self.cursor.fetchall()]

    def write(self, addr, data):
        self.connect()
        j = json.dumps(data)
        self.cursor.execute("""
            INSERT INTO account (public_addr,value)
            VALUES (?,?)
            ON CONFLICT(public_addr) DO UPDATE SET value=excluded.value
        """, (addr, j))
        self.conn.commit()

    def read_account(self, addr):
        self.connect()
        self.cursor.execute("SELECT value FROM account WHERE public_addr=?", (addr,))
        r = self.cursor.fetchone()
        return json.loads(r[0]) if r else None

class NodeDB(BaseDB):
    def __init__(self, db_path=None, node_id=None):
        print(f"[NodeDB Init DEBUG] Received db_path='{db_path}', node_id={node_id}", flush=True)
        # --- Determine the CORRECT path for node.db ---
        # This logic needs refinement based on where node.db should live.
        # Assuming it lives alongside blockchain.db:
        if db_path:
            node_db_actual_path = os.path.join(os.path.dirname(db_path), f"node_{node_id}.db" if node_id is not None else "node.db")
        else:
             node_db_actual_path = f"node_{node_id}.db" if node_id is not None else "node.db"
        print(f"[NodeDB Init DEBUG] Determined node_db_actual_path='{node_db_actual_path}'", flush=True)
        
         # --- Pass the CORRECT path to BaseDB ---
        super().__init__(db_path=node_db_actual_path, # Pass the determined path for node.db
            table_name="nodes", # Pass table name if BaseDB uses it
            create_table_sql="""CREATE TABLE IF NOT EXISTS nodes (
                   port INTEGER PRIMARY KEY
               )""",
            node_id=node_id
        )
        # self.filepath should now be correctly set by BaseDB
        print(f"[NodeDB Init DEBUG] self.filepath after BaseDB init: '{getattr(self, 'filepath', 'Not Set')}'", flush=True)

    def write(self, port):
        self.connect()
        self.cursor.execute("INSERT OR IGNORE INTO nodes (port) VALUES (?)", (port,))
        self.conn.commit()

    def read_nodes(self):
        self.connect()
        self.cursor.execute("SELECT port FROM nodes")
        return [r[0] for r in self.cursor.fetchall()]
    
    def __getstate__(self):
        # Remove non-picklable objects
        state = self.__dict__.copy()
        state['conn'] = None
        state['cursor'] = None
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        # Reinitialize the connection when unpickled.
        self.connect()

