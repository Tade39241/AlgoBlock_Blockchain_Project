import logging
import os
import sys
from flask import Flask, current_app, jsonify, render_template, request, redirect, url_for, session
import psutil
from Blockchain.client.sendTDC import sendTDC
from waitress import serve
from Blockchain.Backend.core.Tx import Tx
from Blockchain.Backend.core.database.db import BlockchainDB, NodeDB
from Blockchain.Backend.util.util import encode_base58,decode_base58
from Blockchain.Backend.core.network.syncManager import syncManager
from hashlib import sha256
from flask_qrcode import QRcode

# --- Add this basic configuration near the top ---
# Configure logging for this module/process
log_format = '%(message)s'
# Log INFO level messages and above to standard error
logging.basicConfig(level=logging.INFO, format=log_format, stream=sys.stderr)
# You could also configure a FileHandler here if you want logs in a separate file per process
# --- End configuration ---

# Get a logger for this module
logger = logging.getLogger('run.py')

app = Flask(__name__)
qrcode = QRcode(app)
main_prefix = b'\00'
global memoryPool
memoryPool = {}

# Globals to be set by main()
UTXOS = None
MEMPOOL = None
localHostPort = None
NODE_ID = None # Add global for Node ID

# --- Helper function to get blockchain DB instance ---
def get_blockchain_db():
    # This assumes the patched __init__ in start_node.py sets the correct path
    # If not, you might need to pass the path explicitly or read from config
    try:
        return BlockchainDB()
    except Exception as e:
        print(f"Error getting BlockchainDB instance: {e}")
        return None
    

# --- /stats Endpoint ---
@app.route('/stats')
def get_stats():
    # Initialize with default values
    height = -1 # Indicate not found initially
    mempool_size = len(MEMPOOL)
    total_transactions = 0
    last_block_time = 0
    last_block_dict = None # Keep this for holding the last valid block dictionary

    blockchain_db = get_blockchain_db()
    if not blockchain_db:
        return jsonify({"error": "Could not connect to blockchain database"}), 500

    try:
        blocks = blockchain_db.read_all_blocks() # Assumed returns List[Dict]
        logger.info(f"DEBUG: Read {len(blocks)} blocks from DB.")

        if blocks:
            # Get the last item, which should be the last block's dictionary
            last_block_item = blocks[-1]

            # --- ADJUSTED CHECK: Check if the last item IS a dictionary ---
            if isinstance(last_block_item, dict):
                last_block_dict = last_block_item # Assign the dictionary directly
                height = last_block_dict.get('Height', -1) # Get height from the last block
                last_block_time = last_block_dict.get('BlockHeader', {}).get('timestamp', 0)
            else:
                # Handle case where the last item isn't a dictionary
                height = blockchain_db.get_height() # Fallback to DB height if last block format is wrong
                last_block_time = 0
                print(f"Warning: Last block read from DB is not a dictionary: {last_block_item}")
            # --- END ADJUSTED CHECK ---

            # --- ADJUSTED LOOP: Iterate over the list of dictionaries ---
            for block_data in blocks: # Iterate directly over block dictionaries
                # Ensure block_data is actually a dictionary
                if isinstance(block_data, dict):
                    # Ensure 'Txs' exists and is a list
                    txs_list = block_data.get('Txs', [])
                    if isinstance(txs_list, list):
                        total_transactions += len(txs_list)
                    else:
                         # This case should be less likely if blocks are consistently dicts
                         print(f"Warning [/stats]: 'Txs' field is not a list in block: {block_data.get('Height', 'N/A')}")
                else:
                    # Log an error if an item in blocks isn't a dictionary
                    print(f"Warning [/stats]: Encountered non-dictionary item in blocks list: {block_data}")
            # --- END ADJUSTED LOOP ---

        else:
            # If blocks list is empty, height is 0 (or -1 depending on convention for empty chain)
             height = 0 # Or maybe -1 if genesis block isn't counted as height 0


        # System Resource Usage (remains the same)
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_info = psutil.virtual_memory()
        memory_percent = memory_info.percent
        disk_info = psutil.disk_usage('/')
        disk_percent = disk_info.percent

        stats = {
            "blockchain_height": height,
            "mempool_size": mempool_size,
            "total_transactions": total_transactions,
            "last_block_timestamp": last_block_time,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "disk_percent": disk_percent,
            "node_port": localHostPort
        }
        return jsonify(stats)

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Use the height calculated before potential error, or fallback
        stats = {
            "blockchain_height": height if height != -1 else 'Error', # Show error if height couldn't be determined
            "mempool_size": mempool_size,
            "total_transactions": 'Error',
            "last_block_timestamp": 'Error',
            "cpu_percent": 'Error',
            "memory_percent": 'Error',
            "disk_percent": 'Error',
            "node_port": localHostPort
        }
        print(f"ERROR in /stats: {str(e)}") # Log the error
        return jsonify({"error": f"An error occurred getting stats: {str(e)}", "partial_stats": stats}), 500


