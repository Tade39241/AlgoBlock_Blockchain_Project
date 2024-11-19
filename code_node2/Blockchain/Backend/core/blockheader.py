from Blockchain.Backend.util.util import hash256, little_endian_to_int, int_to_little_endian, bits_to_targets
from Blockchain.Backend.core.database.db import BlockchainDB


class BlockHeader:
    def __init__(self, version, prevBlockHash, merkleRoot, timestamp, bits, nonce= None):
        self.version= version
        self.prevBlockHash = prevBlockHash
        self.merkleRoot = merkleRoot
        self.timestamp = timestamp
        self.bits = bits
        self.nonce = nonce
        self.blockHash = ''

    @classmethod
    def parse(cls, s):
        version = little_endian_to_int(s.read(4))
        prevBlockHash = s.read(32)[::-1]
        merkleRoot = s.read(32)[::-1]
        timestamp = little_endian_to_int(s.read(4))
        bits = s.read(4)
        nonce = s.read(4)
        return cls(version,prevBlockHash, merkleRoot, timestamp, bits, nonce)


    def serialise(self):
        result = int_to_little_endian(self.version, 4)
        result += self.prevBlockHash[::-1]
        result += self.merkleRoot[::-1]
        result += int_to_little_endian(self.timestamp, 4)
        result += self.bits
        result += self.nonce
        return result

    def mine(self, target):
        self.blockHash = target + 1
        while self.blockHash > target:
            self.blockHash = little_endian_to_int(
                hash256(
                    int_to_little_endian(self.version, 4) 
                    + bytes.fromhex(self.prevBlockHash)[::-1] 
                    + bytes.fromhex(self.merkleRoot)[::-1] 
                    + int_to_little_endian(self.timestamp, 4)
                    + self.bits 
                    + int_to_little_endian(self.nonce, 4)
                )
            )
            
            self.nonce +=1
            print(f" Mining Started {self.nonce}", end ='\r')
        self.blockHash = int_to_little_endian(self.blockHash, 32).hex()[::-1]
        self.nonce -= 1
        self.bits = self.bits.hex()
    
    def validateBlock(self):
        lastBlock = BlockchainDB().lastBlock()

        print(self.prevBlockHash.hex())
        if self.prevBlockHash.hex() == lastBlock[0]['BlockHeader']['blockHash']:
            if self.check_pow():
                return True
            
    def check_pow(self):
        sha = hash256(self.serialise())
        proof = little_endian_to_int(sha)
        print(proof)
        print(bits_to_targets(self.bits))
        print(proof < bits_to_targets(self.bits))
        return proof < bits_to_targets(self.bits)
    
    def generateBlockHash(self):
        sha = hash256(self.serialise())
        proof = little_endian_to_int(sha)
        return int_to_little_endian(proof, 32).hex()[::-1]
    
    def to_dict(self):
        dt = self.__dict__
        return dt



        
            
            



