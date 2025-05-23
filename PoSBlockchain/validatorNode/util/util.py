import hashlib
from Crypto.Hash import RIPEMD160
from hashlib import sha256
from math import log
from EllepticCurve.EllepticCurve import BASE58_ALPHABET

def hash256(s):
    """
    Two rounds of SHA256
    """
    return hashlib.sha256(hashlib.sha256(s).digest()).digest()

def hash160(s):
    
    return RIPEMD160.new(sha256(s).digest()).digest()

def bytes_needed(n):
    if n == 0:
        return 1
    else:
        return int(log(n,256)) + 1

def int_to_little_endian(s,length):
    return s.to_bytes(length,'little')

def little_endian_to_int(s):
    return int.from_bytes(s,'little')

def decode_base58(s):
    s = s.strip()
    n = 0

    for c in s:
        if c not in BASE58_ALPHABET:
            print(f"Character '{c}' not in BASE58_ALPHABET")
        n*= 58
        n+= BASE58_ALPHABET.index(c)
    
    combined = n.to_bytes(25, byteorder='big')
    check_sum = combined[-4:]

    if hash256(combined[:-4])[:4] != check_sum:
        raise ValueError(f'bad address {check_sum} {hash256(combined[:-4][:4])}')

    return combined[1:-4]

def encode_base58(s):
    count = 0
    for c in s:
        if c==0:
            count +=1
        else:
            break
    num = int.from_bytes(s,'big')
    prefix = '1'*count
    result = ''
    while num>0:
        num , mod= divmod(num,58)
        result=BASE58_ALPHABET[mod] + result
    return prefix+result

def read_varint(s):
    """ read_varint reads a variable integer stream """
    i = s.read(1)[0]
    if i == 0xfd:
        # 0xfd means the next two bytes are the number
        return little_endian_to_int(s.read(2))
    elif i == 0xfe:
        # 0xfe means the next four bytes are the number
        return little_endian_to_int(s.read(4))
    elif i == 0xff:
        # 0xff means the next eight bytes are the number
        return little_endian_to_int(s.read(8))
    else:
        # anything else is just an integer
        return i


def encode(i):
    "encodes int"
    if i < 0xfd:
        return bytes([i])
    elif i < 0x10000:
        return b'\xfd' + int_to_little_endian(i,2)
    elif i < 0x100000000:
        return b'\xfe' + int_to_little_endian(i,4)
    elif i < 0x10000000000000000:
        return b'\xff' + int_to_little_endian(i,8)
    else:
        raise ValueError(f'Integer {i} is too large')
    
def encode_ports_varint(i):
    """Encode an integer i as a Bitcoin-style varint
    specifically for portList, using a single byte for values < 0xfd."""
    if i < 0xfd:
        # single byte with the value i
        return bytes([i])
    elif i < 0x10000:
        return b'\xfd' + int_to_little_endian(i, 2)
    elif i < 0x100000000:
        return b'\xfe' + int_to_little_endian(i, 4)
    elif i < 0x10000000000000000:
        return b'\xff' + int_to_little_endian(i, 8)
    else:
        raise ValueError(f'Integer {i} is too large')

def merkle_parent_level(hashes):
    """takes a list of binary hashes and returns a list that's half of the length"""

    if len(hashes) % 2 == 1:
        hashes.append(hashes[-1])

    parent_level = []

    for i in range(0, len(hashes), 2):
        parent = hash256(hashes[i] + hashes[i + 1])
        parent_level.append(parent)
    return parent_level

def merkle_root(hashes):
    """Takes a list of binary hashes and return the merkle root"""
    current_level = hashes

    while len(current_level) > 1:
        current_level = merkle_parent_level(current_level)

    return current_level[0]

def target_to_bits(target):
    """Turns a target integer back into bits"""
    raw_bytes = target.to_bytes(32, "big")
    raw_bytes = raw_bytes.lstrip(b"\x00")  # <1>
    if raw_bytes[0] > 0x7F:  # <2>
        exponent = len(raw_bytes) + 1
        coefficient = b"\x00" + raw_bytes[:2]
    else:
        exponent = len(raw_bytes)  # <3>
        coefficient = raw_bytes[:3]  # <4>
    new_bits = coefficient[::-1] + bytes([exponent])  # <5>
    return new_bits


def bits_to_targets(bits):
    exponent = bits[-1]
    coefficient = little_endian_to_int(bits[:-1])
    return coefficient*256**(exponent - 3)

def deduct_from_utxos(public_addr, amount_satoshis, utxo_set):
        """
        Deduct the specified amount (in satoshis) from the UTXO set for the given public address.
        The function searches for UTXOs whose output script matches the provided address
        (by comparing the hash160 in the script with the hash160 derived from the public address).
        It subtracts the given amount from these UTXOs, removing an output entirely if its amount is spent.
        """
        # Get the hash160 from the public address using your decode_base58 helper.
        h160 = decode_base58(public_addr)
        remaining = amount_satoshis
        # Iterate over a copy of the keys because we may modify the dictionary.
        for txid in list(utxo_set.keys()):
            tx = utxo_set[txid]
            # Iterate over the transaction outputs in reverse so that removal is safe.
            for i in range(len(tx.tx_outs) - 1, -1, -1):
                tx_out = tx.tx_outs[i]
                # Check if this output belongs to the user.
                if tx_out.script_publickey.cmds[2] == h160:
                    if tx_out.amount >= remaining:
                        tx_out.amount -= remaining
                        if tx_out.amount == 0:
                            # Remove the output if it’s fully spent.
                            tx.tx_outs.pop(i)
                            # If the transaction now has no outputs, remove the UTXO entirely.
                            if not tx.tx_outs:
                                del utxo_set[txid]
                        remaining = 0
                        break  # Found enough funds; exit the inner loop.
                    else:
                        remaining -= tx_out.amount
                        # Remove this output entirely.
                        tx.tx_outs.pop(i)
                        if not tx.tx_outs:
                            del utxo_set[txid]
            if remaining == 0:
                break
        if remaining > 0:
            raise Exception("Insufficient UTXO balance to deduct the stake amount.")