# --- /performance Endpoint ---
# Also needs adjustment if it assumes list[list[dict]]
@app.route('/performance')
def get_performance():
    blockchain_db = get_blockchain_db()
    if not blockchain_db:
        return jsonify({"error": "Could not connect to blockchain database"}), 500

    try:
        blocks = blockchain_db.read_all_blocks() # Assumed returns List[Dict]
        num_blocks_to_consider = 100
        recent_blocks_raw = blocks[-num_blocks_to_consider:]

        # --- ADJUSTED: Filter for dictionaries directly ---
        recent_blocks = [item for item in recent_blocks_raw if isinstance(item, dict)]
        if len(recent_blocks) != len(recent_blocks_raw):
             print(f"Warning [/performance]: Filtered out non-dictionary items from recent blocks.")
        # --- END ADJUSTED ---


        if len(recent_blocks) < 2:
            return jsonify({
                "average_block_time": None,
                "average_transactions_per_block": None,
                "estimated_tps": None,
                "message": "Not enough valid blocks to calculate performance metrics."
            })

        total_time_diff = 0
        total_transactions = 0 # Count transactions within the considered blocks
        block_count = 0 # Count valid intervals

        # --- Loop adjusted: recent_blocks is now list[dict] ---
        for i in range(1, len(recent_blocks)):
            try:
                # Access dictionaries directly now
                prev_block_data = recent_blocks[i-1]
                current_block_data = recent_blocks[i]

                # Dictionaries are already filtered, but check header/timestamp existence
                prev_timestamp = prev_block_data.get('BlockHeader', {}).get('timestamp')
                current_timestamp = current_block_data.get('BlockHeader', {}).get('timestamp')

                if prev_timestamp is not None and current_timestamp is not None and current_timestamp > prev_timestamp:
                    total_time_diff += (current_timestamp - prev_timestamp)
                    block_count += 1

                # Get transactions from the current block
                txs_list = current_block_data.get('Txs', [])
                if isinstance(txs_list, list):
                     total_transactions += len(txs_list)
                else:
                    print(f"Warning [/performance]: 'Txs' field not a list in block {current_block_data.get('Height', 'N/A')}")


            except Exception as e: # Catch broader exceptions during processing
                 print(f"Warning [/performance]: Skipping block pair due to data issue or error: {e} in block {current_block_data.get('Height', 'N/A') if 'current_block_data' in locals() else 'unknown'}")
                 continue
        # --- End adjusted loop ---

        average_block_time = total_time_diff / block_count if block_count > 0 else None
        average_transactions_per_block = total_transactions / len(recent_blocks) if recent_blocks else None
        estimated_tps = (total_transactions / total_time_diff) if total_time_diff > 0 else None

        performance = {
            "average_block_time": average_block_time,
            "average_transactions_per_block": average_transactions_per_block,
            "estimated_tps": estimated_tps,
            "blocks_considered": len(recent_blocks), # Use the length of the filtered list
            "valid_block_intervals": block_count
        }
        return jsonify(performance)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"An error occurred calculating performance: {str(e)}"}), 500


@app.route('/')
def index():
    return render_template('home.html')


@app.route('/transactions/<txid>')
@app.route('/transactions')
def transactions(txid=None):
    if txid:
        return redirect(url_for('txDetails', txid=txid))
    else:
        try:
            # --- DEBUG: Check UTXOS ---
            print(f"--- DEBUG /transactions: UTXOS size: {len(UTXOS)}", file=sys.stderr)
            # print(f"--- DEBUG /transactions: UTXOS content: {UTXOS}", file=sys.stderr) # Optional: Print content if small
            # --- End DEBUG ---

            allTxs = dict(UTXOS) # Copy the dictionary

            print(f"--- DEBUG /transactions: Copied allTxs size: {len(allTxs)}", file=sys.stderr) # Check size after copy

            return render_template('transactions.html', allTransactions=allTxs, refreshtime=10)
        except Exception as e:
            # --- FIX: Log error and return empty dict ---
            print(f"ERROR copying UTXOS in /transactions route: {e}", file=sys.stderr)
            # traceback.print_exc(file=sys.stderr) # Optional: Print full traceback
            return render_template('transactions.html', allTransactions={}, refreshtime=10) # Return empty on error

