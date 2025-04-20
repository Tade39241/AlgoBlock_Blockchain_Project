"""
Standalone Blockchain Metrics Server (Fixed Version)
"""

import http.server
import json
import time
import psutil
import os
import sys
import sqlite3
from pathlib import Path
import threading
from urllib.parse import urlparse, parse_qs

# Set your project root
PROJECT_ROOT = "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain"
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# Configure ports for metrics server
PORT = 8080  # Changed to avoid conflicts with blockchain network
NODE_PATHS = [
    os.path.join(PROJECT_ROOT, "network_data", "node_0"),
    os.path.join(PROJECT_ROOT, "network_data", "node_1"),
    os.path.join(PROJECT_ROOT, "network_data", "node_2")
]

# Cache for metrics data
metrics_cache = {
    "last_updated": 0,
    "stats": {},
    "blocks": [],
    "mempool": [],
    "performance": {}
}

# Lock for thread safety
cache_lock = threading.Lock()

def read_blockchain_db(node_dir):
    """Read blockchain data from DB"""
    try:
        blockchain_db_path = os.path.join(node_dir, "blockchain.db")
        if not os.path.exists(blockchain_db_path):
            print(f"Database file not found: {blockchain_db_path}")
            return []
            
        conn = sqlite3.connect(blockchain_db_path)
        cursor = conn.cursor()
        
        # First, check the schema to see what columns are available
        try:
            cursor.execute("PRAGMA table_info(blocks)")
            columns = [col[1] for col in cursor.fetchall()]
            print(f"Available columns in blockchain table: {columns}")
            
            # Adapt query based on available columns
            if 'value' in columns:
                cursor.execute("SELECT value FROM blocks")
            else:
                # Try alternative column names or get all columns
                cursor.execute("SELECT * FROM blocks")
                
            rows = cursor.fetchall()
            conn.close()
            
            blocks = []
            for row in rows:
                try:
                    # Adapt to your database schema by using the right column
                    # If we selected all columns, the JSON data might be in any column
                    for cell in row:
                        if isinstance(cell, str) and (cell.startswith('{') or cell.startswith('[')):
                            try:
                                block_data = json.loads(cell)
                                blocks.append(block_data)
                                break
                            except:
                                pass
                except Exception as e:
                    print(f"Failed to parse block data: {str(e)}")
            
            return blocks
        except Exception as e:
            print(f"Error examining schema: {e}")
            return []
            
    except Exception as e:
        print(f"Error reading blockchain DB: {e}")
        return []

