import sys
import hashlib
from Crypto.Hash import RIPEMD160
from hashlib import sha256
from math import log
from Blockchain.Backend.core.EllepticCurve.EllepticCurve import BASE58_ALPHABET
import logging  # Add logging

logger = logging.getLogger(__name__)

# def hash256(s):
#     """
#     Two rounds of SHA256
#     """
#     return hashlib.sha256(hashlib.sha256(s).digest()).digest()

def hash256(s):
    """
    Two rounds of SHA256
    """
    # --- ADD DEBUG LOG ---
    # print(f"hash256 input bytes (len={len(s)}): {s.hex()}")
    # --- END DEBUG LOG ---
    h1 = hashlib.sha256(s).digest()
    h2 = hashlib.sha256(h1).digest()
    return h2

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

# def merkle_parent_level(hashes):
#     """takes a list of binary hashes and returns a list that's half of the length"""

#     if len(hashes) % 2 == 1:
#         hashes.append(hashes[-1])

#     parent_level = []

#     for i in range(0, len(hashes), 2):
#         parent = hash256(hashes[i] + hashes[i + 1])
#         parent_level.append(parent)
#     return parent_level

# def merkle_root(hashes):
#     """Takes a list of binary hashes and return the merkle root"""
#     current_level = hashes

#     while len(current_level) > 1:
#         current_level = merkle_parent_level(current_level)

#     return current_level[0]

def merkle_parent_level(hashes):
    """
    Takes a list of binary hashes and returns the next level up the Merkle tree.
    Does NOT modify the input list.
    """
    # Handle empty list case
    if not hashes:
        return []
    # If odd number of hashes, duplicate the last one FOR THIS LEVEL'S CALCULATION
    current_hashes = hashes
    if len(hashes) % 2 == 1:
        # Create a new list with the duplicated element, don't modify original
        current_hashes = hashes + [hashes[-1]]
        print(f"[MerkleParent] Odd level, padded with last hash. New len: {len(current_hashes)}",flush=True)

    parent_level = []
    # Iterate through pairs
    for i in range(0, len(current_hashes), 2):
        try:
            # Concatenate the pair
            concat_pair = current_hashes[i] + current_hashes[i+1]
            # Hash the concatenated pair
            parent = hash256(concat_pair)
            parent_level.append(parent)
        except IndexError:
            # This shouldn't happen with the padding logic, but added as safeguard
            print(f"[MerkleParent] IndexError during pairing at index {i}. List len: {len(current_hashes)}",flush=True)
            raise # Re-raise critical error
        except Exception as e:
            print(f"[MerkleParent] Error hashing pair at index {i}: {e}",flush=True)
            raise # Re-raise critical error

    print(f"[MerkleParent] Calculated parent level with {len(parent_level)} hashes.",flush=True)
    return parent_level

def merkle_root(hashes):
    """
    Takes a list of binary hashes and returns the Merkle root (binary).
    """
    if not hashes:
        print("[MerkleRoot] Called with empty hash list. Returning None or default hash?",flush=True)
        return None # Or perhaps a default hash like hash256(b'')?

    current_level = list(hashes) # Start with a copy of the original list

    print(f"[MerkleRoot] Starting calculation with {len(current_level)} leaf hashes.",flush=True)
    level_num = 0
    while len(current_level) > 1:
        level_num += 1
        print(f"[MerkleRoot] Calculating level {level_num} from {len(current_level)} hashes...",flush=True)
        current_level = merkle_parent_level(current_level) # This now receives and returns new lists

    print(f"[MerkleRoot] Final root calculated: {current_level[0].hex()}",flush=True)
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
    h160 = decode_base58(public_addr)
    remaining = amount_satoshis
    # Iterate over a copy of the keys because we may modify the dictionary.
    for (txid, idx) in list(utxo_set.keys()):
        tx_out = utxo_set[(txid, idx)]
        if tx_out.script_publickey.cmds[2] == h160:
            if tx_out.amount >= remaining:
                tx_out.amount -= remaining
                if tx_out.amount == 0:
                    del utxo_set[(txid, idx)]
                remaining = 0
                break  # Found enough funds; exit the loop.
            else:
                remaining -= tx_out.amount
                del utxo_set[(txid, idx)]
        if remaining == 0:
            break
    if remaining > 0:
        raise Exception("Insufficient UTXO balance to deduct the stake amount.")

# def deduct_from_utxos(public_addr, amount_satoshis, utxo_set):
#         """
#         Deduct the specified amount (in satoshis) from the UTXO set for the given public address.
#         The function searches for UTXOs whose output script matches the provided address
#         (by comparing the hash160 in the script with the hash160 derived from the public address).
#         It subtracts the given amount from these UTXOs, removing an output entirely if its amount is spent.
#         """
#         # Get the hash160 from the public address using your decode_base58 helper.
#         h160 = decode_base58(public_addr)
#         remaining = amount_satoshis
#         # Iterate over a copy of the keys because we may modify the dictionary.
#         for txid in list(utxo_set.keys()):
#             tx = utxo_set[txid]
#             # Iterate over the transaction outputs in reverse so that removal is safe.
#             for i in range(len(tx.tx_outs) - 1, -1, -1):
#                 tx_out = tx.tx_outs[i]
#                 # Check if this output belongs to the user.
#                 if tx_out.script_publickey.cmds[2] == h160:
#                     if tx_out.amount >= remaining:
#                         tx_out.amount -= remaining
#                         if tx_out.amount == 0:
#                             # Remove the output if it’s fully spent.
#                             tx.tx_outs.pop(i)
#                             # If the transaction now has no outputs, remove the UTXO entirely.
#                             if not tx.tx_outs:
#                                 del utxo_set[txid]
#                         remaining = 0
#                         break  # Found enough funds; exit the inner loop.
#                     else:
#                         remaining -= tx_out.amount
#                         # Remove this output entirely.
#                         tx.tx_outs.pop(i)
#                         if not tx.tx_outs:
#                             del utxo_set[txid]
#             if remaining == 0:
#                 break
#         if remaining > 0:
#             raise Exception("Insufficient UTXO balance to deduct the stake amount.")