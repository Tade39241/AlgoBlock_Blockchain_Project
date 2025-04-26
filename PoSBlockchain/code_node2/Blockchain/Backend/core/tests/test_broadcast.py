from unittest.mock import Mock
from Blockchain.Frontend.run import broadcastTx
from tx import Tx, TxIn, TxOut
from script import Script

def test_broadcast_and_receive():
    # Create a mock transaction
    prev_tx = b'\x00' * 32
    prev_index = 0xffffffff
    script_sig = Script([b'test'])
    tx_in = TxIn(prev_tx, prev_index, script_sig)

    amount = 5000000000
    script_pubkey = Script([118, 169, b'address', 136, 172])
    tx_out = TxOut(amount, script_pubkey)

    tx = Tx(1, [tx_in], [tx_out], 0)

    # Mock the syncManager
    syncManager = Mock()
    syncManager.publishTx.return_value = None

    # Test broadcasting
    broadcastTx(tx)
    syncManager.publishTx.assert_called_with(tx)

    # Simulate receiving
    serialized = tx.serialise()
    received_tx = Tx.parse(serialized)
    assert received_tx.id() == tx.id()
