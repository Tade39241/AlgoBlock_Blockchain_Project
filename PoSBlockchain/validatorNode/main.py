import sys
import os
import random
import json
from network.connection import Node
from network.network import NetworkEnvelope
from database.db import AccountDB
import configparser
import time
from Blockchain.Backend.util.util import decode_base58, encode_base58, hash256
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'code_node2'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

VALIDATOR_ADDRESS = '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh'

def get_staked_balances_from_utxos(utxo_set):
    staked = {}
    for (txid, idx), tx_out in utxo_set.items():
        cmds = tx_out.script_publickey.cmds
        if len(cmds) == 3 and cmds[0] == b'\x00':
            h160 = cmds[1]
            addr = encode_base58(b'\x00' + h160 + hash256(b'\x00' + h160)[:4])
            staked[addr] = staked.get(addr, 0) + tx_out.amount
    return staked

class ValidatorSelector:
    def __init__(self, host, port, peer_list):
        """
        host, port: This node's local address.
        peer_list: A list of peer addresses (tuples, e.g. (peer_host, peer_port))
                   to which the selection result will be broadcast.
        """
        self.host = host
        self.port = port
        self.peer_list = peer_list  # List of (host, port)
        self.account_db = AccountDB()  # To fetch all accounts with stake

 
    # In ValidatorSelector:
    def select_validator(self, utxo_set):
        staked = get_staked_balances_from_utxos(utxo_set)
        validators = [(addr, amt) for addr, amt in staked.items() if amt > 0 and addr != VALIDATOR_ADDRESS]
        if not validators:
            raise Exception("No validators available. Ensure at least one account has a stake.")
        total_stake = sum(amt for addr, amt in validators)
        r = random.uniform(0, total_stake)
        cumulative = 0
        for addr, amt in validators:
            cumulative += amt
            if r <= cumulative:
                return addr
        return validators[-1][0]

    def broadcast_selection(self, selected_validator):
        message_dict = {
            "type": "validator_selection",
            "selected_validator": selected_validator
        }
        payload = json.dumps(message_dict).encode()
        envelope = NetworkEnvelope(b'valselect', payload)
        
        for peer in self.peer_list:
            try:
                peer_host = peer[0]
                peer_port = int(peer[1])  # Convert port to integer if necessary.
                node = Node(self.host, peer_port)
                sock = node.connect(peer_port)
                print(f"Connecting to peer {peer_host}:{peer_port} to broadcast selection...")
                sock.sendall(envelope.serialise())
                sock.close()
                print(f"[ValidatorSelector] Successfully sent validator selection to {(peer_host, peer_port)}")
            except Exception as e:
                print(f"[ValidatorSelector] Error sending selection to {(peer_host, peer_port)}: {e}")

    def run(self, utxo_set):
        while True:
            try:
                selected_validator = self.select_validator(utxo_set)
                staked = get_staked_balances_from_utxos(utxo_set)
                print(f"[ValidatorSelector] Selected Validator: {selected_validator} with stake {staked[selected_validator]}")
                self.broadcast_selection(selected_validator)
            except Exception as e:
                print(f"[ValidatorSelector] Error during validator selection: {e}")
            time.sleep(60)


# -------------------------------Legacy Code-------------------------------
 # def select_validator(self):
    #     """
    #     Select a validator using weighted random selection.
    #     Only accounts with a nonzero 'staked' amount are eligible.
    #     """
    #     VALIDATOR_ADDRESS = '1CJL7mvokNjrs2D48jM3EEHoRhQiWCbxCh'

    #     accounts = self.account_db.read()
    #     validators = [acc for acc in accounts if acc.get('staked', 0) > 0 
    #                   and acc.get('public_addr') != VALIDATOR_ADDRESS]
    #     if not validators:
    #         raise Exception("No validators available. Ensure at least one account has a stake.")
        
    #     total_stake = sum(acc['staked'] for acc in validators)
    #     r = random.uniform(0, total_stake)
    #     cumulative = 0
    #     for acc in validators:
    #         cumulative += acc['staked']
    #         if r <= cumulative:
    #             return acc
    #     return validators[-1]  # Fallback

        # def run(self):
        # """
        # Main function that selects a validator and broadcasts the result.
        # """
        # while True:
        #     try:
        #         selected_validator = self.select_validator()
        #         print(f"[ValidatorSelector] Selected Validator: {selected_validator['public_addr']} with stake {selected_validator['staked']}")
        #         self.broadcast_selection(selected_validator)
        #     except Exception as e:
        #         print(f"[ValidatorSelector] Error during validator selection: {e}")
        #     time.sleep(60)