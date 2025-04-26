#!/usr/bin/env python3
import os
import sys
import shutil

# Set the project root path
PROJECT_ROOT = "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain"

# Blockchain file path
blockchain_file = os.path.join(PROJECT_ROOT, "code_node2/Blockchain/Backend/core/pos_blockchain.py")
backup_file = blockchain_file + ".backup.2025-04-11"

# Create backup with timestamp
print(f"Creating backup: {backup_file}")
shutil.copy(blockchain_file, backup_file)

# Find the original file from the backups if we can
original_backup = blockchain_file + ".backup"
if os.path.exists(original_backup):
    print(f"Using original backup from: {original_backup}")
    shutil.copy(original_backup, blockchain_file)

# Now read the file we're working with
with open(blockchain_file, 'r') as f:
    content = f.read()

# Find the insertion point - just before class Blockchain
insertion_point = content.find("class Blockchain:")
if insertion_point == -1:
    print("ERROR: Cannot find Blockchain class!")
    sys.exit(1)

# Insert the get_validator_account function
validator_function = """
def get_validator_account(validator_addr):
    \"\"\"Find a validator account using multiple lookup methods\"\"\"
    print(f"Looking up validator account: {validator_addr}")
    validator_account = None
    
    # First try with account.get_account 
    import sys
    for module_name, module in list(sys.modules.items()):
        if module_name.endswith('account') and hasattr(module, 'get_account'):
            try:
                validator_account = module.get_account(validator_addr)
                if validator_account:
                    print(f"Found validator account using {module_name}.get_account")
                    return validator_account
            except Exception as e:
                print(f"Error with {module_name}.get_account: {e}")
    
    # If that fails, try direct database access
    print("Standard lookup failed, trying direct database access")
    import os
    import re
    import sqlite3
    import json
    
    # Try to detect node ID from cwd
    node_id = 0
    cwd = os.getcwd()
    match = re.search(r'node_(\\d+)', cwd)
    if match:
        node_id = int(match.group(1))
        print(f"Detected node_id {node_id}")
    
    # Try different DB paths
    db_paths = [
        os.path.join("/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/network_data", 
                    f"node_{node_id}/account.db"),
        "account.db",
        "data/account.db",
        os.path.join(os.getcwd(), "account.db")
    ]
    
    for db_path in db_paths:
        if os.path.exists(db_path):
            try:
                print(f"Trying database path: {db_path}")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM account WHERE public_addr = ?", 
                              (validator_addr,))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    print(f"Found account in {db_path}!")
                    account_data = json.loads(row[0])
                    
                    # Create account object
                    class SimpleAccount:
                        def __init__(self):
                            self.db_path = db_path
                            
                        def save_to_db(self):
                            print("Saving validator account changes")
                            
                            # Save to the same DB we loaded from
                            updated_data = {
                                'public_addr': self.public_addr,
                                'privateKey': self.privateKey,
                                'balance': self.balance,
                                'staked': self.staked, 
                                'public_key': self.public_key.hex() 
                                    if hasattr(self, 'public_key') and 
                                       isinstance(self.public_key, bytes) 
                                    else self.public_key
                            }
                            
                            try:
                                conn = sqlite3.connect(self.db_path)
                                cursor = conn.cursor()
                                cursor.execute("UPDATE account SET value = ? WHERE public_addr = ?",
                                             (json.dumps(updated_data), self.public_addr))
                                conn.commit()
                                conn.close()
                                print(f"Account updated successfully in {self.db_path}")
                            except Exception as e:
                                print(f"Error saving account: {e}")
                    
                    validator_account = SimpleAccount()
                    
                    # Set properties from account_data
                    validator_account.public_addr = account_data.get('public_addr')
                    
                    # Convert privateKey to integer if it's stored as string
                    priv_key = account_data.get('privateKey')
                    if isinstance(priv_key, str):
                        try:
                            # Try direct conversion
                            validator_account.privateKey = int(priv_key)
                            print(f"Converted privateKey from string to int: {validator_account.privateKey}")
                        except ValueError:
                            # If it fails, maybe it's hexadecimal
                            if priv_key.startswith('0x'):
                                validator_account.privateKey = int(priv_key, 16)
                            else:
                                # Last resort - just set it and hope for the best
                                validator_account.privateKey = priv_key
                    else:
                        validator_account.privateKey = priv_key
                    
                    print(f"privateKey type: {type(validator_account.privateKey)}")
                    
                    validator_account.balance = account_data.get('balance', 0)
                    validator_account.staked = account_data.get('staked', 0)
                    
                    # Handle public key - might be hex string or bytes
                    pub_key = account_data.get('public_key')
                    if isinstance(pub_key, str):
                        validator_account.public_key = bytes.fromhex(pub_key)
                    else:
                        validator_account.public_key = pub_key
                        
                    return validator_account
            except Exception as e:
                print(f"Error accessing database {db_path}: {e}")
                
    # If we get here, we couldn't find the account
    print(f"WARNING: Could not find validator account for {validator_addr}")
    return None
"""

