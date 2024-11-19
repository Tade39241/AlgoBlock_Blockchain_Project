# import os
# import json

# class BaseDB:
#     def __init__(self):
#         self.basepath = 'data'
#         self.filepath = '/'.join((self.basepath, self.filename))

#     def read(self):
#         if not os.path.exists(self.filepath):
#             print(f"File {self.filepath} not available")
#             return False
        
#         with open(self.filepath, 'r') as file:
#             raw = file.readline()

#         if len(raw)>0:
#             data = json.loads(raw)
#         else:
#             data = []
#         return data

#     def write(self, item):
#         data = self.read()
#         if data:
#             data = data + item
#         else:
#             data = item
#         with open(self.filepath, "w+") as file:
#             file.write(json.dumps(data))


# class BlockchainDB(BaseDB):
#     def  __init__(self):
#         self.filename = 'blockchain'
#         super().__init__()

#     def lastBlock(self):
#         data = self.read()

#         if data:
#             return data[-1]

import sqlite3
import json
import os

class BaseDB:
    def __init__(self):
        self.basepath = 'data'
        self.filepath = '/'.join((self.basepath, self.filename))
        self.conn = sqlite3.connect(self.filepath)
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        """Create a table if it doesn't already exist"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS blockchain_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )
        ''')
        self.conn.commit()

    def read(self):
        """Read all data from the blockchain_data table"""
        self.cursor.execute('SELECT data FROM blockchain_data')
        rows = self.cursor.fetchall()

        if len(rows) > 0:
            # Return the data as a list of dictionaries (blocks)
            return [json.loads(row[0]) for row in rows]
        else:
            return []

    def write(self, item):
        """Write a new block (item) to the blockchain_data table"""
        # Convert the item to JSON before writing it to the database
        data_json = json.dumps(item)
        self.cursor.execute('INSERT INTO blockchain_data (data) VALUES (?)', (data_json,))
        self.conn.commit()

    def __del__(self):
        """Close the database connection when the object is destroyed"""
        self.conn.close()


class BlockchainDB(BaseDB):
    def  __init__(self):
        self.filename = 'blockchain.db' 
        super().__init__()

    def lastBlock(self):
        """Retrieve the last block in the blockchain"""
        data = self.read()

        if data:
            return data[-1]
        else:
            return None
    
    def read_all_blocks(self):
        """Read all blocks from the blockchain_data table"""
        self.cursor.execute('SELECT data FROM blockchain_data ORDER BY id ASC')
        rows = self.cursor.fetchall()
        if rows:
            # Return the data as a list of dictionaries (blocks)
            return [json.loads(row[0]) for row in rows]
        else:
            return []
        
    
        
class AccountDB(BaseDB):
    def __init__(self):
        self.filename = "account.db"
        super().__init__()


class NodeDB(BaseDB):
    def __init__(self):
        self.filename = "node.db"
        super().__init__()
        self._initialise_with_8888()

    def _initialise_with_8888(self):
        """Initialize the database with [8888] if it's empty"""
        # Check if any data exists in the node.db table
        self.cursor.execute('SELECT data FROM blockchain_data')
        rows = self.cursor.fetchall()

        # If the database is empty, add [8888]
        if not rows:
            self.write([8888])
