from flask import Flask, render_template, request, redirect, url_for, session
from Blockchain.client.sendTDC import sendTDC
from Blockchain.Backend.core.Tx import Tx
from Blockchain.Backend.core.database.db import BlockchainDB
from Blockchain.Backend.util.util import encode_base58,decode_base58
from hashlib import sha256
from flask_qrcode import QRcode

app = Flask(__name__)
qrcode = QRcode(app)
main_prefix = b'\00'
global memoryPool
memoryPool = {}

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

@app.route('/tx/<txid>')
def txDetails(txid):
    blocks = read_database()
    for block in blocks:
        for Tx in block[0]['Txs']:
            if Tx['TxId'] == txid:
                return render_template('txDetails.html', Tx=Tx, block=block,encode_base58=encode_base58,
                                       bytes = bytes, sha256=sha256, main_prefix = main_prefix)

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
            return redirect(url_for('txDetail', txid = identifier))
    else:
        return redirect(url_for('address', publicAddress = identifier))


def read_database():
    ErrorFlag = True
    while ErrorFlag:
        try:
            blockchain = BlockchainDB()
            blocks = blockchain.read_all_blocks()
            ErrorFlag = False
        except:
            ErrorFlag = True
            print('Error reading database')
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
        if block[0]['BlockHeader']['blockHash'] == BlockHeader:
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
                ErrorFlag = False
            except Exception as e:
                ErrorFlag = True
        
        amount = 0
        AccountUtxos = []

        for TxId in AllUtxos:
            for tx_out in AllUtxos[TxId].tx_outs:
                if tx_out.script_publickey.cmds[2] == h160:
                    amount += tx_out.amount
                    AccountUtxos.append(AllUtxos[TxId])
        return render_template('address.html', Txs = AccountUtxos, amount = amount,
                            encode_base58=encode_base58, bytes=bytes, sha256=sha256, main_prefix=main_prefix,
                            publicAddress=publicAddress,qrcode = qrcode)
    else:
        return "<h1> Invalid Identifier </h1>"

@app.route('/wallet', methods=['GET', 'POST'])
def wallet():
    message = ''
    if request.method == 'POST':
    
        from_addy = request.form.get("fromAddress")
        to_addy = request.form.get("toAddress")
        amount = request.form.get("Amount", type=int)
        sendCoin = sendTDC(from_addy, to_addy, amount,UTXOS)
        TxObj = sendCoin.prepTransaction()

        if not from_addy or not to_addy or amount is None:
            message = 'Please fill out all the fields.'

        script_pubkey = sendCoin.script_public_key(from_addy)
        verified = True

        if not TxObj:
            message = 'Insufficient balance'

        if isinstance(TxObj, Tx):
            for index, tx in enumerate(TxObj.tx_ins):
                if not TxObj.verify_input(index, script_pubkey):
                    verified = False
            
            if verified:
                MEMPOOL[TxObj.TxId] = TxObj
                message = 'Transaction added to mem pool'

    # Always return the template
    return render_template("wallet.html", message=message)

def main(utxos, mem_pool,port):
    global UTXOS
    global MEMPOOL
    UTXOS = utxos
    MEMPOOL = mem_pool
    app.run(port=port)
