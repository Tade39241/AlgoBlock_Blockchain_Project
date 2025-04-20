import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
NETWORK_DATA_DIR = os.path.join(PROJECT_ROOT, "network_data")
DB_FILES = ["account.db", "blockchain.db", "node.db"]

def delete_db_files_in_node(node_dir):
    data_dir = os.path.join(node_dir, "data")
    if not os.path.exists(data_dir):
        return
    for db_file in DB_FILES:
        db_path = os.path.join(data_dir, db_file)
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
                print(f"Deleted: {db_path}")
            except Exception as e:
                print(f"Failed to delete {db_path}: {e}")

def main():
    if not os.path.exists(NETWORK_DATA_DIR):
        print(f"Network data directory not found: {NETWORK_DATA_DIR}")
        return

    for item in os.listdir(NETWORK_DATA_DIR):
        if item.startswith("node_") or item == "validator_node":
            node_dir = os.path.join(NETWORK_DATA_DIR, item)
            if os.path.isdir(node_dir):
                delete_db_files_in_node(node_dir)

if __name__ == "__main__":
    main()
    