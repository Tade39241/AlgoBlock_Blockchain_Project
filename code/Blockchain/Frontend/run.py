from flask import Flask, render_template, request, redirect, url_for, session
from Blockchain.client.sendTDC import sendTDC
from Blockchain.Backend.core.Tx import Tx


app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('home.html')

@app.route('/transactions')
def transactions():
    return render_template('transactions.html')

@app.route('/mempool')
def mempool():
    render_template ('mempool.html')

@app.route('/', methods=['GET', 'POST'])
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

def main(utxos, mem_pool):
    global UTXOS
    global MEMPOOL
    UTXOS = utxos
    MEMPOOL = mem_pool
    app.run()
