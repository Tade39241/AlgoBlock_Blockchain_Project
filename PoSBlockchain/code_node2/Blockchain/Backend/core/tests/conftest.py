import pytest
from Tx import Tx, TxIn, TxOut
from script import Script

@pytest.fixture
def sample_tx():
    prev_tx = b'\x00' * 32
    prev_index = 0xffffffff
    script_sig = Script([b'test'])
    tx_in = TxIn(prev_tx, prev_index, script_sig)

    amount = 5000000000
    script_pubkey = Script([118, 169, b'address', 136, 172])
    tx_out = TxOut(amount, script_pubkey)

    return Tx(1, [tx_in], [tx_out], 0)