@app.route('/tx/<txid>')
def txDetails(txid):
    print(f"--- DEBUG: txDetails route called with txid: {txid}") # Add this
    blocks = read_database()
    print(f"--- DEBUG: Read {len(blocks)} blocks from DB.") # Add this
    for i, block in enumerate(blocks):
        # print(f"--- DEBUG: Checking block {i} (Height: {block.get('Height', 'N/A')})") # Optional: Check blocks
        if 'Txs' not in block:
             print(f"--- WARNING: Block {i} has no 'Txs' key.")
             continue
        for Tx in block['Txs']:
            db_txid = Tx.get('TxId') # Use .get() for safety
            if db_txid:
                # print(f"--- DEBUG: Comparing URL '{txid}' with DB '{db_txid}'") # Optional: Verbose comparison
                if db_txid == txid:
                    print(f"--- DEBUG: Match found for {txid} in block {block.get('Height', 'N/A')}") # Add this
                    return render_template('txDetails.html', Tx=Tx, block=block,encode_base58=encode_base58,
                                           bytes = bytes, sha256=sha256, main_prefix = main_prefix)
            else:
                print(f"--- WARNING: Transaction in block {i} missing 'TxId' key.")

    print(f"--- DEBUG: No match found for {txid} in any block. Returning 'Invalid Identifier'.") # Add this
    return "<h1> Invalid Identifier </h1>"


@app.route('/mempool')
def mempool():
    try:
        blocks = read_database()
        ErrorFlag = True
        while ErrorFlag:
            try:
                mempooltxs = dict(MEMPOOL)
                ErrorFlag = False
            except:
                ErrorFlag = True

        for txid in memoryPool:
            if txid not in mempooltxs:
                del memoryPool[txid]

        for Txid in mempooltxs:
            amount = 0
            TxObj = mempooltxs[Txid]
            match_found = False

            for txin in TxObj.tx_ins:
                for block in blocks:
                    for Tx in block['Txs']:
                        if Tx['TxId'] == txin.prev_tx.hex():
                            amount+= Tx['tx_outs'][txin.prev_index]['amount']
                            match_found = True
                            break
                    if match_found:
                        match_found = False
                        break
            memoryPool[TxObj.TxId] = [TxObj.to_dict(), amount/100000000, txin.prev_index]
        return render_template('mempool.html', Txs = memoryPool, refreshtime=2)

    except Exception as e:
        return render_template('mempool.html', Txs = memoryPool, refreshtime=2)

@app.route('/memTx/<txid>')
def memTxDetails(txid):
    if txid in memoryPool:
        Tx = memoryPool.get(txid)[0]
        return render_template('txDetails.html',Tx=Tx,refreshtime=2, encode_base58=encode_base58,
                               bytes=bytes,sha256=sha256, main_prefix=main_prefix ,Unconfirmed=True)
    else:
        return redirect(url_for('transactions',txid=txid))

@app.route('/search')
def search():
    identifier = request.args.get('search')
    if len(identifier) == 64:
        if identifier[:4] == "0000":
            return redirect(url_for('showBlock', BlockHeader = identifier))
        else:
            return redirect(url_for('txDetail', txid = identifier))
    else:
        return redirect(url_for('address', publicAddress = identifier))


def read_database():
    print(f"Frontend using blockchain DB path: {os.environ.get('BLOCKCHAIN_DB_PATH')}")
    ErrorFlag = True
    while ErrorFlag:
        try:
            db_path = os.environ.get("BLOCKCHAIN_DB_PATH")
            blockchain = BlockchainDB(db_path=db_path)
            blocks = blockchain.read_all_blocks()
            ErrorFlag = False
        except Exception as e:
            ErrorFlag = True
            print('Error reading database', e)
    return blocks

@app.route('/block')
def block():
    if request.args.get('BlockHeader'):
        return redirect(url_for('showBlock',BlockHeader = request.args.get('BlockHeader'), refreshtime = 10))
    else:
        blocks = read_database()
        return render_template('block.html', blocks = blocks)


