#!/usr/bin/env python3
"""
Reset Account and Blockchain State for PoS Blockchain Testing

This script will:
  - Backup your account and blockchain databases (if they exist)
  - Recreate the account table with the hardcoded test ACCOUNTS.
  - Optionally, back up and reset the blockchain state.
  
Usage:
  python reset_accounts.py --reset-blockchain   (to reset blockchain state too)
"""

import os
import re
import sys
import sqlite3
import json
import time
import logging
import argparse

from datetime import datetime

# Configure logging to both console and a file.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("reset_accounts.log")
    ]
)
logger = logging.getLogger(__name__)

# Set your project root
PROJECT_ROOT = "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain"

# Hardcoded test accounts
ACCOUNTS = {
    "1DPPqS7kQNQMcn28du4sYJe8YKLUH8Jrig": {
        "privateKey": 96535626569238604192129746772702330856431841702880282095447645155889990991526, 
        "public_addr": "1DPPqS7kQNQMcn28du4sYJe8YKLUH8Jrig", 
        "public_key": "0248c103d04cc26840fa000d9614301fa5aee9d79b3a972e61c0712367658530b4", 
        # Multiply coin amounts by 100,000,000
        "staked": 100 * 100000000,         # becomes 10000000000
        "unspent": 0,            
        "locked_until": 0, 
        "staking_history": "[]"
    },
    "14yikjhubj1sepvqsvzpRv4H6LhMN43XGD": {
        "privateKey": 101116694282830344663754055609096743199644277746685645606199809457638491163865, 
        "public_addr": "14yikjhubj1sepvqsvzpRv4H6LhMN43XGD", 
        "public_key": "0387c964aa67e33f0b93d3221b1bdfce382746cc7772e7497ca2677826f58d901d", 
        "staked": 100 * 100000000,
        "unspent": 0, 
        "locked_until": 0, 
        "staking_history": "[]"
    },
    "1Lu9SwPPo7DJYrMVrZnkDXVw5y4aEeF1kz": {
        "privateKey": 46707185248865296345366463593339102785859545093537333336358754291775493830931, 
        "public_addr": "1Lu9SwPPo7DJYrMVrZnkDXVw5y4aEeF1kz", 
        "public_key": "035b605b121b0382b340dd55bb960bd73c19bb5b484d61837b41beb29b1e8341b1", 
        "staked": 100 * 100000000,
        "unspent": 0, 
        "locked_until": 0, 
        "staking_history": "[]"
    }
}


def backup_file(file_path):
    """Rename file to include backup timestamp."""
    backup_path = f"{file_path}.bak.{int(time.time())}"
    try:
        os.rename(file_path, backup_path)
        logger.info(f"Backed up {file_path} -> {backup_path}")
    except Exception as e:
        logger.warning(f"Could not back up {file_path}: {e}")


