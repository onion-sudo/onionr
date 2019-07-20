'''
    Onionr - Private P2P Communication

    This file handles Onionr's cryptography.
'''
'''
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
'''
import os, binascii, base64, hashlib, time, sys, hmac, secrets
import nacl.signing, nacl.encoding, nacl.public, nacl.hash, nacl.pwhash, nacl.utils, nacl.secret
import unpaddedbase32
import logger, onionrproofs
from onionrutils import stringvalidators, epoch, bytesconverter
import filepaths
import onionrexceptions, keymanager, onionrutils
import config
from . import generate, hashers
config.reload()

class OnionrCrypto:
    def __init__(self):
        self._keyFile = filepaths.keys_file
        self.pubKey = None
        self.privKey = None
        self.secrets = secrets
        self.deterministicRequirement = 25 # Min deterministic password/phrase length
        self.HASH_ID_ROUNDS = 2000
        self.keyManager = keymanager.KeyManager()

        # Load our own pub/priv Ed25519 keys, gen & save them if they don't exist
        if os.path.exists(self._keyFile):
            if len(config.get('general.public_key', '')) > 0:
                self.pubKey = config.get('general.public_key')
            else:
                self.pubKey = self.keyManager.getPubkeyList()[0]
            self.privKey = self.keyManager.getPrivkey(self.pubKey)
        else:
            keys = self.generatePubKey()
            self.pubKey = keys[0]
            self.privKey = keys[1]
            self.keyManager.addKey(self.pubKey, self.privKey)
        return


    def pubKeyEncrypt(self, data, pubkey, encodedData=False):
        '''Encrypt to a public key (Curve25519, taken from base32 Ed25519 pubkey)'''
        pubkey = unpaddedbase32.repad(bytesconverter.str_to_bytes(pubkey))
        retVal = ''
        box = None
        data = bytesconverter.str_to_bytes(data)
        
        pubkey = nacl.signing.VerifyKey(pubkey, encoder=nacl.encoding.Base32Encoder()).to_curve25519_public_key()

        if encodedData:
            encoding = nacl.encoding.Base64Encoder
        else:
            encoding = nacl.encoding.RawEncoder
        
        box = nacl.public.SealedBox(pubkey)
        retVal = box.encrypt(data, encoder=encoding)

        return retVal

    def symmetricEncrypt(self, data, key, encodedKey=False, returnEncoded=True):
        '''Encrypt data with a 32-byte key (Salsa20-Poly1305 MAC)'''
        if encodedKey:
            encoding = nacl.encoding.Base64Encoder
        else:
            encoding = nacl.encoding.RawEncoder

        # Make sure data is bytes
        if type(data) != bytes:
            data = data.encode()

        box = nacl.secret.SecretBox(key, encoder=encoding)

        if returnEncoded:
            encoding = nacl.encoding.Base64Encoder
        else:
            encoding = nacl.encoding.RawEncoder

        encrypted = box.encrypt(data, encoder=encoding)
        return encrypted

    def symmetricDecrypt(self, data, key, encodedKey=False, encodedMessage=False, returnEncoded=False):
        '''Decrypt data to a 32-byte key (Salsa20-Poly1305 MAC)'''
        if encodedKey:
            encoding = nacl.encoding.Base64Encoder
        else:
            encoding = nacl.encoding.RawEncoder
        box = nacl.secret.SecretBox(key, encoder=encoding)

        if encodedMessage:
            encoding = nacl.encoding.Base64Encoder
        else:
            encoding = nacl.encoding.RawEncoder
        decrypted = box.decrypt(data, encoder=encoding)
        if returnEncoded:
            decrypted = base64.b64encode(decrypted)
        return decrypted

    def generateSymmetric(self):
        '''Generate a symmetric key (bytes) and return it'''
        return binascii.hexlify(nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE))

    def generatePubKey(self):
        '''Generate a Ed25519 public key pair, return tuple of base32encoded pubkey, privkey'''
        return generate.generate_pub_key()

    def generateDeterministic(self, passphrase, bypassCheck=False):
        '''Generate a Ed25519 public key pair from a password'''
        passStrength = self.deterministicRequirement
        passphrase = bytesconverter.str_to_bytes(passphrase) # Convert to bytes if not already
        # Validate passphrase length
        if not bypassCheck:
            if len(passphrase) < passStrength:
                raise onionrexceptions.PasswordStrengthError("Passphase must be at least %s characters" % (passStrength,))
        # KDF values
        kdf = nacl.pwhash.argon2id.kdf
        salt = b"U81Q7llrQcdTP0Ux" # Does not need to be unique or secret, but must be 16 bytes
        ops = nacl.pwhash.argon2id.OPSLIMIT_SENSITIVE
        mem = nacl.pwhash.argon2id.MEMLIMIT_SENSITIVE

        key = kdf(32, passphrase, salt, opslimit=ops, memlimit=mem) # Generate seed for ed25519 key
        key = nacl.signing.SigningKey(key)
        return (key.verify_key.encode(nacl.encoding.Base32Encoder).decode(), key.encode(nacl.encoding.Base32Encoder).decode())

    def pubKeyHashID(self, pubkey=''):
        '''Accept a ed25519 public key, return a truncated result of X many sha3_256 hash rounds'''
        if pubkey == '':
            pubkey = self.pubKey
        prev = ''
        pubkey = bytesconverter.str_to_bytes(pubkey)
        for i in range(self.HASH_ID_ROUNDS):
            try:
                prev = prev.encode()
            except AttributeError:
                pass
            hasher = hashlib.sha3_256()
            hasher.update(pubkey + prev)
            prev = hasher.hexdigest()
        result = prev
        return result

    def sha3Hash(self, data):
        return hashers.sha3_hash(data)

    def blake2bHash(self, data):
        return hashers.blake2b_hash(data)

    def verifyPow(self, blockContent):
        '''
            Verifies the proof of work associated with a block
        '''
        retData = False

        dataLen = len(blockContent)

        try:
            blockContent = blockContent.encode()
        except AttributeError:
            pass

        blockHash = self.sha3Hash(blockContent)
        try:
            blockHash = blockHash.decode() # bytes on some versions for some reason
        except AttributeError:
            pass
        
        difficulty = onionrproofs.getDifficultyForNewBlock(blockContent, ourBlock=False)
        
        if difficulty < int(config.get('general.minimum_block_pow')):
            difficulty = int(config.get('general.minimum_block_pow'))
        mainHash = '0000000000000000000000000000000000000000000000000000000000000000'#nacl.hash.blake2b(nacl.utils.random()).decode()
        puzzle = mainHash[:difficulty]

        if blockHash[:difficulty] == puzzle:
            # logger.debug('Validated block pow')
            retData = True
        else:
            logger.debug("Invalid token, bad proof")

        return retData