@app.route('/block/<BlockHeader>')
def showBlock(BlockHeader):
    blocks = read_database()
    for block in blocks:
        if block['BlockHeader']['blockHash'] == BlockHeader:
            return render_template('blockDetails.html', block = block, main_prefix=main_prefix, encode_base58=encode_base58, sha256=sha256, bytes = bytes)
    
    return "<h1> Invalid Identifier </h1>"

@app.route('/address/<publicAddress>')
def address(publicAddress):
    if len(publicAddress) < 35 and publicAddress[:1] == "1":
        h160 = decode_base58(publicAddress)

        ErrorFlag = True
        while ErrorFlag:
            try:
                AllUtxos = dict(UTXOS)
                if AllUtxos:
                    first_key = next(iter(AllUtxos))
                    print(f"--- DEBUG Address Route: Type of first UTXO value: {type(AllUtxos[first_key])}")
                ErrorFlag = False
            except Exception as e:
                ErrorFlag = True
                print(f"Error copying UTXOS: {e}") 
        
        amount = 0
        AccountUtxos = []

        for utxo_key in AllUtxos:
            tx_out_obj = AllUtxos[utxo_key] # This is a TxOut OBJECT
            # --- ADD DEBUG PRINTS ---
            print(f"\n--- DEBUG UTXO Check ---")
            print(f"  Checking UTXO Key: {utxo_key}")
            print(f"  Target h160 (bytes): {h160}")
            is_coinbase_tx = utxo_key[0] in [tx['TxId'] for block in read_database() for tx in block.get('Txs', []) if tx.get('tx_ins') and tx['tx_ins'][0]['prev_tx'] == '0'*64] # Quick check if it's a coinbase txid
            print(f"  Is likely coinbase TX: {is_coinbase_tx}")

            if hasattr(tx_out_obj, 'script_pubkey') and tx_out_obj.script_publickey and hasattr(tx_out_obj.script_publickey, 'cmds'):
                script_cmds = tx_out_obj.script_publickey.cmds
                print(f"  Output Script Cmds: {script_cmds}")
                print(f"  Script Length: {len(script_cmds)}")
                if len(script_cmds) == 5:
                     cmd2 = script_cmds[2]
                     print(f"  Output Cmd[2]: {cmd2}")
                     print(f"  Type of Cmd[2]: {type(cmd2)}")
                     print(f"  Comparison Result (Cmd[2] == h160): {cmd2 == h160}")
                else:
                     print(f"  Script length is not 5.")
            else:
                print(f"  Output object missing script_pubkey or cmds attribute.")
            # --- END DEBUG PRINTS ---
            if tx_out_obj.script_publickey and tx_out_obj.script_publickey.cmds and len(tx_out_obj.script_publickey.cmds) == 5 and tx_out_obj.script_publickey.cmds[2] == h160:
                    amount += tx_out_obj.amount
                    utxo_info = {
                    'txid': utxo_key[0], # Get txid from the key tuple
                    'index': utxo_key[1], # Get index from the key tuple
                    'amount': tx_out_obj.amount,
                    # 'locktime': ??? # TxOut object doesn't have locktime, Tx object does. Need to fetch Tx if needed.
                    }
                    AccountUtxos.append(utxo_info)
        return render_template('address.html', Txs = AccountUtxos, amount = amount,
                            encode_base58=encode_base58, bytes=bytes, sha256=sha256, main_prefix=main_prefix,
                            publicAddress=publicAddress,qrcode = qrcode)
    else:
        return "<h1> Invalid Identifier </h1>"
    


