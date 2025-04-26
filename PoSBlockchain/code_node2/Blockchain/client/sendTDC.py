from Blockchain.Backend.util.util import decode_base58
from Blockchain.Backend.core.script import Script
from Blockchain.Backend.core.tx import TxIn, TxOut, Tx
from Blockchain.Backend.core.database.db import AccountDB
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import PrivateKey
from Blockchain.client.account import account
import time, random

class sendTDC:
    def __init__(self, from_acct, to_acct, amount, UTXOS):
        self.COIN = 100000000
        self.from_public_addr = from_acct
        self.to_acct = to_acct
        self.amount = amount * self.COIN
        self.utxos = UTXOS  # Should be {(txid, idx): TxOut}


    def script_public_key(self, public_addy):
        h160 = decode_base58(public_addy)
        script_pubkey = Script().p2pkh_script(h160)
        return script_pubkey
    
    def get_private_key(self, public_addr):
        acct = account.get_account(public_addr)
        if acct is None:
            raise KeyError(f"Account not found for address {public_addr}")
        return acct.privateKey
    

    # def prepareTxIn(self):
    #     """
    #     Flatten the global UTXO set on the fly and select inputs that belong to the sender.
    #     (It assumes that a regular P2PKH output’s script has the public key hash at index 2.)
    #     """
    #     TxIns = []
    #     self.Total = 0
    #     # Get sender’s public key script and extract the public key hash.
    #     self.from_public_addr_script_pubkey = self.script_public_key(self.from_public_addr)
    #     self.fromPubKeyHash = self.from_public_addr_script_pubkey.cmds[2]

    #     # Flatten the UTXO set.
    #     flat_utxos = flatten_utxos(self.utxos)

    #     # Iterate over the flattened UTXO set to select inputs.
    #     for (txid, index), tx_out in flat_utxos.items():
    #         cmds = tx_out.script_publickey.cmds
    #         # Check that this output is a standard P2PKH output (not a staking one)
    #         if len(cmds) >= 3 and cmds[2] == self.fromPubKeyHash:
    #             if self.Total < self.amount:
    #                 self.Total += tx_out.amount
    #                 TxIns.append(TxIn(
    #                     prev_tx=bytes.fromhex(txid),
    #                     prev_index=index,
    #                     script_sig=Script(),  # Initially empty; will be filled when signing
    #                     sequence=0xFFFFFFFF
    #                 ))
    #             else:
    #                 break
    #     if self.Total < self.amount:
    #         self.sufficient_balance = False
    #     else:
    #         self.sufficient_balance = True

    #     return TxIns

    def prepareTxIn(self):
        TxIns = []
        self.Total = 0
        self.from_public_addr_script_pubkey = self.script_public_key(self.from_public_addr)
        self.fromPubKeyHash = self.from_public_addr_script_pubkey.cmds[2]

        # Iterate over the UTXO set directly
        for (txid, index), tx_out in self.utxos.items():
            cmds = tx_out.script_publickey.cmds
            if len(cmds) >= 3 and cmds[2] == self.fromPubKeyHash:
                if self.Total < self.amount:
                    self.Total += tx_out.amount
                    TxIns.append(TxIn(
                        prev_tx=bytes.fromhex(txid),
                        prev_index=index,
                        script_sig=Script(),
                        sequence=0xFFFFFFFF
                    ))
                else:
                    break
        self.sufficient_balance = self.Total >= self.amount
        return TxIns

    def prepareTxOut(self):
        """
        Build the outputs for a standard send transaction:
        One output sends the specified amount to the recipient.
        If there is change, add an output returning it to the sender.
        A fixed fee is subtracted.
        """
        TxOuts = []
        # Build output for the recipient.
        to_script_public_key = self.script_public_key(self.to_acct)
        TxOuts.append(TxOut(self.amount, to_script_public_key))

        # Calculate fee (here, a fixed fee is used; adjust as needed).
        self.fee = self.COIN
        self.change_amount = self.Total - self.amount - self.fee
        print(f"DEBUG: Total input = {self.Total}, amount = {self.amount}, fee = {self.fee}, change = {self.change_amount}")

        # If there is change, create a change output for the sender.
        if self.change_amount > 0:
            TxOuts.append(TxOut(self.change_amount, self.from_public_addr_script_pubkey))
        return TxOuts

    def sign_tx(self):
        """
        Sign each input in the transaction using the sender’s private key.
        """
        secret = self.get_private_key(self.from_public_addr)
        priv = PrivateKey(secret=secret)
        for index, tx_in in enumerate(self.TxIns):
            self.TxObj.sign_input(index, priv, self.from_public_addr_script_pubkey)
        return True

    def prepTransaction(self):
        """
        Build, sign, and return a new transaction if there is sufficient balance;
        otherwise, return False.
        """
        self.TxIns = self.prepareTxIn()
        if self.sufficient_balance:
            self.TxOuts = self.prepareTxOut()
            self.TxObj = Tx(1, self.TxIns, self.TxOuts, 0)
            self.sign_tx()
            self.TxObj.TxId = self.TxObj.id()
            return self.TxObj
        return False
    
def update_utxo_set(TxObj, utxos):
    """
    For each input in TxObj, remove the corresponding output from the global UTXO set.
    Then, add the new outputs to the UTXO set.
    """
    # Remove spent outputs.
    for txin in TxObj.tx_ins:
        key = (txin.prev_tx.hex(), txin.prev_index)
        if key in utxos:
            print(f"Removing spent UTXO: {key}")
            del utxos[key]
        else:
            print(f"Warning: Referenced UTXO {key} not found in UTXO set.")

    # Add the new outputs to the UTXO set.
    print(f"Adding new transaction {TxObj.TxId} with {len(TxObj.tx_outs)} output(s) to UTXO set.")
    for idx, tx_out in enumerate(TxObj.tx_outs):
        utxos[(TxObj.TxId, idx)] = tx_out

# def update_utxo_set(TxObj, utxos):
#     """
#     For each input in TxObj, remove the corresponding output from the global UTXO set.
#     Then, add the new transaction (with its outputs) to the UTXO set.
#     This function assumes that utxos is a dictionary keyed by transaction ID (txid)
#     and that each value is a Tx object that contains a list of outputs (tx_outs).
#     """
#     # Remove spent outputs.
#     for txin in TxObj.tx_ins:
#         prev_txid = txin.prev_tx.hex()
#         prev_index = txin.prev_index
#         if prev_txid in utxos:
#             prev_tx = utxos[prev_txid]
#             if hasattr(prev_tx, 'tx_outs') and len(prev_tx.tx_outs) > prev_index:
#                 print(f"Removing spent UTXO: txid {prev_txid}, index {prev_index}")
#                 prev_tx.tx_outs[prev_index] = None
#             else:
#                 print(f"Warning: Transaction {prev_txid} does not have an output at index {prev_index}")
#         else:
#             print(f"Warning: Referenced transaction {prev_txid} not found in UTXO set.")
    
#     # Add the new transaction to the UTXO set.
#     # All outputs in TxObj are assumed to be unspent.
#     print(f"Adding new transaction {TxObj.TxId} with {len(TxObj.tx_outs)} output(s) to UTXO set.")
#     utxos[TxObj.TxId] = TxObj
    







        