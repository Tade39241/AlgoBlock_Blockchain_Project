from Blockchain.Backend.util.util import hash160
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import Sha256Point, Signature


def op_dup(stack):

    if len(stack) < 1:
        return False
    stack.append(stack[-1])

    return True


def op_hash160(stack):
    if len(stack) < 1:
        return False
    element = stack.pop()
    h160 = hash160(element)
    stack.append(h160)
    return True


def op_equal(stack):
    if len(stack) < 2:
        return False

    element1 = stack.pop()
    element2 = stack.pop()

    if element1 == element2:
        stack.append(1)
    else:
        stack.append(0)

    return True


def op_verify(stack):
    if len(stack) < 1:
        False
    element = stack.pop()

    if element == 0:
        return False

    return True


def op_equalverify(stack):
    return op_equal(stack) and op_verify(stack)


def op_checksig(stack, z):
    if len(stack) < 1:
        return False

    sec_pubkey = stack.pop()
    der_signature = stack.pop()[:-1]

    try:
        point = Sha256Point.parse(sec_pubkey)
        sig = Signature.parse(der_signature)
    except Exception as e:
        return False

    if point.verify(z, sig):
        stack.append(1)
        return True
    else:
        stack.append(0)
        return False
    
def op_checklocktimeverify(stack, lock_time):
    if len(stack) < 1:
        return False
    element = stack[-1]  # Peek at the top of the stack
    try:
        tx_lock_time = int.from_bytes(element, 'big')
    except Exception:
        return False

    # Ensure the transaction's lock time matches or exceeds the script's lock time
    if tx_lock_time < lock_time:
        return False
    return True

def op_drop(stack):
    if len(stack) < 1:
        return False
    stack.pop()
    return True



OP_CODE_FUNCTION = {118: op_dup, 136: op_equalverify, 169: op_hash160, 172: op_checksig,177: op_checklocktimeverify, 117: op_drop}

