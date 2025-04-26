import traceback
from Blockchain.Backend.util.util import decode_base58
from Blockchain.Backend.core.script import Script
from Blockchain.Backend.core.Tx import TxIn, TxOut, Tx
from Blockchain.Backend.core.database.db import AccountDB
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import PrivateKey
import time, random

SATOSHI = 100_000_000
FEE_BASE_UNITS = 10_000_000

class sendTDC:
    def __init__(self,from_acct,to_acct,amount, UTXOS):
        self.COIN = SATOSHI
        self.from_public_addr = from_acct
        self.to_acct = to_acct
        self.amount = amount * self.COIN
        self.utxos = UTXOS
        self.FEE_BASE_UNITS = FEE_BASE_UNITS


    def script_public_key(self, public_addy):
        h160 = decode_base58(public_addy)
        script_pubkey = Script().p2pkh_script(h160)
        return script_pubkey
    
    def get_private_key(self, from_public_addr):
        account_db = AccountDB()
        all_accts = account_db.read()

        # --- FIX: Iterate through account dictionaries directly ---
        for account_dict in all_accts: # Rename loop variable for clarity
            # Check if the current dictionary has the public address
            if account_dict.get('public_addr') == from_public_addr:
                # Return the private key from this dictionary
                return account_dict.get('privateKey')
        # --- End FIX ---

        # If no matching account was found after checking all dicts
        print(f"Error: Private key not found for address {from_public_addr}")
        return None # Return None or False to indicate failure
    
    
    # def prepareTxIn(self):
    #     TxIns = []
    #     self.Total = 0

    #     "convert public addy into public hash to find transactions that are locked into this hash"

    #     self.from_public_addr_script_pubkey = self.script_public_key(self.from_public_addr)
    #     self.from_pub_key_hash= self.from_public_addr_script_pubkey.cmds[2]

    #     newutxos = {}

    #     try:
    #         while len(newutxos) < 1:
    #             newutxos = dict(self.utxos)
    #             time.sleep(2)
    #     except Exception as e:
    #         print("Error in converting managed dict to normal dict")
        
    #     for Txbyte in newutxos:
    #         if self.Total < self.amount:
    #             TxObj = newutxos[Txbyte]
            
    #             for index, txout in enumerate(TxObj.tx_outs):
    #                 if txout.script_publickey.cmds[2] == self.from_pub_key_hash:
    #                     self.Total += txout.amount
    #                     prev_tx = bytes.fromhex(TxObj.id())
    #                     TxIns.append(TxIn(prev_tx, index))
    #                 else:
    #                     break
            
    #     if self.Total < self.amount:
    #         self.sufficient_balance = False
    #     else:
    #         self.sufficient_balance = True

    #     return TxIns

    def prepareTxIn(self):
        TxIns = []
        self.Total = 0
        self.sufficient_balance = True

        required_total = self.amount + self.FEE_BASE_UNITS

        # Convert Public Address into Public Hash to find tx_outs that are locked to this hash

        self.from_public_addr_script_pubkey = self.script_public_key(self.from_public_addr)
        self.fromPubKeyHash = self.from_public_addr_script_pubkey.cmds[2]

        newutxos = {}

        try:
            while not newutxos:
                newutxos = dict(self.utxos)
                if not newutxos: # Avoid busy-waiting if UTXOS is genuinely empty
                    print("UTXO set is currently empty, waiting...")
                    time.sleep(2)
        except Exception as e:
            print(f"Error converting Managed Dict to Normal Dict: {e}")
            self.sufficient_balance = False
            return [] # Return empty list on error
        
        # --- FIX: Iterate through UTXO items (key, value) ---
        utxo_items = list(newutxos.items()) # Get items to allow potential modification/removal if needed
        random.shuffle(utxo_items) # Shuffle to get random UTXOs instead of relying on dict order

        for utxo_key, tx_out_obj in utxo_items:
            # utxo_key is (txid_hex, prev_index)
            # tx_out_obj is the TxOut object

            # Check if the output script matches the sender's hash
            # Ensure comparison is bytes vs bytes
            if tx_out_obj.script_publickey and tx_out_obj.script_publickey.cmds and len(tx_out_obj.script_publickey.cmds) == 5 and tx_out_obj.script_publickey.cmds[2] == self.fromPubKeyHash:

                # Add this UTXO to the inputs
                self.Total += tx_out_obj.amount
                prev_tx_hash_hex = utxo_key[0]
                prev_index = utxo_key[1]
                prev_tx_bytes = bytes.fromhex(prev_tx_hash_hex) # Convert hex txid to bytes
                TxIns.append(TxIn(prev_tx_bytes, prev_index))

                # Check if we have collected enough value
                if self.Total >= required_total: # Check against amount + fee: # Check if enough for amount (fee added later)
                    print(f"Found sufficient funds: {self.Total} >= {required_total}")
                    break # Stop collecting inputs once amount is met

        


        # for index, Txbyte in enumerate(newutxos):
        #     if index > random.randint(1, 30):
        #         if self.Total < self.amount:
        #             TxObj = newutxos[Txbyte]

        #             for index, txout in enumerate(TxObj.tx_outs):
        #                 if txout.script_publickey.cmds[2] == self.fromPubKeyHash:
        #                     self.Total += txout.amount
        #                     prev_tx = bytes.fromhex(Txbyte)
        #                     TxIns.append(TxIn(prev_tx, index))
        #         else:
        #             break
            
        if self.Total < required_total:
            print(f"Insufficient funds. Need {required_total} (incl. fee), found {self.Total}")
            self.sufficient_balance = False
        else:
            self.sufficient_balance = True
            print(f"Found sufficient funds: {self.Total}")

        return TxIns

    def prepareTxOut(self):
        TxOuts = []
        # Ensure self.Total and self.amount are available from prepareTxIn
        if not hasattr(self, 'Total') or self.Total < self.amount:
             print("Cannot prepare TxOut: Insufficient funds or prepareTxIn not run.")
             return [] # Cannot prepare outputs without sufficient input total
        
        to_script_public_key = self.script_public_key(self.to_acct)
        TxOuts.append(TxOut(self.amount, to_script_public_key))

        "calculate fee"
        self.fee = self.FEE_BASE_UNITS
        self.change_amount = self.Total - self.amount - self.fee

        if self.change_amount > 0: # Avoid creating dust outputs
            # Ensure self.from_public_addr_script_pubkey is available
            if not hasattr(self, 'from_public_addr_script_pubkey'):
                 self.from_public_addr_script_pubkey = self.script_public_key(self.from_public_addr)

            TxOuts.append(TxOut(self.change_amount, self.from_public_addr_script_pubkey))

            print(f"Change output created: {self.change_amount}")
        else:
             print(f"No change output needed (Change: {self.change_amount})")

        return TxOuts
    
    def sign_tx(self):
        priv_key_str = self.get_private_key(self.from_public_addr)
        if priv_key_str is None:
            print("Signing failed: Could not retrieve private key.")
            # logger.error(f"Signing failed for {self.from_public_addr}: Private key not found in DB.")
            return False

        try:
            # --- FIX: Convert the retrieved string to an integer ---
            private_key_int = int(priv_key_str)
            # --- END FIX ---

            # Now create the PrivateKey object using the integer
            private_key = PrivateKey(secret=private_key_int)

        except ValueError:
            # Handle case where the string in the DB is not a valid integer
            print(f"Signing failed: Invalid private key format found in database for {self.from_public_addr}.")
            # logger.error(f"Signing failed for {self.from_public_addr}: Invalid private key format in DB.", exc_info=True)
            return False
        except Exception as e:
            # Catch other potential errors during PrivateKey creation
            print(f"Signing failed: Error creating PrivateKey object: {e}")
            # logger.error(f"Signing failed for {self.from_public_addr}: Error creating PrivateKey object.", exc_info=True)
            return False
        
        print("Starting signature process...")
        try:
            # Fetch the UTXO set again to get the script_pubkeys
            current_utxos = dict(self.utxos) # Get a fresh copy

            for index, tx_input in enumerate(self.TxIns):
                # --- THIS PART IS NECESSARY ---
                # Find the TxOut object corresponding to this TxIn
                utxo_key = (tx_input.prev_tx.hex(), tx_input.prev_index)
                if utxo_key not in current_utxos:
                    print(f"Signing failed: UTXO {utxo_key} for input {index} not found in current set.")
                    return False

                tx_out_to_spend = current_utxos[utxo_key]
                # Get the script_publickey from the UTXO being spent
                script_pubkey_to_spend = tx_out_to_spend.script_publickey
                # --- END NECESSARY PART ---

                if not script_pubkey_to_spend:
                    print(f"Signing failed: Missing script_publickey for UTXO {utxo_key} (input {index}).")
                    return False

                print(f"Signing input {index} using script from UTXO: {script_pubkey_to_spend.cmds}")
                # Pass the CORRECT script_pubkey from the UTXO
                if not self.TxObj.sign_input(index, private_key, script_pubkey_to_spend): # Pass script_pubkey_to_spend
                    print(f"Signing failed for input {index}")
                    return False

            print("All inputs signed successfully.")
            return True
        except Exception as e:
            print(f"Error during signing process: {e}")
            traceback.print_exc() # Print full traceback for debugging
            return False
        
        #  # Ensure self.from_public_addr_script_pubkey exists
        # if not hasattr(self, 'from_public_addr_script_pubkey'):
        #     self.from_public_addr_script_pubkey = self.script_public_key(self.from_public_addr)

        # for index, input in enumerate(self.TxIns):
        #     self.TxObj.sign_input(index, priv, self.from_public_addr_script_pubkey)
        
        # return True


    def prepTransaction(self):
        self.TxIns = self.prepareTxIn()

        if self.sufficient_balance:
            self.TxOuts = self.prepareTxOut()
            # Ensure TxOuts were actually prepared
            if not self.TxOuts:
                 print("Transaction preparation failed: Could not prepare outputs.")
                 return False

            # Check if total input matches total output + fee
            total_out = sum(txo.amount for txo in self.TxOuts)
            if self.Total != total_out + self.fee:
                 print(f"CRITICAL ERROR: Input total ({self.Total}) != Output total ({total_out}) + Fee ({self.fee})")
                 # This indicates a logic error in fee/change calculation
                 return False

            self.TxObj = Tx(1, self.TxIns, self.TxOuts, 0) # Assuming version 1, locktime 0

            if self.sign_tx(): # Check if signing was successful
                self.TxObj.TxId = self.TxObj.id() # Calculate TxId after signing
                print(f"Transaction prepared successfully: {self.TxObj.TxId}")
                return self.TxObj
            else:
                 print("Transaction preparation failed: Signing failed.")
                 return False
        else:
             print("Transaction preparation failed: Insufficient balance.")
             return False

def update_utxo_set(TxObj, utxos):
    """
    For each input in TxObj, remove the corresponding output from the global UTXO set.
    Then, add the new outputs to the UTXO set.
    """
    # Remove spent outputs.
    for txin in TxObj.tx_ins:
        key = (txin.prev_tx.hex(), txin.prev_index)
        utxos.pop(key, None)

    # 2) Add the new outputs under the canonical .txid
    txid = TxObj.txid
    for idx, tx_out in enumerate(TxObj.tx_outs):
        utxos[(txid, idx)] = tx_out