@app.route('/wallet', methods=['GET', 'POST'])
def wallet():
    print(f"[DEBUG][FLASK] request.form: {request.form} request.data: {request.data}")
    global MEMPOOL, UTXOS
    message = ''
    if request.method == 'POST':
        reload_utxos_from_chain()
        if request.is_json:
            data = request.get_json()
            print(f"[DEBUG][WALLET/FLASK] Parsed JSON data: {data}")
            from_addy = data.get("fromAddress")
            to_addy = data.get("toAddress")
            amount = data.get("Amount", None)
            if amount is not None:
                try:
                    amount = int(amount)
                except Exception:
                    amount = None
            sendCoin = sendTDC(from_addy, to_addy, amount, UTXOS)
            TxObj = sendCoin.prepTransaction()
            if not from_addy or not to_addy or amount is None:
                return jsonify({"error": "Missing required fields."}), 400
            if not TxObj:
                return jsonify({"error": "Insufficient balance"}), 400
            script_pubkey = sendCoin.script_public_key(from_addy)
            verified = all(TxObj.verify_input(i, script_pubkey) for i in range(len(TxObj.tx_ins)))
            if verified:
                MEMPOOL[TxObj.TxId] = TxObj
                logging.info(f"SUCCESS: Transaction {TxObj.TxId} from {from_addy} to {to_addy} for {amount} satoshis added to mempool.")
                broadcastTx(TxObj)
                return jsonify({"success": True, "txid": TxObj.TxId}), 200
            else:
                return jsonify({"error": "Transaction verification failed."}), 400
        else:
            from_addy = request.form.get("fromAddress")
            to_addy = request.form.get("toAddress")
            amount = request.form.get("Amount", type=float)
            # print(f"[DEBUG][WALLET] Extracted: from={from_addy}, to={to_addy}, amount={amount}")
            sendCoin = sendTDC(from_addy, to_addy, amount, UTXOS)
            TxObj = sendCoin.prepTransaction()
            # print(f"[DEBUG][WALLET] sendTDC/prepTransaction result: TxObj={TxObj}")
            if not from_addy or not to_addy or amount is None:
                # print(f"[DEBUG][WALLET] Missing field(s): from={from_addy}, to={to_addy}, amount={amount}")
                message = 'Please fill out all the fields.'
                return render_template("wallet.html", message=message)
            if not TxObj:
                # print(f"[DEBUG][WALLET] Transaction creation failed (TxObj is None).")
                message = 'Insufficient balance'
            else:
                script_pubkey = sendCoin.script_public_key(from_addy)
                # print(f"[DEBUG][WALLET] script_pubkey for {from_addy}: {script_pubkey}")
                verified = True
                for index in range(len(TxObj.tx_ins)):
                    if not TxObj.verify_input(index, script_pubkey):
                        verified = False
                        break
                if verified:
                    # print(f"[DEBUG][WALLET] Transaction verified. Adding to MEMPOOL.")
                    # update_utxo_set(TxObj, UTXOS)
                    MEMPOOL[TxObj.TxId] = TxObj
                    logging.info(f"SUCCESS: Transaction {TxObj.TxId} from {from_addy} to {to_addy} for {amount} satoshis added to mempool.")
                    # print(f"[DEBUG][WALLET] Added Tx {TxObj.TxId} to MEMPOOL. Keys now: {list(MEMPOOL.keys())}")
                    message = f"Transaction added to mempool: {TxObj.TxId}"

                    broadcastTx(TxObj)
                else:
                    message = "Transaction verification failed."
            return render_template("wallet.html", message=message)
    # print(f"[DEBUG][WALLET] MEMPOOL keys after POST: {list(MEMPOOL.keys())}")
    # print(f"[DEBUG][WALLET] UTXOS keys after POST: {list(UTXOS.keys())}")
    # print(f"[DEBUG][WALLET] TxObj dict: {TxObj.to_dict() if hasattr(TxObj, 'to_dict') else str(TxObj)}")
    return render_template("wallet.html", message=message)

# @app.route('/wallet', methods=['GET', 'POST'])
# def wallet():
#     message = ''
#     default_sender_address = current_app.config.get('DEFAULT_ADDRESS', '')
#     if request.method == 'POST':
    
#         from_addy = request.form.get("fromAddress")
#         if not from_addy:
#             from_addy = default_sender_address
#             print(f"Wallet: No 'fromAddress' provided, using default: {from_addy}")

#         to_addy = request.form.get("toAddress")

#         amount = request.form.get("Amount", type=int)
        
#         sendCoin = sendTDC(from_addy, to_addy, amount,UTXOS)
#         TxObj = sendCoin.prepTransaction()

#         if not from_addy or not to_addy or amount is None:
#             message = 'Please fill out all the fields.'

#         script_pubkey = sendCoin.script_public_key(from_addy)
#         verified = True

#         if not TxObj:
#             message = 'Insufficient balance'

#         if isinstance(TxObj, Tx):
#             for index, tx in enumerate(TxObj.tx_ins):
#                 if not TxObj.verify_input(index, script_pubkey):
#                     verified = False
            
#             if verified:
#                 MEMPOOL[TxObj.TxId] = TxObj
#                 print(f"Transaction added to mem pool {TxObj.TxId}")
#                 broadcastTx(TxObj)
#                 message = 'Transaction added to mem pool'

#     # Always return the template
#     return render_template("wallet.html", message=message)

