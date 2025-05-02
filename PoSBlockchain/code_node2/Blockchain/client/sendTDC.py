from Blockchain.Backend.util.util import decode_base58
from Blockchain.Backend.core.script import Script
from Blockchain.Backend.core.tx import TxIn, TxOut, Tx
from Blockchain.Backend.core.database.db import AccountDB
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import PrivateKey
from Blockchain.client.account import account
import time, random

from Blockchain.Backend.util.logging_config import get_logger # Adjust path if needed

# Get a logger specific to this module
logger = get_logger("SendTDC")


class sendTDC:
    def __init__(self, from_acct, to_acct, amount_satoshis, UTXOS,mempool=None):
        self.COIN = 100_000_000
        self.from_public_addr = from_acct
        self.to_acct = to_acct
        try:
            # Ensure it's an integer and positive
            self.amount = int(amount_satoshis)
            if self.amount <= 0:
                raise ValueError("Amount in satoshis must be positive.")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid amount_satoshis provided: {amount_satoshis}. ")
        
        self.utxos = UTXOS  # Should be {(txid, idx): TxOut}
        self.mempool = mempool
        self.Total = 0
        self.sufficient_balance = False
        self.fee = 1_000_000
        self.change_amount = 0
        self.from_public_addr_script_pubkey = None
        self.fromPubKeyHash = None
        self.TxIns = []
        self.TxOuts = []
        self.TxObj = None


    def script_public_key(self, public_addy):
        h160 = decode_base58(public_addy)
        script_pubkey = Script().p2pkh_script(h160)
        return script_pubkey
    
    def get_private_key(self, public_addr):
        acct = account.get_account(public_addr)
        if acct is None:
            raise KeyError(f"Account not found for address {public_addr}")
        return acct.privateKey
    

    def prepareTxIn(self):
        """
        Selects spendable UTXOs for the transaction, excluding those already spent in the mempool.
        """
        TxIns = []
        self.Total = 0 # Reset total for this specific call
        # logger.info(f"[prepareTxIn] Preparing inputs for sending {self.amount} satoshis from {self.from_public_addr}")
        try:
            self.from_public_addr_script_pubkey = self.script_public_key(self.from_public_addr)
            # Ensure cmds list is not empty and index 2 exists before accessing
            if len(self.from_public_addr_script_pubkey.cmds) > 2:
                 self.fromPubKeyHash = self.from_public_addr_script_pubkey.cmds[2]
                 if not isinstance(self.fromPubKeyHash, bytes) or len(self.fromPubKeyHash) != 20:
                      raise ValueError("Extracted PubKeyHash is not a 20-byte hash.")
                #  logger.info(f"[prepareTxIn] Sender H160: {self.fromPubKeyHash.hex()}")
            else:
                 raise ValueError("Could not extract PubKeyHash from sender's script.")

        except Exception as e:
            logger.error(f"[prepareTxIn] Failed to get script/hash for sender {self.from_public_addr}: {e}")
            self.sufficient_balance = False
            return []

        # 1. Get UTXOs currently being spent in the mempool
        spent_in_mempool = set()
        try:
            # Using items() on proxy dict is generally safe
            logger.debug(f"[prepareTxIn] Checking mempool ({type(self.mempool)}) with {len(self.mempool)} entries...")
            mempool_items = list(self.mempool.items()) # Snapshot if needed, though direct iteration often ok
            for tx_id, tx_obj_proxy in mempool_items:
                # Access attributes via the proxy
                try:
                    # We need to access the tx_ins attribute OF THE PROXY OBJECT
                    # If the proxy holds Tx objects, access directly. If it holds dicts, adjust.
                    # Assuming proxy holds Tx objects (or objects with similar attributes)
                    if hasattr(tx_obj_proxy, 'tx_ins'):
                        tx_inputs = tx_obj_proxy.tx_ins # Access via proxy
                        for tx_in in tx_inputs:
                            # Access attributes of the TxIn object (could also be proxy)
                             if hasattr(tx_in, 'prev_tx') and hasattr(tx_in, 'prev_index'):
                                 # Ensure prev_tx is bytes before hex(), handle potential proxy results
                                 prev_tx_bytes = getattr(tx_in, 'prev_tx')
                                 prev_idx_val = getattr(tx_in, 'prev_index')
                                 if isinstance(prev_tx_bytes, bytes):
                                      spent_in_mempool.add((prev_tx_bytes.hex(), prev_idx_val))
                                 else:
                                      logger.warning(f"Mempool tx {tx_id} input prev_tx type is {type(prev_tx_bytes)}, expected bytes.")
                             else:
                                 logger.warning(f"Mempool tx {tx_id} input object missing attributes (prev_tx/prev_index). Type: {type(tx_in)}")
                    else:
                        # If mempool stores dicts instead of objects
                        logger.warning(f"Mempool object for tx {tx_id} (type {type(tx_obj_proxy)}) lacks 'tx_ins' attribute.")
                        # Add logic here to parse inputs if mempool stores dicts

                except Exception as e_mempool_tx:
                    logger.error(f"Error processing mempool tx {tx_id}: {e_mempool_tx}")

        except Exception as e_mempool:
            logger.error(f"Error iterating mempool: {e_mempool}")
            # Decide handling: proceed without mempool check? fail?

        # logger.info(f"[prepareTxIn] Identified {len(spent_in_mempool)} UTXOs spent in mempool: {spent_in_mempool}")


        # 2. Select UTXOs, EXCLUDING those spent in mempool
        # logger.info(f"[prepareTxIn] Using confirmed UTXO snapshot ({type(self.utxos)}) with {len(self.utxos)} entries.")
        utxo_processed_count = 0
        required_total = self.amount + self.fee # Calculate required amount including fee
        # logger.info(f"[prepareTxIn] Required total (incl. fee {self.fee}): {required_total}")

        # Create a sorted list of UTXOs to process them consistently (optional, helps debugging)
        # Sorting by amount might prioritize larger UTXOs, potentially reducing number of inputs
        try:
            # Ensure keys are comparable (e.g., hex txid, int index)
            # Safely get items, handling potential proxy issues
             utxo_items = list(self.utxos.items())
             # Example sort: by amount descending (prioritize larger UTXOs)
             # Make sure tx_out has 'amount' attribute
             sorted_utxos = sorted(utxo_items, key=lambda item: getattr(item[1], 'amount', 0), reverse=True)
        except Exception as e_sort:
             logger.warning(f"Could not sort UTXOs, proceeding in default order: {e_sort}")
             sorted_utxos = list(self.utxos.items()) # Fallback

        for (txid_hex, index), tx_out in sorted_utxos: # Iterate sorted items
            utxo_processed_count += 1
            logger.debug(f"--- Checking UTXO {utxo_processed_count}/{len(self.utxos)}: ({txid_hex}, {index}) ---")
            try:
                # Add checks for valid TxOut and Script structure
                if not (hasattr(tx_out, 'amount') and hasattr(tx_out, 'script_publickey') and hasattr(tx_out.script_publickey, 'cmds')):
                    logger.warning(f"  Invalid structure for UTXO ({txid_hex}, {index}). Skipping.")
                    continue

                cmds = tx_out.script_publickey.cmds
                utxo_amount = tx_out.amount

                # Ensure amount is int
                if not isinstance(utxo_amount, int):
                    logger.warning(f"  UTXO ({txid_hex}, {index}) has non-integer amount ({type(utxo_amount)}). Skipping.")
                    continue

                # logger.debug(f"  Amount: {utxo_amount}, Script Cmds: {cmds}")

                 # *** CHECK IF SPENT IN MEMPOOL ***
                utxo_key = (txid_hex, index) # Key to check against mempool set
                if utxo_key in spent_in_mempool:
                    # logger.info(f"  Skipping UTXO {txid_hex}:{index} - already spent in mempool.")
                    continue
                 # ********************************

                # Check if it's a standard P2PKH output for the sender
                is_p2pkh_match = False
                if len(cmds) == 5 and cmds[0] == 0x76 and cmds[1] == 0xa9 and isinstance(cmds[2], bytes) and len(cmds[2]) == 20 and cmds[3] == 0x88 and cmds[4] == 0xac:
                    script_h160 = cmds[2]
                    if script_h160 == self.fromPubKeyHash:
                         is_p2pkh_match = True
                         logger.debug(f"  -> MATCHED P2PKH.")
                    else:
                         logger.debug(f"  -> P2PKH H160 mismatch.")
                else:
                     logger.debug(f"  -> Script structure not P2PKH.")

                # Only use matched P2PKH outputs that are NOT spent in mempool
                if is_p2pkh_match:
                    logger.debug(f"  Found spendable UTXO {txid_hex}:{index} (Amount: {utxo_amount})")
                    # Add input if needed
                    if self.Total < required_total:
                        self.Total += utxo_amount
                        TxIns.append(TxIn(
                            prev_tx=bytes.fromhex(txid_hex), # Convert hex txid back to bytes
                            prev_index=index,
                            script_sig=Script(), # Empty script_sig for now
                            sequence=0xFFFFFFFF
                        ))
                        # logger.info(f"  --> ADDED as input. Current Total: {self.Total}") # Log when added
                    else:
                        logger.debug(f"  Sufficient total already reached ({self.Total} >= {required_total}). Skipping add.")

                    # Break if sufficient funds found
                    if self.Total >= required_total:
                        #  logger.info("  Sufficient total found, breaking loop.")
                         break
                # else: # If not a match or spent in mempool
                    # logger.debug(f"  Skipping UTXO ({txid_hex}, {index}) - not a matching P2PKH or spent in mempool.")

            except Exception as e_inner:
                 logger.error(f"  Error processing UTXO ({txid_hex}, {index}): {e_inner}")
                 continue # Skip to next UTXO on error

        # Final check after loop
        self.sufficient_balance = self.Total >= required_total
        # logger.info(f"[prepareTxIn] Finished loop. Total found: {self.Total}. Sufficient: {self.sufficient_balance}")
        if not self.sufficient_balance:
             logger.warning(f"Insufficient balance for {self.from_public_addr}. Needed: {required_total}, Found: {self.Total}")

        self.TxIns = TxIns # Store prepared inputs
        return TxIns # Return the list of inputs found
    

    
    def prepareTxOut(self):
        """
        Build the outputs for a standard send transaction.
        """
        TxOuts = [] # Initialize list for this call
        recipient_amount = self.amount # Use satoshi amount directly

        # Build output for the recipient.
        try:
            to_script_public_key = self.script_public_key(self.to_acct)
        except Exception as e:
             logger.error(f"Error creating script for recipient {self.to_acct}: {e}")
             return [] # Cannot create output

        TxOuts.append(TxOut(recipient_amount, to_script_public_key))
        # logger.info(f"Prepared recipient output: Amount={recipient_amount}")

        # Calculate change amount.
        self.change_amount = self.Total - recipient_amount - self.fee
        # logger.info(f"Calculated change: {self.change_amount} (Total={self.Total}, Amount={recipient_amount}, Fee={self.fee})")

        # If there is change (and it's positive), create a change output.
        if self.change_amount > 0:
            # Ensure sender script was prepared in prepareTxIn
            if self.from_public_addr_script_pubkey is None:
                 logger.error("Cannot create change output: Sender script not available.")
                 return [] # Return empty list or raise error

            change_satoshi_amount = int(self.change_amount) # Ensure int
            change_output = TxOut(change_satoshi_amount, self.from_public_addr_script_pubkey)
            TxOuts.append(change_output)
            # logger.info(f"Prepared change output: Amount={change_satoshi_amount}")
        elif self.change_amount < 0:
             logger.error(f"Negative change amount ({self.change_amount}) calculated. Transaction invalid.")
             return []

        self.TxOuts = TxOuts # Store prepared outputs
        return TxOuts


    def sign_tx(self):
        """
        Sign each input in the transaction using the sender’s private key.
        """
        if self.TxObj is None:
            logger.error("[sign_tx] Cannot sign transaction: TxObj is None.")
            return False
        if not self.TxIns: # Check if TxIns list is empty
            logger.error("[sign_tx] Cannot sign transaction: TxIns list is empty.")
            return False
        if self.from_public_addr_script_pubkey is None:
            logger.error("[sign_tx] Cannot sign transaction: Sender script_pubkey not available.")
            return False

        try:
            secret = self.get_private_key(self.from_public_addr)
            # logger.debug(f"[sign_tx] Retrieved secret for signing: {str(secret)[:10]}...{str(secret)[-10:]}")
            priv = PrivateKey(secret=secret)
            # logger.debug(f"[sign_tx] Created PrivateKey object: {priv}")
        except (KeyError, AttributeError, Exception) as e:
            logger.error(f"[sign_tx] Failed to get private key for signing: {e}")
            return False

        # logger.info(f"[sign_tx] Attempting to sign {len(self.TxIns)} inputs for Tx {self.TxObj.id()}") # Use TxObj.id()
        try:
            all_signed = True # Flag to track success
            for index, tx_in in enumerate(self.TxIns):
                # logger.debug(f"[sign_tx] Calling TxObj.sign_input for index {index}")
                success = self.TxObj.sign_input(index, priv, self.from_public_addr_script_pubkey)
                if not success:
                    logger.error(f"[sign_tx] TxObj.sign_input returned False for index {index}")
                    all_signed = False
                    break # Stop signing if one input fails
            if all_signed:
                pass
                # logger.info(f"[sign_tx] All inputs appear signed successfully according to sign_input return values.")
            else:
                logger.error(f"[sign_tx] Signing failed for at least one input.")
            return all_signed # Return overall success/failure

        except Exception as e:
            logger.error(f"[sign_tx] Exception during signing loop: {e}")
            import traceback
            traceback.print_exc()
            return False


    def prepTransaction(self):
        """
        Build, sign, and return a new transaction if there is sufficient balance;
        otherwise, return False (None).
        """
        # 1. Prepare Inputs (checks balance and excludes mempool spends)
        self.TxIns = self.prepareTxIn()
        if not self.sufficient_balance:
            logger.warning("Transaction preparation failed: Insufficient balance or error finding inputs.")
            return None # Use None to clearly indicate failure

        # 2. Prepare Outputs
        self.TxOuts = self.prepareTxOut()
        if not self.TxOuts: # Check if output preparation failed (e.g., negative change)
            logger.error("Transaction preparation failed: Error preparing outputs.")
            return None

        # 3. Create Transaction Object
        try:
            # Ensure version=1, locktime=0 are appropriate
            self.TxObj = Tx(version=1, tx_ins=self.TxIns, tx_outs=self.TxOuts, locktime=0)
            # Set TxId immediately after creation
            self.TxObj.TxId = self.TxObj.id()
            # logger.info(f"Transaction object created with TxId: {self.TxObj.TxId}")
        except Exception as e:
            logger.error(f"Failed to create Tx object: {e}")
            return None

        # 4. Sign Transaction
        if not self.sign_tx():
            logger.error(f"Transaction signing failed for TxId: {self.TxObj.TxId}")
            return None

        # logger.info(f"Transaction {self.TxObj.TxId} prepared and signed successfully.")
        return self.TxObj

# Note: update_utxo_set is now typically handled by the Blockchain class
# when processing a confirmed block. The simulator/frontend shouldn't
# modify the canonical UTXO set directly.

# Keep the helper function if used elsewhere, but its role changes.
    
# def update_utxo_set(TxObj, utxos):
#     """
#     For each input in TxObj, remove the corresponding output from the global UTXO set.
#     Then, add the new outputs to the UTXO set.
#     """
#     # Remove spent outputs.
#     for txin in TxObj.tx_ins:
#         key = (txin.prev_tx.hex(), txin.prev_index)
#         if key in utxos:
#             print(f"Removing spent UTXO: {key}")
#             del utxos[key]
#         else:
#             print(f"Warning: Referenced UTXO {key} not found in UTXO set.")

#     # Add the new outputs to the UTXO set.
#     print(f"Adding new transaction {TxObj.TxId} with {len(TxObj.tx_outs)} output(s) to UTXO set.")
#     for idx, tx_out in enumerate(TxObj.tx_outs):
#         utxos[(TxObj.TxId, idx)] = tx_out







        