# Add the function before the Blockchain class
content = content[:insertion_point] + validator_function + "\n\n" + content[insertion_point:]

# Replace account.get_account calls with our function
content = content.replace("account.get_account(validator['public_addr'])", "get_validator_account(validator['public_addr'])")
content = content.replace("account.get_account(validator_addr)", "get_validator_account(validator_addr)")

# Patch sign_block method if it exists
sign_block_pattern = "def sign_block(self, block_data, private_key_int):"
sign_block_idx = content.find(sign_block_pattern)

if sign_block_idx != -1:
    # Find where to start making changes from
    sign_block_body_start = content.find(":", sign_block_idx) + 1
    
    # Find the next method (where our patch should end)
    next_def = content.find("def ", sign_block_idx + 10)
    if next_def == -1:
        next_def = len(content)  # If no more methods, go to end of file
    
    # Find indentation level
    indent = ""
    line_start = content.rfind("\n", 0, sign_block_idx) + 1
    for i in range(line_start, sign_block_idx):
        if content[i].isspace():
            indent += content[i]
        else:
            break
    
    # Create new method body with proper indentation
    new_sign_block_body = f"\n{indent}    \"\"\"Sign the block data using the validator's private key.\"\"\"\n"
    new_sign_block_body += f"{indent}    # Convert private_key_int to integer if it's a string\n"
    new_sign_block_body += f"{indent}    if isinstance(private_key_int, str):\n"
    new_sign_block_body += f"{indent}        try:\n"
    new_sign_block_body += f"{indent}            private_key_int = int(private_key_int)\n"
    new_sign_block_body += f"{indent}            print(f\"Converted private key to int in sign_block\")\n"
    new_sign_block_body += f"{indent}        except ValueError:\n"
    new_sign_block_body += f"{indent}            # Try hex conversion if it starts with 0x\n"
    new_sign_block_body += f"{indent}            if private_key_int.startswith('0x'):\n"
    new_sign_block_body += f"{indent}                private_key_int = int(private_key_int, 16)\n"
    new_sign_block_body += f"{indent}                print(f\"Converted hex private key to int in sign_block\")\n"
    new_sign_block_body += f"{indent}            else:\n"
    new_sign_block_body += f"{indent}                print(f\"ERROR: Cannot convert privateKey to int: {{private_key_int}}\")\n"
    new_sign_block_body += f"{indent}                raise ValueError(\"Private key must be an integer or convertible to integer\")\n"
    new_sign_block_body += f"{indent}    \n"
    new_sign_block_body += f"{indent}    priv_key = PrivateKey(private_key_int)\n"
    new_sign_block_body += f"{indent}    # Hash the block data\n"
    new_sign_block_body += f"{indent}    hashed_data = hashlib.sha256(block_data).digest()\n"
    new_sign_block_body += f"{indent}    # Convert to integer\n"
    new_sign_block_body += f"{indent}    z = int.from_bytes(hashed_data, 'big')\n"
    new_sign_block_body += f"{indent}    # Sign\n"
    new_sign_block_body += f"{indent}    signature_obj = priv_key.sign(z)\n"
    new_sign_block_body += f"{indent}    return signature_obj.der().hex()  # return hex string\n"
    
    # Replace the function body but keep the original function signature
    method_signature = content[sign_block_idx:sign_block_body_start]
    content_before = content[:sign_block_idx]
    content_after = content[next_def:]
    
    content = content_before + method_signature + new_sign_block_body + content_after
    print("Successfully patched sign_block method")

# Write the fixed content back to the file
with open(blockchain_file, 'w') as f:
    f.write(content)

print("Successfully fixed the blockchain code")
print("Restart your blockchain network for changes to take effect!")