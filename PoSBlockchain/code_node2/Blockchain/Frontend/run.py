import sys
import os

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

sys.path.append('/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain/code_node2')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
# Set log file path to network_data/transaction.log at project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
log_file_path = os.path.join(project_root, "network_data", "transaction.log")
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
file_handler = logging.FileHandler(log_file_path, mode='w')
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
file_handler.setFormatter(formatter)
logging.getLogger().addHandler(file_handler)
logging.basicConfig(level=logging.INFO)  # At the top of your file (if not already set)

# Import jsonify for API responses and psutil for system stats
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import psutil # Make sure psutil is installed: pip install psutil

from Blockchain.client.sendTDC import sendTDC
from Blockchain.Backend.core.tx import Tx, TxIn, TxOut, ZERO_HASH
from Blockchain.Backend.core.database.db import BlockchainDB, NodeDB, AccountDB
from Blockchain.Backend.util.util import encode_base58,decode_base58
from Blockchain.Backend.core.network.syncManager import syncManager
from Blockchain.client.account import account
from Blockchain.client.sendTDC import update_utxo_set
from Blockchain.Backend.util.util import decode_base58
from Blockchain.Backend.core.script import Script
from hashlib import sha256
from flask_qrcode import QRcode
import time
import json

app = Flask(__name__)
qrcode = QRcode(app)

main_prefix = b'\00'
global memoryPool, UTXOS,MEMPOOL, localHostPort
memoryPool = {}
UTXOS = {} # Initialize UTXOS
MEMPOOL = {} # Initialize MEMPOOL
localHostPort = 0 # Initialize localHostPort

# --- Helper function to get blockchain DB instance ---
def get_blockchain_db():
    # This assumes the patched __init__ in start_node.py sets the correct path
    # If not, you might need to pass the path explicitly or read from config
    try:
        # Use the AccountDB path logic as a reference if needed
        # config = configparser.ConfigParser()
        # config.read('config.ini') # Assuming config.ini is in the CWD
        # db_path = os.path.join(os.getcwd(), "blockchain.db") # Adjust if needed
        return BlockchainDB()
    except Exception as e:
        print(f"Error getting BlockchainDB instance: {e}")
        return None
    

# --- /stats Endpoint ---
@app.route('/stats')
def get_stats():
    blockchain_db = get_blockchain_db()
    if not blockchain_db:
        return jsonify({"error": "Could not connect to blockchain database"}), 500

    try:
        # Blockchain Height
        height = blockchain_db.get_height()

        # Mempool Size
        mempool_size = len(MEMPOOL)

        # Total Transactions (Approximate by summing tx in blocks)
        total_transactions = 0
        last_block_time = 0
        blocks = blockchain_db.read_all_blocks() # Read blocks once
        if blocks:
            last_block_time = blocks[-1][0].get('BlockHeader', {}).get('timestamp', 0)
            for block_data, _ in blocks: # Iterate through block data only
                 # Ensure 'Txs' exists and is a list
                 txs_list = block_data.get('Txs', [])
                 if isinstance(txs_list, list):
                      total_transactions += len(txs_list)


        # System Resource Usage
        cpu_percent = psutil.cpu_percent(interval=0.1) # Short interval for responsiveness
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
            "node_port": localHostPort # Include the node's network port
        }
        return jsonify(stats)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# --- /performance Endpoint ---