def reset_account_db(node_dir):
    """
    Reset the account database for a node.
      - Look for the account database inside the node's "data" folder.
      - If the "data" folder does not exist, create it.
      - Back up the existing account database if it exists.
      - Re-create the account table and insert hardcoded ACCOUNTS.
    """
    # Ensure we operate on the data/ subdirectory
    data_dir = os.path.join(node_dir, "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        logger.info(f"Created data directory: {data_dir}")
    
    account_db_path = os.path.join(data_dir, "account.db")
    logger.info(f"Resetting account database for node directory: {data_dir}")

    if os.path.exists(account_db_path):
        backup_file(account_db_path)

    try:
        conn = sqlite3.connect(account_db_path)
        cursor = conn.cursor()
        # DROP any legacy tables that used 'data' or plural names
        cursor.execute("DROP TABLE IF EXISTS accounts")
        cursor.execute("DROP TABLE IF EXISTS account")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account (
                public_addr TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        # Clear table if it exists.
        cursor.execute("DELETE FROM account")
        for addr, account_data in ACCOUNTS.items():
            cursor.execute("INSERT INTO account (public_addr, value) VALUES (?, ?)",
                           (addr, json.dumps(account_data)))
        conn.commit()
        conn.close()
        logger.info(f"✅ Successfully reset account database: {account_db_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Error resetting account database at {account_db_path}: {e}")
        return False


def reset_blockchain_state(node_dir):
    """
    Back up and reset the blockchain database (blockchain.db) for a node.
    Looks inside the node's "data" subdirectory, backs up any existing file,
    and then creates the table "blocks" if it doesn't exist.
    """
    import sqlite3  # Ensure sqlite3 is imported
    data_dir = os.path.join(node_dir, "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        logger.info(f"Created data directory: {data_dir}")
    blockchain_db_path = os.path.join(data_dir, "blockchain.db")
    if os.path.exists(blockchain_db_path):
        backup_file(blockchain_db_path)
    else:
        logger.info(f"No blockchain database to back up in {data_dir}")
    try:
        conn = sqlite3.connect(blockchain_db_path)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS blocks")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        logger.info(f"Created blocks table in {blockchain_db_path}")
    except Exception as e:
        logger.error(f"Error creating blocks table in {blockchain_db_path}: {e}")

def reset_node_db(node_dir):
    """
    Reset the node database for a node:
      - Backup node.db
      - (Re)create the nodes table
    """
    data_dir = os.path.join(node_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    node_db_path = os.path.join(data_dir, "node.db")
    if os.path.exists(node_db_path):
        backup_file(node_db_path)
    logger.info(f"Resetting node database: {node_db_path}")

    try:
        conn = sqlite3.connect(node_db_path)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS nodes")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                port INTEGER PRIMARY KEY
            )
        ''')
        cursor.execute("DELETE FROM nodes")
        # populate ports based on node_* folders
        for nd in find_node_dirs(PROJECT_ROOT):
            m = re.match(r'.*node_(\d+)$', nd)
            if m:
                port = 9000 + int(m.group(1))
                cursor.execute("INSERT OR IGNORE INTO nodes (port) VALUES (?)", (port,))
        conn.commit()
        conn.close()
        logger.info(f"✅ Node DB populated with ports.")
        return True
    except Exception as e:
        logger.error(f"❌ Error resetting node DB: {e}")
        return False


def find_node_dirs(root_dir):
    """
    Scan the network_data folder for subdirectories that are either
    node directories (starting with 'node_') or the validator node directory.
    """
    node_dirs = []
    network_dir = os.path.join(root_dir, "network_data")
    if not os.path.exists(network_dir):
        logger.error(f"Network data folder not found: {network_dir}")
        return node_dirs
    for item in os.listdir(network_dir):
        if item.startswith("node_") or item == "validator_node":
            full_path = os.path.join(network_dir, item)
            if os.path.isdir(full_path):
                node_dirs.append(full_path)
    return sorted(node_dirs)


def reset_all_nodes(reset_blockchain=False):
    """
    Reset node.db, account.db (and optionally blockchain.db) for all nodes.
    """
    node_dirs = find_node_dirs(PROJECT_ROOT)
    if not node_dirs:
        logger.error("No node directories found to reset.")
        return

    success = 0
    for nd in node_dirs:
        logger.info(f"\n--- Resetting databases for {nd} ---")
        if reset_node_db(nd):
            success += 1
        if reset_account_db(nd):
            success += 1
        if reset_blockchain:
            reset_blockchain_state(nd)

    total = len(node_dirs) * (2 + int(reset_blockchain))
    logger.info(f"\nReset {success}/{total} databases across {len(node_dirs)} nodes.")


def main():
    parser = argparse.ArgumentParser(description="Reset PoS Blockchain databases for testing.")
    parser.add_argument("--reset-blockchain", action="store_true",
                        help="Also back up/reset blockchain state (blockchain.db).")
    args = parser.parse_args()

    logger.info("Starting PoS Blockchain Reset Script")
    reset_all_nodes(reset_blockchain=args.reset_blockchain)
    logger.info("Database reset complete!")
    logger.info("IMPORTANT: Remember to restart your blockchain nodes for changes to take effect.")


if __name__ == "__main__":
    main()