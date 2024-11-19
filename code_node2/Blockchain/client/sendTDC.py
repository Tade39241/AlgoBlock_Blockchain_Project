from Blockchain.Backend.util.util import decode_base58
from Blockchain.Backend.core.script import Script
from Blockchain.Backend.core.Tx import TxIn, TxOut, Tx
from Blockchain.Backend.core.database.db import AccountDB
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import PrivateKey
import time

class sendTDC:
    def __init__(self,from_acct,to_acct,amount, UTXOS):
        self.COIN = 1000000
        self.from_public_addr = from_acct
        self.to_acct = to_acct
        self.amount = amount * self.COIN
        self.utxos = UTXOS


    def script_public_key(self, public_addy):
        h160 = decode_base58(public_addy)
        script_pubkey = Script().p2pkh_script(h160)
        return script_pubkey
    
    def get_private_key(self, from_public_addr):
        account_db = AccountDB()
        all_accts = account_db.read()

        # for account in all_accts:
        #     print(account[account.index('public_addr')])
        #     if account[account.index('public_addr')] == from_public_addr:
        #         return account['privateKey']
        
        for account in all_accts:
            # Access the dictionary inside the list
            acct_dict = account[0]
            # print(acct_dict['public_addr'])
            if acct_dict['public_addr'] == from_public_addr:
                return acct_dict['privateKey']
        return False
    
    
    def prepareTxIn(self):
        TxIns = []
        self.Total = 0

        "convert public addy into public hash to find transactions that are locked into this hash"

        self.from_public_addr_script_pubkey = self.script_public_key(self.from_public_addr)
        self.from_pub_key_hash= self.from_public_addr_script_pubkey.cmds[2]

        newutxos = {}

        try:
            while len(newutxos) < 1:
                newutxos = dict(self.utxos)
                time.sleep(2)
        except Exception as e:
            print("Error in converting managed dict to normal dict")
        
        for Txbyte in newutxos:
            if self.Total < self.amount:
                TxObj = newutxos[Txbyte]
            
                for index, txout in enumerate(TxObj.tx_outs):
                    if txout.script_publickey.cmds[2] == self.from_pub_key_hash:
                        self.Total += txout.amount
                        prev_tx = bytes.fromhex(TxObj.id())
                        TxIns.append(TxIn(prev_tx, index))
                    else:
                        break
            
        if self.Total < self.amount:
            self.sufficient_balance = False
        else:
            self.sufficient_balance = True

        return TxIns

    def prepareTxOut(self):
        TxOuts = []
        to_script_public_key = self.script_public_key(self.to_acct)
        TxOuts.append(TxOut(self.amount, to_script_public_key))

        "calculate fee"

        self.fee = self.COIN
        self.change_amount = self.Total - self.amount - self.fee

        TxOuts.append(TxOut(self.change_amount, self.from_public_addr_script_pubkey))

        return TxOuts
    
    def sign_tx(self):
        secret = self.get_private_key(self.from_public_addr)
        priv = PrivateKey(secret=secret)

        for index, input in enumerate(self.TxIns):
            self.TxObj.sign_input(index, priv, self.from_public_addr_script_pubkey)
        
        return True


    def prepTransaction(self):
        self.TxIns= self.prepareTxIn()
        if self.sufficient_balance:
            self.TxOuts= self.prepareTxOut()
            self.TxObj= Tx(1,self.TxIns,self.TxOuts,0)
            self.TxObj.TxId = self.TxObj.id()
            self.sign_tx()
            return self.TxObj
        return False

        