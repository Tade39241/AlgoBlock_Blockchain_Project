import logging
import os
import sys
from flask import Flask, current_app, jsonify, render_template, request, redirect, url_for, session
from Blockchain.client.sendTDC import sendTDC
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
    global UTXOS
    from Blockchain.Backend.core.blockchain import Blockchain
    blockchain = Blockchain(UTXOS, MEMPOOL, None, None, localHostPort, "127.0.0.1")
    blockchain.buildUTXOS()
    UTXOS = blockchain.get_utxos()
    print("[Frontend] UTXO set reloaded from blockchain.")


def main(utxos, mem_pool,port, localPort, node_id, default_addr):
    global UTXOS, MEMPOOL, localHostPort, NODE_ID # Declare globals
    UTXOS = utxos
    MEMPOOL = mem_pool
    localHostPort = localPort
    NODE_ID = node_id # Store node_id
    # Store the default address in Flask app config
    app.config['DEFAULT_ADDRESS'] = default_addr

    print(f"[Flask App Node {NODE_ID}] Starting on port {port}...")
    app.run(host='127.0.0.1',port=port, debug=True, use_reloader=False)
