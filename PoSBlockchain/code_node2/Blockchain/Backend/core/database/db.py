import sqlite3
import json
import os
import logging

# Configure logging
logging.basicConfig(
    filename='database.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)
logger = logging.getLogger(__name__)


def resolve_db_path(filename, node_id=None):
    """
    Try to resolve the correct absolute path for a DB file.
    If node_id is not given, try to extract it from the current working directory.
    """
    cwd = os.getcwd()
    db_paths = []

    # Check for validator_node in cwd
    if "validator_node" in cwd:
        db_paths.append(os.path.join(
            "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data",
            "validator_node/data", filename
        ))

    if node_id is None:
        import re
        match = re.search(r'node_(\d+)', cwd)
        if match:
            node_id = int(match.group(1))
    # Try the most likely paths first
    
    if node_id is not None:
        db_paths.append(os.path.join(
            "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data",
            f"node_{node_id}/data/{filename}"
        ))

    # Add the default paths 
    db_paths.extend([
        os.path.join("data", filename),
        filename,
        os.path.join(cwd, "data", filename),
        os.path.join(cwd, filename)
    ])
    for path in db_paths:
        if os.path.exists(path):
            return path
    # If not found, return the preferred path (even if it doesn't exist yet)
    return db_paths[0] if db_paths else filename

class BaseDB:
    def __init__(self, filename, table_schema):
        self.basepath = 'data'
        self.filepath = os.path.join(self.basepath, filename)
        self.conn = None
        self.cursor = None
        self.table_schema = table_schema
        self._create_table()
    
    def connect(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.filepath, timeout=30)
            self.cursor = self.conn.cursor()
            self.cursor.execute("PRAGMA journal_mode=WAL;")
        # if self.conn is None:
        #     self.conn = sqlite3.connect(self.filepath)
        #     self.cursor = self.conn.cursor()
        

    def _create_table(self):
        self.connect()
        self.cursor.execute(self.table_schema)
        self.conn.commit()
        # logger.info(f"Ensured table exists in {self.filepath}")

    def read(self):
        self.connect()
        self.cursor.execute(f'SELECT * FROM {self.table_name}')
        rows = self.cursor.fetchall()
        if len(rows) > 0:
            return [json.loads(row[1]) for row in rows]
        else:
            return []
        
    def update(self, data):
        self.connect()
        self.cursor.execute('DELETE FROM blocks')
        self.conn.commit()
        for item in data:
            public_addr = item.get('public_addr')
            if public_addr is None:
                logger.error("Missing 'public_addr' in data item.")
                continue
            self.write(public_addr, item)

    def write(self, public_addr, data):
        self.connect()
        try:
            self.cursor.execute('''
                INSERT INTO accounts (public_addr, data)
                VALUES (?, ?)
                ON CONFLICT(public_addr) DO UPDATE SET data=excluded.data
            ''', (public_addr, json.dumps(data)))
            self.conn.commit()
            # logger.info(f"Account {public_addr} written/updated successfully.")
        except Exception as e:
            logger.error(f"Error writing account {public_addr} to DB: {e}")
            raise

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

    def __del__(self):
        if self.conn:
            self.conn.close()



class BlockchainDB(BaseDB):
    def __init__(self, db_path=None, node_id=None):
        self.table_name = 'blocks'
        self.filename = db_path if db_path else 'blockchain.db'
        table_schema = '''
            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )
        '''
        self.conn = None
        self.cursor = None
        # Use resolve_db_path to get the correct path
        resolved_path = resolve_db_path(self.filename, node_id=node_id)
        super().__init__(resolved_path, table_schema)
        self.filepath = resolved_path  # Ensure absolute path is used

    def connect(self):
        if self.conn is None:
            try:
                # logging.info(f"[PID {os.getpid()}] BlockchainDB.connect attempting: sqlite3.connect('{self.filepath}')")
                self.conn = sqlite3.connect(self.filepath)
                # logging.info(f"[PID {os.getpid()}] BlockchainDB.connect successful for: '{self.filepath}'")
                self.cursor = self.conn.cursor()
            except sqlite3.Error as e:
                logging.error(f"[PID {os.getpid()}] BlockchainDB.connect error: {e}")
                raise


    def write(self, block):
        """
        Insert a block into the blocks table.
        """
        self.connect()
        try:
            # Ensure all bytes in the block dict are converted to hex strings
            block_serializable = self.make_serializable(block)
            data_json = json.dumps(block_serializable)
            self.cursor.execute('''
                INSERT INTO blocks (data)
                VALUES (?)
            ''', (data_json,))
            self.conn.commit()
            logger.info(f"Block written successfully.")
        except Exception as e:
            logger.error(f"Error writing block to DB: {e}")
            raise

    def lastBlock(self):
        """Retrieve the last block in the blockchain"""
        self.connect()
        self.cursor.execute('SELECT data FROM blocks ORDER BY id DESC LIMIT 1')
        row = self.cursor.fetchone()
        if row:
            return json.loads(row[0])
        else:
            return None
    
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

    def read_block_by_hash(self, block_hash_hex):
        """
        Reads a block from the database using its block hash.
        Assumes block data is stored as JSON text in the 'data' column
        and contains the path '$.BlockHeader.blockHash'.

        Args:
            block_hash_hex (str): The block hash (hex string) to search for.

        Returns:
            dict: The block data as a dictionary if found, otherwise None.
                  Returns None also in case of database or JSON errors.
        """
        conn = None
        cursor = None
        # Define query using json_extract
        # The path '$.BlockHeader.blockHash' navigates the JSON structure
        query = f"SELECT data FROM {self.table_name} WHERE json_extract(data, '$.BlockHeader.blockHash') = ?"

        try:
            # Use a short-lived connection for this specific read for safety
            # Connect using the filepath stored during __init__
            conn = sqlite3.connect(self.filepath, timeout=10)
            # Set pragmas for potentially better read performance/concurrency
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")

            cursor = conn.cursor()
            logger.debug(f"Executing query: {query} with hash: {block_hash_hex}")
            cursor.execute(query, (block_hash_hex,))
            result = cursor.fetchone() # Fetch one row

            if result:
                block_data_json = result[0]
                try:
                    block_data_dict = json.loads(block_data_json)
                    logger.debug(f"Found block with hash {block_hash_hex}")
                    return block_data_dict # Return the parsed dictionary
                except json.JSONDecodeError as json_err:
                    logger.error(f"Failed to decode JSON for block hash {block_hash_hex} from DB: {json_err}")
                    logger.error(f"Invalid JSON data was: {block_data_json[:200]}...") # Log snippet
                    return None # Cannot parse data
            else:
                logger.debug(f"Block with hash {block_hash_hex} not found.")
                return None # Block not found

        except sqlite3.OperationalError as op_err:
            # Specific check for "no such function: json_extract"
            if "no such function: json_extract" in str(op_err):
                 logger.error("SQLite JSON1 extension is not enabled or available. Cannot use read_block_by_hash.")
                 # Consider falling back to a less efficient method here if needed
            else:
                 logger.error(f"SQLite OperationalError in read_block_by_hash (Hash: {block_hash_hex}): {op_err}", exc_info=True)
            return None # Indicate error
        except sqlite3.Error as sql_err:
            logger.error(f"SQLite error in read_block_by_hash (Hash: {block_hash_hex}): {sql_err}", exc_info=True)
            return None # Indicate error
        except Exception as e:
            # Catch any other unexpected errors
             logger.error(f"Unexpected error in read_block_by_hash (Hash: {block_hash_hex}): {e}", exc_info=True)
             return None
        finally:
            # Ensure connection is closed
            if cursor:
                try: cursor.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass


    def read_all_blocks(self):
        """Read all blocks from the blocks table"""
        self.connect()
        self.cursor.execute('SELECT data FROM blocks ORDER BY id ASC')
        rows = self.cursor.fetchall()
        if rows:
            # Return the data as a list of dictionaries (blocks)
            return [json.loads(row[0]) for row in rows]
        else:
            return []

    def make_serializable(self, obj):
        
        """Recursively convert bytes to hex strings in the object"""
        if isinstance(obj, dict):
            return {k: self.make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.make_serializable(item) for item in obj]
        elif isinstance(obj, bytes):
            return obj.hex()
        else:
            return obj
    
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
        
class AccountDB(BaseDB):
    def __init__(self, db_path=None): # Allow optional db_path override
        self.table_name = 'account'  # *** SET THE CORRECT TABLE NAME HERE ***
        self.filename = "account.db"
        # *** USE THE CORRECT TABLE NAME IN THE SCHEMA ***
        table_schema = '''
            CREATE TABLE IF NOT EXISTS account (  
                public_addr TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        '''
        self.conn = None
        self.cursor = None
        # Handle explicit db_path if provided, otherwise use default logic
        effective_filename = db_path if db_path else self.filename
        # Call BaseDB init AFTER setting table_name and schema
        # BaseDB needs filename and schema, but uses self.filepath internally
        # We need to adjust how BaseDB gets the path if overridden
        super().__init__(effective_filename, table_schema)
        # Override filepath if db_path was given, as BaseDB defaults to data/ subdir
        if db_path:
            self.filepath = db_path # Ensure filepath is the absolute one provided
        
        # print(f"[DEBUG] AccountDB using path: {self.filepath}")


    def read_account(self, address):
        """
        Retrieve a single account dict from DB by its public address.
        Returns None if not found.
        """
        # Connect if needed
        if not hasattr(self, 'conn') or self.conn is None:
            if hasattr(self, 'connect'):
                self.connect()
            else:
                import sqlite3
                self.conn = sqlite3.connect(self.db_path if hasattr(self, 'db_path') else 
                                        (self.filename if hasattr(self, 'filename') else 'account.db'))
                self.cursor = self.conn.cursor()
        
        # First try the correct table name and column name
        self.cursor.execute('SELECT value FROM account WHERE public_addr = ?', (address,))
        row = self.cursor.fetchone()
        if row:
            import json
            return json.loads(row[0])
            
        # If not found, try legacy table/column names
        try:
            self.cursor.execute('SELECT data FROM accounts WHERE public_addr = ?', (address,))
            row = self.cursor.fetchone()
            if row:
                import json
                return json.loads(row[0])
        except:
            pass
            
        return None

    def write_account(self, account_data):
        """
        Write or update a single account dict in the DB.
        """
        public_addr = account_data.get('public_addr')
        if public_addr is None:
            raise ValueError("Account data must include 'public_addr'.")
        
        if not hasattr(self, 'conn') or self.conn is None:
            if hasattr(self, 'connect'):
                self.connect()
            else:
                import sqlite3
                self.conn = sqlite3.connect(self.db_path if hasattr(self, 'db_path') else 
                                        (self.filename if hasattr(self, 'filename') else 'account.db'))
                self.cursor = self.conn.cursor()
        
        import json
        data_json = json.dumps(account_data)
        
        # Create the account table if it doesn't exist
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS account
            (public_addr TEXT PRIMARY KEY, value TEXT)
        ''')
        
        # First try the correct table name and column name
        try:
            self.cursor.execute('''
                INSERT INTO account (public_addr, value)
                VALUES (?, ?)
                ON CONFLICT(public_addr) DO UPDATE SET value=excluded.value
            ''', (public_addr, data_json))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error writing to account table: {e}")
            
            # Try legacy table format as fallback
            try:
                self.cursor.execute('''
                    CREATE TABLE IF NOT EXISTS accounts
                    (public_addr TEXT PRIMARY KEY, data TEXT NOT NULL)
                ''')
                
                self.cursor.execute('''
                    INSERT INTO accounts (public_addr, data)
                    VALUES (?, ?)
                    ON CONFLICT(public_addr) DO UPDATE SET data=excluded.data
                ''', (public_addr, data_json))
                self.conn.commit()
                return True
            except Exception as e2:
                print(f"Error writing to accounts table: {e2}")
                raise

    def update_account(self, address, data_json):
        """Update an account with provided data"""
        try:
            # Connect to the database
            conn = sqlite3.connect(self.filepath)
            cursor = conn.cursor()

            if isinstance(data_json, dict):
                data_json = json.dumps(data_json)
            
            # Check if the account already exists
            cursor.execute("""
                SELECT COUNT(*) FROM account WHERE public_addr = ?
            """, (address,))
            exists = cursor.fetchone()[0] > 0
            
            if exists:
                # Update the existing account
                cursor.execute("""
                    UPDATE account SET value = ? WHERE public_addr = ?
                """, (data_json, address))
            else:
                # Insert a new account
                cursor.execute("""
                    INSERT INTO account (public_addr, value) VALUES (?, ?)
                """, (address, data_json))
            
            # Commit and close
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error in update_account: {e}")
        return False
    
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

class NodeDB(BaseDB):
    def __init__(self):
        self.filename = "node.db"
        self.table_name = 'nodes'
        table_schema = '''
            CREATE TABLE IF NOT EXISTS nodes (
                port INTEGER PRIMARY KEY
           )
       '''
        self.conn = None  # Don't open the connection here.
        self.cursor = None
        super().__init__(self.filename, table_schema)
    
    def write(self, item):
        """Write a new block (item) to the blockchain_data table"""
        self.connect()
        # Convert the item to JSON before writing it to the database
        self.cursor.execute(
            'INSERT OR IGNORE INTO nodes (port) VALUES (?)',
            (item,)
        )
        self.conn.commit()
        

    def read_nodes(self):
        """Read all nodes from the node table"""
        self.connect()
        self.cursor.execute('SELECT port FROM nodes')
        rows = self.cursor.fetchall()
        if rows:
            return [row[0] for row in rows]
        else:
            return []
        
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