@app.route('/performance')
def get_performance():
    blockchain_db = get_blockchain_db()
    if not blockchain_db:
        return jsonify({"error": "Could not connect to blockchain database"}), 500

    try:
        blocks = blockchain_db.read_all_blocks()
        num_blocks_to_consider = 100 # Calculate metrics over the last N blocks
        recent_blocks = blocks[-num_blocks_to_consider:]

        if len(recent_blocks) < 2:
            return jsonify({
                "average_block_time": None,
                "average_transactions_per_block": None,
                "estimated_tps": None,
                "message": "Not enough blocks to calculate performance metrics."
            })

        total_time_diff = 0
        total_transactions = 0
        block_count = 0

        for i in range(1, len(recent_blocks)):
            try:
                prev_block_data = recent_blocks[i-1][0]
                current_block_data = recent_blocks[i][0]

                prev_timestamp = prev_block_data.get('BlockHeader', {}).get('timestamp')
                current_timestamp = current_block_data.get('BlockHeader', {}).get('timestamp')

                if prev_timestamp is not None and current_timestamp is not None and current_timestamp > prev_timestamp:
                    total_time_diff += (current_timestamp - prev_timestamp)
                    block_count += 1 # Only count blocks where time diff is valid

                # Count transactions in the current block
                txs_list = current_block_data.get('Txs', [])
                if isinstance(txs_list, list):
                     total_transactions += len(txs_list)

            except (KeyError, TypeError, IndexError) as e:
                 print(f"Warning: Skipping block pair due to data issue: {e}")
                 continue # Skip this block pair if data is missing/malformed


        average_block_time = total_time_diff / block_count if block_count > 0 else None
        average_transactions_per_block = total_transactions / len(recent_blocks) if recent_blocks else None # Avg over all considered blocks
        estimated_tps = (total_transactions / total_time_diff) if total_time_diff > 0 else None

        performance = {
            "average_block_time": average_block_time,
            "average_transactions_per_block": average_transactions_per_block,
            "estimated_tps": estimated_tps,
            "blocks_considered": len(recent_blocks),
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
        ErrorFlag = True
        while ErrorFlag:
            try:
                allTxs = dict(UTXOS)
                ErrorFlag = False
                return render_template('transactions.html', allTransactions=allTxs, refreshtime=10)
            except:
                ErrorFlag = True
                return render_template('transactions.html', allTransactions={}, refreshtime=10)

import json

@app.route('/tx/<txid>')
def txDetails(txid):
    blocks = read_database()
    for block in blocks:
        for Tx in block[0]['Txs']:
            if Tx['TxId'] == txid:
                # Precompute the serialized transaction size.
                try:
                    # Here we serialize the transaction dictionary as JSON.
                    tx_serialised = json.dumps(Tx)
                    tx_size = len(tx_serialised)
                except Exception as e:
                    tx_size = "Unknown"
                    print(f"Error serializing transaction: {e}")
                return render_template('txDetails.html', Tx=Tx, block=block,
                                       encode_base58=encode_base58,
                                       bytes=bytes, sha256=sha256, main_prefix=main_prefix,
                                       tx_size=tx_size)
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
                    for Tx in block[0]['Txs']:
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
            return redirect(url_for('txDetails', txid = identifier))
    else:
        return redirect(url_for('address', publicAddress = identifier))

def read_database():
    blockchain_db = get_blockchain_db()
    if not blockchain_db:
        print('Error getting blockchain database instance for reading.')
        return [] # Return empty list on error
    try:
        blocks = blockchain_db.read_all_blocks()
        return blocks
    except Exception as e:
        print(f'Error reading database: {e}')
        return [] # Return empty list on error


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
        if block[0]['BlockHeader']['blockHash'] == BlockHeader:
            return render_template('blockDetails.html', block = block, main_prefix=main_prefix, encode_base58=encode_base58, sha256=sha256, bytes = bytes)
    
    return "<h1> Invalid Identifier </h1>"


@app.route('/address/<publicAddress>')
def address(publicAddress):
    reload_utxos_from_chain()

    # Validate publicAddress…
    if not (len(publicAddress) < 35 and publicAddress[0] == "1"):
        return "<h1>Invalid Identifier</h1>"
    # Calculate spendable funds by iterating UTXOs that belong to publicAddress.
    acct = account.get_account(publicAddress)
    if acct is None:
        return "<h1>Account not found</h1>"
    spendable, staked = acct.get_balance(UTXOS)
    print(f"[DEBUG][address] spendable={spendable} staked={staked}")
    # --- UTXOs belonging to this address ---
    
    utxo_list = []
    h160_user = decode_base58(publicAddress)
    spent_keys = set()

    # Build a set of (txid, idx) pairs spent by mempool txs
    for tx in MEMPOOL.values():
        for txin in tx.tx_ins:
            spent_keys.add((txin.prev_tx.hex(), txin.prev_index))

    for (txid, idx), tx_out in UTXOS.items():
        # Skip if this UTXO is being spent by a pending tx
        if (txid, idx) in spent_keys:
            print(f"[DEBUG][UI] Skipping UTXO {txid}:{idx} as it is spent by a pending tx")
            continue
        cmds = tx_out.script_publickey.cmds
        print(f"[DEBUG][UTXO] {txid}:{idx} cmds={cmds} amount={tx_out.amount}")
        # Standard spendable output (P2PKH)
        if len(cmds) >= 3 and cmds[2] == h160_user and cmds[0] == 0x76:
            is_staking = False
        # Staked output (StakingScript)
        elif len(cmds) == 3 and cmds[0] == b'\x00' and cmds[1] == h160_user:
            is_staking = True
        else:
            continue  # <-- SKIP UTXOs not belonging to this address

        locktime = int.from_bytes(cmds[2], 'big') if is_staking else None
        print(f"[DEBUG][UI] Adding confirmed UTXO: {txid}:{idx} pending=False is_staking={is_staking}")
        utxo_list.append({
            "txid": txid,
            "index": idx,
            "amount": tx_out.amount,
            "is_staking": is_staking,
            "locktime": locktime,
            "pending": False
        })

    # --- Pending transactions from MEMPOOL ---
    pending_txs = []
    for txid, tx in MEMPOOL.items():
        # Check if this tx spends from or pays to this address
        involved = False
        # Check outputs (receiving funds)
        for idx, tx_out in enumerate(tx.tx_outs):
            cmds = tx_out.script_publickey.cmds
            is_staking = (len(cmds) == 3 and cmds[0] == b'\x00' and cmds[1] == h160_user)
            is_spendable = (len(cmds) >= 3 and cmds[2] == h160_user and cmds[0] == 0x76)
            if is_staking or is_spendable:
                print(f"[DEBUG][UI] Adding pending UTXO: {txid}:{idx} pending=True is_staking={is_staking}")
                pending_txs.append({
                    "txid": txid,
                    "index": idx,
                    "amount": tx_out.amount,
                    "is_staking": is_staking,
                    "locktime": int.from_bytes(cmds[2], 'big') if is_staking else None,
                    "pending": True
                })
                involved = True
        # Check inputs (spending funds)
        for tx_in in tx.tx_ins:
            # If this input spends a UTXO belonging to this address, show as pending spent
            prev_key = (tx_in.prev_tx.hex(), tx_in.prev_index)
            if prev_key in UTXOS:
                prev_out = UTXOS[prev_key]
                cmds = prev_out.script_publickey.cmds
                if (len(cmds) == 3 and cmds[0] == b'\x00' and cmds[1] == h160_user) or \
                   (len(cmds) >= 3 and cmds[2] == h160_user and cmds[0] == 0x76):
                    pending_txs.append({
                        "txid": tx_in.prev_tx.hex(),
                        "index": tx_in.prev_index,
                        "amount": prev_out.amount,
                        "is_staking": (len(cmds) == 3 and cmds[0] == b'\x00' and cmds[1] == h160_user),
                        "locktime": int.from_bytes(cmds[2], 'big') if (len(cmds) == 3 and cmds[0] == b'\x00' and cmds[1] == h160_user) else None,
                        "pending": True,
                        "spent": True
                    })

    # Combine confirmed and pending, but don't duplicate
    all_utxos = utxo_list.copy()
    # Only add pending outputs that are not already in confirmed UTXOs
    existing_keys = {(u['txid'], u['index']) for u in utxo_list}
    for p in pending_txs:
        if (p['txid'], p['index']) not in existing_keys:
            all_utxos.append(p)


    return render_template(
        "address.html",
        publicAddress=publicAddress,
        amount=spendable,
        staked=staked,
        Txs=all_utxos
    )



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

@app.route('/stake', methods=['GET', 'POST'])
def stake_page():
    global UTXOS, MEMPOOL
    message = ""
    addr = None
    account_data = None
    spendable_balance = 0 # Initialize spendable balance from UTXOs

    if request.method == 'POST':
        reload_utxos_from_chain()
        if request.is_json:
            data = request.get_json()
            action = data.get("action")
            fromAddress = data.get("fromAddress")
            acct = account.get_account(fromAddress)
            if acct is None:
                return jsonify({"error": "Account not found."}), 400
            try:
                if action == "stake":
                    # Process staking form.
                    amount_TDC = float(data.get("amount", 0)) # Use float for TDC input
                    lock_duration = int(data.get("lock_duration", 0))
                    if amount_TDC is None or lock_duration is None:
                        return jsonify({"error": "Please fill out all fields for staking."}), 400
                    elif amount_TDC <= 0 or lock_duration <= 0:
                         return jsonify({"error": "Amount and lock duration must be positive."}), 400
                    else:
                        amount = int(amount_TDC * 100000000)  # Convert TDC to satoshis
                        stakeTx = acct.create_stake_transaction(amount, lock_duration, UTXOS, fromAddress)
                    if not stakeTx:
                        return jsonify({"error": "Insufficient balance or error preparing stake transaction."}), 400
                    else:
                        # Verify inputs before adding to mempool
                        verified = True
                        script_pubkey = acct.script_public_key(fromAddress)
                        for i in range(len(stakeTx.tx_ins)):
                            if not stakeTx.verify_input(i, script_pubkey):
                                verified = False
                                return jsonify({"error": f"Input verification failed for input {i}."}), 400
                                break
                        if verified:
                            MEMPOOL[stakeTx.TxId] = stakeTx
                            logging.info(f"SUCCESS: Stake transaction {stakeTx.TxId} by {fromAddress} for {amount} satoshis added to mempool.")
                            broadcastTx(stakeTx) # Broadcast the transaction
                            return jsonify({"success": True, "txid": stakeTx.TxId}), 200

                elif action == "unstake":
                    # Process unstake form.
                    unstake_amount_TDC = float(data.get("amount_unstake")) # Use float
                    if unstake_amount_TDC is None:
                        return jsonify({"error": "Please specify an amount to unstake."}), 400
                    elif unstake_amount_TDC <= 0:
                         return jsonify({"error": "Unstake amount must be positive."}), 400
                    else:
                        unstake_amount = int(unstake_amount_TDC * 100000000)  # Convert TDC to satoshis
                        unstakeTx = acct.create_unstake_transaction(unstake_amount, UTXOS)
                        if not unstakeTx:
                            return jsonify({"error": "Could not create unstake transaction. Check lock time, staked amount, or balance."}), 400
                        script_pubkey = acct.script_public_key(fromAddress)
                        verified = all(unstakeTx.verify_input(i, script_pubkey) for i in range(len(unstakeTx.tx_ins)))
                    if verified:
                        MEMPOOL[unstakeTx.TxId] = unstakeTx
                        logging.info(f"SUCCESS: Unstake transaction {unstakeTx.TxId} by {fromAddress} for {unstake_amount} satoshis added to mempool.")
                        broadcastTx(unstakeTx)
                        return jsonify({"success": True, "txid": unstakeTx.TxId}), 200
                    else:
                        return jsonify({"error": "Input verification failed."}), 400
                else:
                    return jsonify({"error": "Invalid action."}), 400
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500
        # For non-JSON POST, handle form data
        else:
             # --- Browser POST (form) ---
            action = request.form.get("action")
            fromAddress = request.form.get("fromAddress")
            addr = fromAddress # record address from POST to display metrics later

            if not fromAddress:
                message = "Please provide your wallet address."
            else:
                acct = account.get_account(fromAddress)
                if acct is None:
                    message = "Account not found. Please create an account first."
                else:
                    try:
                        if action == "stake":
                            # Process staking form.
                            amount_TDC = request.form.get("amount", type=float) # Use float for TDC input
                            lock_duration = request.form.get("lock_duration", type=int)
                            if amount_TDC is None or lock_duration is None:
                                message = "Please fill out all fields for staking."
                            elif amount_TDC <= 0 or lock_duration <= 0:
                                message = "Amount and lock duration must be positive."
                            else:
                                amount = int(amount_TDC * 100000000)  # Convert TDC to satoshis
                                stakeTx = acct.create_stake_transaction(amount, lock_duration, UTXOS, fromAddress)
                            if not stakeTx:
                                message = "Insufficient balance or error preparing stake transaction."
                            else:
                                # Verify inputs before adding to mempool
                                verified = True
                                script_pubkey = acct.script_public_key(fromAddress)
                                for i in range(len(stakeTx.tx_ins)):
                                    if not stakeTx.verify_input(i, script_pubkey):
                                        verified = False
                                        message = f"Input verification failed for input {i}."
                                        break
                                if verified:
                                    MEMPOOL[stakeTx.TxId] = stakeTx
                                    logging.info(f"SUCCESS: Stake transaction {stakeTx.TxId} by {fromAddress} for {amount} satoshis added to mempool.")

                                    # update_utxo_set(stakeTx, UTXOS) # Update UTXOs locally
                                    # No need to update acct fields here; already done in create_stake_transaction
                                    broadcastTx(stakeTx) # Broadcast the transaction
                                    message = f"Stake transaction created and broadcasted with TxID {stakeTx.TxId}. Your stake increased by {amount_TDC} TDC."

                        elif action == "unstake":
                            # Process unstake form.
                            unstake_amount_TDC = request.form.get("amount_unstake", type=float) # Use float
                            if unstake_amount_TDC is None:
                                message = "Please specify an amount to unstake."
                            elif unstake_amount_TDC <= 0:
                                message = "Unstake amount must be positive."
                            else:
                                unstake_amount = int(unstake_amount_TDC * 100000000)  # Convert TDC to satoshis
                                unstakeTx = acct.create_unstake_transaction(unstake_amount, UTXOS)
                                if not unstakeTx:
                                    message = "Could not create unstake transaction. Check lock time, staked amount, or balance."
                                else:
                                    # Verify inputs before adding to mempool
                                    verified = True
                                    script_pubkey = acct.script_public_key(fromAddress)
                                    for i in range(len(unstakeTx.tx_ins)):
                                        if not unstakeTx.verify_input(i, script_pubkey):
                                            verified = False
                                            message = f"Input verification failed for input {i}."
                                            break
                                    if verified:
                                        MEMPOOL[unstakeTx.TxId] = unstakeTx
                                        logging.info(f"SUCCESS: Unstake transaction {unstakeTx.TxId} by {fromAddress} for {unstake_amount} satoshis added to mempool.")
                                        # update_utxo_set(unstakeTx, UTXOS) # Update UTXOs locally
                                        # No need to update acct fields here; already done in create_unstake_transaction
                                        broadcastTx(unstakeTx) # Broadcast the transaction
                                        message = f"Unstake transaction created and broadcasted with TxID: {unstakeTx.TxId}"
                        else:
                            message = "Invalid action."
                    except Exception as e:
                        import traceback
                        traceback.print_exc() # Print full traceback to console for debugging
                        message = f"An unexpected error occurred: {str(e)}"
    else:
        # For GET, try to get the address from a query parameter.
        addr = request.args.get("fromAddress")

    # Fetch account metrics and calculate spendable balance if an address is available.
    if addr:
        # Basic validation before fetching
        if len(addr) < 35 and addr.startswith("1"):
            account_data = account.get_account(addr)
            if account_data:
                try:
                    user_script = Script().p2pkh_script(decode_base58(addr))
                    for (txid, idx), tx_out in UTXOS.items():
                        if tx_out is None:
                            continue
                        if tx_out.script_publickey.serialise() == user_script.serialise():
                            if hasattr(tx_out, 'amount') and isinstance(tx_out.amount, (int, float)):
                                spendable_balance += tx_out.amount
                except Exception as e:
                    print(f"Error calculating spendable balance for stake page: {e}")
                    traceback.print_exc()
            else:
                message = f"Account not found for address: {addr}"
        else:
            message = "Invalid address format provided in URL."


    # Pass the account data and the calculated spendable balance to the template
    return render_template("stake.html",
                           message=message,
                           account=account_data,
                           spendable_balance=spendable_balance) # Pass calculated UTXO balance



def broadcastTx(TxObj):
    global UTXOS, MEMPOOL
    try:
        node = NodeDB()
        portList = node.read_nodes()

        if not isinstance(portList, list):
            print(f"Warning: NodeDB().read() did not return a list, got: {type(portList)}")
            portList = [] # Default to empty list

        serialized_tx = TxObj.serialise()
        print(f"DEBUG: Broadcasting Serialized Tx: {serialized_tx.hex()}")
        print(f"DEBUG (Sender): TxId: {TxObj.TxId}")
        
        for port_tuple in portList:
                    # Assuming read() returns list of tuples like [(port,)]
                    if isinstance(port_tuple, (tuple, list)) and len(port_tuple) > 0:
                        port = port_tuple[0]
                    elif isinstance(port_tuple, int):
                        port = port_tuple # Handle if it returns list of ints
                    else:
                        print(f"Warning: Skipping invalid port entry in list: {port_tuple}")
                        continue

                    if localHostPort != port:
                        # Use 127.0.0.1 as host, assuming local network
                        sync = syncManager('127.0.0.1', port, MEMPOOL)
                        try:
                            # sync.connectToHost(localHostPort - 1, port) # connectToHost might not be needed/correct here
                            sync.publishTx(TxObj)
                            print(f"Published Tx {TxObj.TxId} to port {port}")

                        except Exception as err:
                            print(f"Error publishing Tx to port {port}: {err}")

    except Exception as err:
        import traceback
        traceback.print_exc()
        print(f"Error during broadcastTx setup: {err}")

def reload_utxos_from_chain():
    global UTXOS
    from Blockchain.Backend.core.pos_blockchain import Blockchain
    blockchain = Blockchain(UTXOS, MEMPOOL, None, None, localHostPort, "127.0.0.1")
    blockchain.buildUTXOS()
    UTXOS = blockchain.get_utxos()
    print("[Frontend] UTXO set reloaded from blockchain.")


def main(utxos, mem_pool,port, localPort):
    global UTXOS, MEMPOOL, localHostPort
    UTXOS = utxos
    MEMPOOL = mem_pool
    localHostPort = localPort
    print(f"Frontend starting on port {port}, node network port is {localHostPort}") # Add print statement
    # Use waitress for production, or app.run for debug
    # serve(app, host='127.0.0.1', port=port) # Use Waitress
    app.run(host='127.0.0.1', port=port,debug=True,use_reloader=False)

if __name__ == '__main__':
     # Example for standalone testing (won't have shared memory)
     print("Running frontend standalone for testing (no shared memory)")
     test_port = 5900
     test_local_port = 9000
     # Create dummy shared objects if needed for testing routes
     # from multiprocessing import Manager
     # manager = Manager()
     # test_utxos = manager.dict()
     # test_mempool = manager.dict()
     main({}, {}, test_port, test_local_port) # Pass empty dicts for standalone


# -----------------------Legacy Code-----------------------

                    # elif action == "claim":
                    #     # Process claim rewards form.
                    #     claim_amount_TDC = request.form.get("amount_claim", type=float) # Use float
                    #     if claim_amount_TDC is None:
                    #         message = "Please specify an amount to claim."
                    #     elif claim_amount_TDC <= 0:
                    #          message = "Claim amount must be positive."
                    #     else:
                    #         claim_amount = int(claim_amount_TDC * 100000000)  # Convert TDC to satoshis

                    #          # --- DEBUG: Print balance before ---
                    #         print(f"DEBUG: Claiming {claim_amount_TDC} TDC ({claim_amount} satoshis) for {acct.public_addr}")
                    #         # print(f"DEBUG: Pending rewards BEFORE claim: {acct.pending_rewards}")
                    #         # --- End DEBUG ---
                    #         # Check if claim amount exceeds pending rewards
                    #         if claim_amount > acct.unspent:
                    #             message = "Claim amount exceeds available rewards."
                    #         else:
                    #             claimTx = acct.create_claim_rewards_transaction(claim_amount, UTXOS)
                    #             if not claimTx:
                    #                 message = "Could not create claim transaction. Insufficient rewards or error."
                    #             else:
                    #                 # No inputs to verify for claim tx (it's like coinbase)
                    #                 MEMPOOL[claimTx.TxId] = claimTx
                    #                 # update_utxo_set(claimTx, UTXOS) # Update UTXOs locally
                    #                 # Account rewards are likely updated within create_claim_rewards_transaction or need manual update
                    #                 # acct.pending_rewards -= claim_amount # Assuming this happens in create_claim or needs to be done here
                    #                 # acct.save_to_db() # Save changes if any
                    #                 broadcastTx(claimTx) # Broadcast the transaction
                    #                 message = f"Claim rewards transaction created and broadcasted with TxID: {claimTx.TxId}"
                    #         # --- DEBUG: Print balance after ---
                    #         print(f"DEBUG: Pending rewards AFTER claim: {acct.pending_rewards}")
