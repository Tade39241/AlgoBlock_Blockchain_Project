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
            self.conn = sqlite3.connect(self.filepath)
            self.cursor = self.conn.cursor()

    def _create_table(self):
        self.connect()
        self.cursor.execute(self.table_schema)
        self.conn.commit()
        logger.info(f"Ensured table exists in {self.filepath}")

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
            logger.info(f"Account {public_addr} written/updated successfully.")
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
    def __init__(self):
        self.table_name = 'blocks'
        self.filename = 'blockchain.db'
        table_schema = '''
            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )
        '''
        self.conn = None  # Don't open the connection here.
        self.cursor = None
        super().__init__(self.filename, table_schema)

    def connect(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.filename)
            self.cursor = self.conn.cursor()

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
        
    
        
class AccountDB(BaseDB):
    def __init__(self, custom_filepath=None):
        self.table_name = 'account'  # SINGULAR - to match actual DB
        self.filename = custom_filepath if custom_filepath else "account.db"
        table_schema = '''
            CREATE TABLE IF NOT EXISTS account (  
                public_addr TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        '''
        self.conn = None  # Don't open the connection here.
        self.cursor = None
        super().__init__(self.filename, table_schema)


    # def write_account(self, account_data):
    #     """
    #     Write or update a single account dict in the DB.
    #     """
    #     self.connect()
    #     public_addr = account_data.get('public_addr')
    #     if public_addr is None:
    #         logger.error("Attempted to write account without 'public_addr'.")
    #         raise ValueError("Account data must include 'public_addr'.")
        
    #     try:
    #         # Use 'account' instead of 'accounts' and 'value' instead of 'data'
    #         self.cursor.execute('''
    #             INSERT INTO account (public_addr, value)
    #             VALUES (?, ?)
    #             ON CONFLICT(public_addr) DO UPDATE SET value=excluded.value
    #         ''', (public_addr, json.dumps(account_data)))
    #         self.conn.commit()
    #         logger.info(f"Account {public_addr} written/updated successfully.")
    #     except Exception as e:
    #         logger.error(f"Error writing account {public_addr} to DB: {e}")
    #         raise
    

    # def read_account(self, address):
    #     """
    #     Retrieve a single account dict from DB by its public address.
    #     Returns None if not found.
    #     """
    #     self.connect()
    #     self.cursor.execute('SELECT value FROM account WHERE public_addr = ?', (address,))
    #     row = self.cursor.fetchone()
    #     if row:
    #         return json.loads(row[0])
    #     return None

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

class NodeDB(BaseDB):
    def __init__(self):
        self.filename = "node.db"
        self.table_name = 'nodes'
        table_schema = '''
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )
        '''
        self.conn = None  # Don't open the connection here.
        self.cursor = None
        super().__init__(self.filename, table_schema)
        self._initialise_with_8888()
    
    def write(self, item):
        """Write a new block (item) to the blockchain_data table"""
        self.connect()
        # Convert the item to JSON before writing it to the database
        data_json = json.dumps(item)
        self.cursor.execute('INSERT INTO nodes (data) VALUES (?)', (data_json,))
        self.conn.commit()

    def _initialise_with_8888(self):
        """Initialize the database with [8888] if it's empty"""
        self.connect()
        # Check if any data exists in the node.db table
        self.cursor.execute('SELECT data FROM nodes')
        rows = self.cursor.fetchall()

        # If the database is empty, add [8888]
        if not rows:
            self.write(8888)

    def read_nodes(self):
        """Read all nodes from the blockchain_data table"""
        self.connect()
        self.cursor.execute('SELECT data FROM nodes')
        rows = self.cursor.fetchall()
        if rows:
            return [int(row[0]) for row in rows]
        else:
            return []