def get_blockchain_height(node_dir):
    """Get just the blockchain height without loading all data"""
    try:
        blockchain_db_path = os.path.join(node_dir, "blockchain.db")
        if not os.path.exists(blockchain_db_path):
            return 0
            
        conn = sqlite3.connect(blockchain_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM blocks")
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else 0
    except Exception as e:
        print(f"Error getting blockchain height: {e}")
        return 0

def read_mempool_data(node_dir):
    """Read mempool transactions (placeholder)"""
    # This would need custom implementation based on how your mempool is stored
    # For now, returning empty list
    return []

def update_metrics_cache():
    """Update the metrics cache with latest data"""
    global metrics_cache
    
    # Only update every 5 seconds at most
    current_time = time.time()
    with cache_lock:
        if current_time - metrics_cache["last_updated"] < 5:
            return
    
    # Use first node as primary data source
    node_dir = NODE_PATHS[0]
    
    # Get blockchain height (lightweight query)
    height = get_blockchain_height(node_dir)
    
    # Get basic stats that don't require full blockchain load
    stats = {
        "timestamp": current_time,
        "height": height,
        "node_count": len(NODE_PATHS),
        "cpu_usage": psutil.cpu_percent(),
        "memory_usage": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage('/').percent
    }
    
    # Add mempool size if available
    mempool = read_mempool_data(node_dir)
    stats["mempool_size"] = len(mempool)
    
    # Performance metrics (simplified)
    performance = {
        "avg_block_time_seconds": 0,
        "avg_tx_per_block": 0,
        "transactions_per_second": 0,
        "recent_block_count": 0
    }
    
    # Update cache with lock
    with cache_lock:
        metrics_cache = {
            "last_updated": current_time,
            "stats": stats,
            "performance": performance
        }
    
    # For full blockchain data, we load asynchronously to avoid blocking
    threading.Thread(target=load_blockchain_data, args=(node_dir,)).start()

def load_blockchain_data(node_dir):
    """Load blockchain data asynchronously"""
    try:
        global metrics_cache
        
        # Load full blockchain data (might be slow)
        blocks = read_blockchain_db(node_dir)
        
        # Extract recent blocks (last hour)
        current_time = time.time()
        recent_blocks = []
        
        for block in blocks:
            if isinstance(block, list) and len(block) > 0 and isinstance(block[0], dict):
                block_header = block[0].get('BlockHeader', {})
                timestamp = block_header.get('timestamp', 0)
                if timestamp > current_time - 3600:
                    recent_blocks.append(block)
            elif isinstance(block, dict):
                block_header = block.get('BlockHeader', {})
                timestamp = block_header.get('timestamp', 0)
                if timestamp > current_time - 3600:
                    recent_blocks.append([block])
        
        # Calculate performance metrics
        performance = calculate_performance_metrics(recent_blocks)
        
        # Update the stats with transaction count
        stats = metrics_cache["stats"].copy()
        total_tx_count = sum(block[0].get('TxCount', 0) for block in blocks if isinstance(block, list) and len(block) > 0)
        stats["total_tx_count"] = total_tx_count
        
        # Update metrics cache with full data
        with cache_lock:
            metrics_cache["blocks"] = blocks[:10]  # Just store the most recent blocks
            metrics_cache["performance"] = performance
            metrics_cache["stats"] = stats
    except Exception as e:
        print(f"Error loading blockchain data: {e}")

def calculate_performance_metrics(blocks):
    """Calculate blockchain performance metrics"""
    try:
        performance = {
            "avg_block_time_seconds": 0,
            "avg_tx_per_block": 0,
            "transactions_per_second": 0,
            "recent_block_count": len(blocks)
        }
        
        if len(blocks) < 2:
            return performance
        
        # Calculate transactions per block
        tx_counts = []
        for block in blocks:
            if isinstance(block, list) and len(block) > 0:
                tx_counts.append(block[0].get('TxCount', 0))
        
        performance["avg_tx_per_block"] = sum(tx_counts) / len(tx_counts) if tx_counts else 0
        
        # Calculate block times
        block_times = []
        for i in range(1, len(blocks)):
            prev_time = blocks[i-1][0].get('BlockHeader', {}).get('timestamp', 0)
            curr_time = blocks[i][0].get('BlockHeader', {}).get('timestamp', 0)
            if prev_time > 0 and curr_time > prev_time:
                block_times.append(curr_time - prev_time)
        
        if block_times:
            performance["avg_block_time_seconds"] = sum(block_times) / len(block_times)
            performance["transactions_per_second"] = performance["avg_tx_per_block"] / performance["avg_block_time_seconds"] if performance["avg_block_time_seconds"] > 0 else 0
        
        return performance
    except Exception as e:
        print(f"Error calculating performance metrics: {e}")
        return {
            "avg_block_time_seconds": 0,
            "avg_tx_per_block": 0,
            "transactions_per_second": 0,
            "recent_block_count": 0,
            "error": str(e)
        }

class MetricsHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for blockchain metrics"""
    
    def do_GET(self):
        """Handle GET requests"""
        # Parse URL path
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        # Ignore favicon requests
        if path == '/favicon.ico':
            self.send_response(404)
            self.end_headers()
            return
        
        # Update metrics cache
        update_metrics_cache()
        
        # Route to appropriate handler
        if path == '/api/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "online",
                "timestamp": time.time()
            }).encode())
            
        elif path == '/api/stats':
            with cache_lock:
                stats = metrics_cache["stats"]
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode())
            
        elif path == '/api/blocks':
            with cache_lock:
                blocks = metrics_cache.get("blocks", [])
            
            # Parse query parameters
            query = parse_qs(parsed_url.query)
            count = int(query.get('count', [10])[0])
            start = int(query.get('start', [0])[0])
            
            # Calculate start and end indices
            end = min(start + count, len(blocks))
            
            # Extract block data
            block_data = []
            for i in range(start, end):
                if i < len(blocks):
                    block = blocks[i][0] if isinstance(blocks[i], list) and len(blocks[i]) > 0 else blocks[i]
                    block_data.append({
                        "index": block.get('Height', i),
                        "timestamp": block.get('BlockHeader', {}).get('timestamp', 0),
                        "hash": block.get('BlockHeader', {}).get('blockHash', ""),
                        "previous_hash": block.get('BlockHeader', {}).get('prevBlockHash', ""),
                        "tx_count": block.get('TxCount', 0)
                    })
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "chain_length": metrics_cache["stats"].get("height", 0),
                "blocks": block_data
            }).encode())
            
        elif path == '/api/performance':
            with cache_lock:
                performance = metrics_cache["performance"]
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(performance).encode())
            
        else:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Not Found",
                "message": f"The requested path {path} was not found"
            }).encode())
    
    def log_message(self, format, *args):
        """Custom log message format"""
        sys.stderr.write(f"[metrics_server] {self.address_string()} - {format % args}\n")

def run_server():
    """Run the metrics server"""
    server_address = ('', PORT)
    httpd = http.server.ThreadingHTTPServer(server_address, MetricsHandler)
    print(f"Starting metrics server on port {PORT}...")
    print(f"Blockchain metrics API available at:")
    print(f"  - http://localhost:{PORT}/api/health")
    print(f"  - http://localhost:{PORT}/api/stats")
    print(f"  - http://localhost:{PORT}/api/blocks")
    print(f"  - http://localhost:{PORT}/api/performance")
    print(f"Using blockchain data from: {NODE_PATHS[0]}")
    httpd.serve_forever()

if __name__ == "__main__":
    # Verify node directories exist
    for path in NODE_PATHS:
        if not os.path.exists(path):
            print(f"Warning: Node directory doesn't exist: {path}")
    
    run_server()