import pytest
from Tx import Tx, TxIn, TxOut
from script import Script
from Blockchain.Backend.util.util import int_to_little_endian

def test_tx_serialization_consistency():
    # Setup a sample transaction
    prev_tx = b'\x00' * 32
    prev_index = 0xffffffff
    script_sig = Script([b'test'])
    tx_in = TxIn(prev_tx, prev_index, script_sig)

    amount = 5000000000
    script_pubkey = Script([118, 169, b'address', 136, 172])
    tx_out = TxOut(amount, script_pubkey)

    tx = Tx(1, [tx_in], [tx_out], 0)
    serialized = tx.serialise()

    # Parse the serialized transaction back
    parsed_tx = Tx.parse(serialized)
    assert parsed_tx.serialise() == serialized
    assert parsed_tx.id() == tx.id()