def broadcastTx(TxObj):
    global NODE_ID # Access global
    global localHostPort # Access global
    if NODE_ID is None or localHostPort is None:
         print("[BroadcastTx] NODE_ID or localHostPort not set. Cannot broadcast.")
         return
    try:
        # node = NodeDB()
        node = NodeDB(node_id=NODE_ID) # NEW
        portList = node.read_nodes()

        serialized_tx = TxObj.serialise()
        print(f"DEBUG: Broadcasting Serialized Tx: {serialized_tx.hex()}")
        print(f"DEBUG (Sender): TxId: {TxObj.TxId}")
        
        for port in portList:
            # Don't broadcast to self
            if localHostPort != port:
                # Assuming peers are on localhost, adjust if necessary
                target_host = '127.0.0.1' 
                target_port = port

                sync = syncManager(target_host, target_port, MemoryPool=MEMPOOL, node_id=NODE_ID) 
                try:
                    sync.publishTx(TxObj,target_host, target_port)

                except Exception as err:
                    print(f"Error broadcasting Tx to {target_host}:{target_port}: {err}") 
                
    except Exception as err:
       print(f"Error during broadcast setup: {err}")


def reload_utxos_from_chain():
    global UTXOS, BLOCKCHAIN_PROXY, SHARED_LOCK # Need access to the global proxies and lock
    if BLOCKCHAIN_PROXY is None:
        print("[Frontend] Error: Blockchain proxy not available for reloading UTXOs.")
        return False # Indicate failure
    if SHARED_LOCK is None:
         print("[Frontend] Error: Shared lock not available for reloading UTXOs.")
         return False

    try:
        # --- DO NOT CALL buildUTXOS() here ---
        # --- Just GET the current set from the Blockchain process ---
        print("[Frontend] Getting latest UTXO set from Blockchain process...")
        # This call goes to the Blockchain process via the manager
        utxos_from_proxy = BLOCKCHAIN_PROXY.get_utxos()
        print(f"[Frontend] Received UTXO set proxy/data type: {type(utxos_from_proxy)}")

        # Update the frontend's shared UTXO dictionary proxy
        if hasattr(UTXOS, 'clear') and hasattr(UTXOS, 'update') and isinstance(utxos_from_proxy, dict):
             print("[Frontend] Acquiring lock to update shared UTXO dict...")
             with SHARED_LOCK: # Protect write access to the shared dict
                 UTXOS.clear()
                 UTXOS.update(utxos_from_proxy) # Update the shared dict
             print(f"[Frontend] Shared UTXO dict updated (Size: {len(UTXOS)}). Lock released.")
             return True
        else:
             # Handle cases where UTXOS isn't a manager dict or proxy didn't return a dict
             print(f"[Frontend] Warning: Cannot update global UTXOS. Type: {type(UTXOS)}, Received type: {type(utxos_from_proxy)}")
             # Fallback: Maybe assign locally if not shared? Depends on how UTXOS is used.
             # UTXOS = utxos_from_proxy # Assign if UTXOS is just a local global
             return False

    except AttributeError as ae:
        print(f"[Frontend] Error reloading UTXOs via proxy (AttributeError): {ae}. Is 'get_utxos' exposed?")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"[Frontend] Error reloading UTXOs via proxy: {e}")
        import traceback
        traceback.print_exc()
        return False


# def reload_utxos_from_chain():
#     global UTXOS
#     from Blockchain.Backend.core.blockchain import Blockchain
#     blockchain = Blockchain(UTXOS, MEMPOOL, None, None, localHostPort, "127.0.0.1")
#     blockchain.buildUTXOS()
#     UTXOS = blockchain.get_utxos()
#     print("[Frontend] UTXO set reloaded from blockchain.")


def main(utxos, mem_pool,port, localPort, blockchain_proxy, shared_state_lock,node_id, default_addr):
    global UTXOS, MEMPOOL, localHostPort,SHARED_LOCK,BLOCKCHAIN_PROXY
    UTXOS = utxos
    MEMPOOL = mem_pool
    SHARED_LOCK = shared_state_lock        # Assign the shared lock
    BLOCKCHAIN_PROXY = blockchain_proxy # Assign the blockchain proxy

    localHostPort = localPort
    NODE_ID = node_id # Store node_id
    # Store the default address in Flask app config
    app.config['DEFAULT_ADDRESS'] = default_addr

    print(f"[Flask App Node {NODE_ID}] Starting on port {port}...")
    # app.run(host='127.0.0.1',port=port, debug=True, use_reloader=False)
    serve(app, host='127.0.0.1', port=port,threads=8) 
