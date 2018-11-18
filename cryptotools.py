from binascii import hexlify, unhexlify
import ecdsa
import hashlib
import random
import string
from Crypto.Hash import RIPEMD
from Crypto import Random
from Crypto.Cipher import AES
from google.appengine.ext import ndb
import base64
import logging

# blockcypher api
from blockcypher import get_address_overview
from blockcypher import create_unsigned_tx
from blockcypher import make_tx_signatures
from blockcypher import broadcast_signed_transaction
from blockcypher import get_blockchain_overview

BLOCK_SIZE = 16
b58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
pad = lambda s: s + (BLOCK_SIZE - len(s) % BLOCK_SIZE) * chr(BLOCK_SIZE - len(s) % BLOCK_SIZE)
unpad = lambda s: s[:-ord(s[len(s) - 1:])]

base_index_characters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']

class Cheque(ndb.Model):
    """Models a cheque data object"""
    created = ndb.DateTimeProperty(auto_now_add=True)
    ident_sha256 = ndb.StringProperty()
    private_key_encrypted = ndb.StringProperty()
    public_key = ndb.StringProperty()
    public_address = ndb.StringProperty()
    verification_shifts = ndb.StringProperty()

def send_tx(private_key_sender, public_key_sender, public_address_sender, public_address_receiver):
  # api key
  api_key = '880643770b1448bf87b4278eb145ab0f'
  addr_service_fee = '32pRJbkXSRcchk3TJfHY4jkkkki9s3y5Uj'
  
  # get fees
  try:
    medium_fees = int(get_blockchain_overview()['medium_fee_per_kb'])
    transaction_fee = int(medium_fees*0.5)
  except:
    return 101
  
  # get balance
  try:
    addr_overview = get_address_overview(public_address_sender)
    balance = int(addr_overview['balance'])
    service_fee = max(1000, int(balance * 0.015))   # lower limit for transaction is 546 satoshis 
    payout = int(balance - service_fee - transaction_fee)
    preference = 'low'
  except:
    return 102

  if payout <= 0:
    return 103
  
  # create unsigned transaction
  inputs = [{'address': public_address_sender}]
  outputs = [{'address': public_address_receiver, 'value': payout}, {'address': addr_service_fee, 'value': service_fee}]
  try:
    unsigned_tx = create_unsigned_tx(inputs=inputs, outputs=outputs, coin_symbol='btc', api_key=api_key, preference=preference)
  except:
    return 104
  
  # sign transaction
  privkey_list = [private_key_sender]
  pubkey_list = [public_key_sender]
  try:
    tx_signatures = make_tx_signatures(txs_to_sign=unsigned_tx['tosign'], privkey_list=privkey_list, pubkey_list=pubkey_list)
  except:
    return 105
  
  if 'errors' in tx_signatures:
    return 106
  
  # push transaction
  try:
    broadcasted = broadcast_signed_transaction(unsigned_tx=unsigned_tx, signatures=tx_signatures, pubkeys=pubkey_list, coin_symbol='btc', api_key=api_key)
  except:
    return 107
  
  if 'errors' in broadcasted:
    return broadcasted
  
  return 0
  
def get_balance(ident):
  #logging.debug('getting balance for ident ' + ident)
  ident_hash256 = hashlib.sha256(ident).hexdigest()
  query = Cheque.query(Cheque.ident_sha256 == ident_hash256).fetch(1)
  if len(query) == 0:
    return None
  cheque = query[0]
  try:
    address_overview = get_address_overview(cheque.public_address)
  except Exception as e:
    logging.error(e)
    return None
  return address_overview['balance']

def redeem(ident, verification_code, receiver_address):
  ident_hash256 = hashlib.sha256(ident).hexdigest()
  query = Cheque.query(Cheque.ident_sha256 == ident_hash256).fetch(1)
  if len(query) == 0:
    return None
  cheque = query[0]
  #try:
  private_key_sender = decrypt(cheque.private_key_encrypted, ident+verification_code)
  result = send_tx(private_key_sender, cheque.public_key, cheque.public_address, receiver_address)
    #address_overview = get_address_overview(cheque.public_address)
  #except:
    #return sys.exc_info()[0]
    #return 'redeem error'
  return result
    
def base58encode(n):
    result = ''
    while n > 0:
        result = b58[n%58] + result
        n /= 58
    return result

def base256decode(s):
    result = 0
    for c in s:
        result = result * 256 + ord(c)
    return result

def privateKeyToPublicKey(s):
    sk = ecdsa.SigningKey.from_string(s.decode('hex'), curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    return ('\04' + sk.verifying_key.to_string()).encode('hex')
  
def privateKeyToWif(key_hex):    
    return base58CheckEncode(0x80, key_hex.decode('hex'))
  
def base58CheckEncode(version, payload):
    s = chr(version) + payload
    checksum = hashlib.sha256(hashlib.sha256(s).digest()).digest()[0:4]
    result = s + checksum
    leadingZeros = countLeadingChars(result, '\0')
    return '1' * leadingZeros + base58encode(base256decode(result))
  
def countLeadingChars(s, ch):
    count = 0
    for c in s:
        if c == ch:
            count += 1
        else:
            break
    return count
  
def pubKeyToAddr(s):
    #ripemd160 = hashlib.new('ripemd160')
    ripemd160 = RIPEMD.new()
    ripemd160.update(hashlib.sha256(s.decode('hex')).digest())
    return base58CheckEncode(0, ripemd160.digest())

def keyToAddr(s):
    return pubKeyToAddr(privateKeyToPublicKey(s))
  
def generateKey():
  private_key = hexlify(ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1).to_string())
  public_key = privateKeyToPublicKey(private_key)
  public_address = keyToAddr(private_key)
  # wif = privateKeyToWif(private_key)
  return {'private_key': private_key,'public_key': public_key,'public_address': public_address}

def generateIdent():
  return ''.join(random.choice(string.digits) for _ in range(15))

def generateIden():
  return ''.join(random.choice(string.digits) for _ in range(15))

def generateVerification():
  verification_master = ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase) for _ in range(6))
  verification_shifts = ','.join(''.join(random.choice(string.digits) for _ in range(6)) for _ in range(16))
  return verification_master, verification_shifts
 
def encrypt(raw, password):
  private_key = hashlib.sha256(password.encode("utf-8")).digest()
  raw = pad(raw)
  iv = Random.new().read(AES.block_size)
  cipher = AES.new(private_key, AES.MODE_CBC, iv)
  return base64.b64encode(iv + cipher.encrypt(raw))

def decrypt(enc, password):
  private_key = hashlib.sha256(password.encode("utf-8")).digest()
  enc = base64.b64decode(enc)
  iv = enc[:16]
  cipher = AES.new(private_key, AES.MODE_CBC, iv)
  return unpad(cipher.decrypt(enc[16:]))

def generateCheque():
  # generate cheque database entity
  cheque = Cheque()
  
  # generate random cheque id
  ident = generateIdent()
  ident_sha256 = hashlib.sha256(ident).hexdigest()
  
  # generate random bitcoin key 
  key = generateKey()
  
  # generate random verification keys
  verification_master, verification_shifts = generateVerification()
  
  # push cheque to database
  cheque.ident_sha256 = ident_sha256
  cheque.private_key_encrypted = encrypt(key['private_key'], ident + verification_master)
  cheque.public_key = key['public_key']
  cheque.public_address = key['public_address']
  cheque.verification_shifts = verification_shifts
  cheque.put()
  
  return ident, verification_master, verification_shifts, cheque


def generate_chars_bars(verification_master, verification_shifts_string):
  
  # generate random int lists
  data = [x for x in range(52)]
  random_picks = []
  picks = []
  for j in range(24):
    if (j%6==0) and (j>0):
      picks.sort()
      random_picks.append(picks)
      picks = []
    index = random.randrange(len(data))
    elem = data[index]
    del data[index]
    picks.append(elem)
  picks.sort()
  random_picks.append(picks)
  
  # verification shifts
  verification_shifts_list = verification_shifts_string.split(',')
  
  # generate chars
  validation_chars_list = []
  for i in range(4):
    validation_chars = ">>" + base_index_characters[i] + ":|"
    for j in range(52):
      if j in random_picks[0]:
        validation_chars += verification_master_encrypt(verification_master, verification_shifts_list[i*4+0])[random_picks[0].index(j)]
      elif j in random_picks[1]:
        validation_chars += verification_master_encrypt(verification_master, verification_shifts_list[i*4+1])[random_picks[1].index(j)]
      elif j in random_picks[2]:
        validation_chars += verification_master_encrypt(verification_master, verification_shifts_list[i*4+2])[random_picks[2].index(j)]
      elif j in random_picks[3]:
        validation_chars += verification_master_encrypt(verification_master, verification_shifts_list[i*4+3])[random_picks[3].index(j)]
      else:
        validation_chars += random.choice(string.ascii_letters)
    validation_chars += "|"
    validation_chars_list.append(validation_chars) 
    validation_chars = ''
  
  # generate bars
  validation_bars_list = []
  for i in range(4):
    validation_bars = ">>" + base_index_characters[i+4] + ":|"
    for j in range(52):
      if j in random_picks[i]:
        validation_bars += "|"
      else:
        validation_bars += " "
    validation_bars += "|"
    validation_bars_list.append(validation_bars) 
    validation_bars = ''
  
  return validation_chars_list, validation_bars_list
  
def verification_master_encrypt(verification_master, index_digits):
  result = ''
  for i in range(6):
    n = ord(verification_master[i])
    # capital letters
    if n >= 65 and n <= 90:
      n += int(index_digits[i])
      if n > 90:
        n -= 26
    elif n >= 97 and n <= 122:
      n += int(index_digits[i])
      if n > 122:
        n -= 26
    else:
      return None
    result += chr(n)
  return result

def verification_master_decrypt(encrypted, index_digits):
  result = ''
  for i in range(6):
    n = ord(encrypted[i])
    # capital letters
    if n >= 65 and n <= 90:
      n -= int(index_digits[i])
      if n < 65:
        n += 26
    elif n >= 97 and n <= 122:
      n -= int(index_digits[i])
      if n < 97:
        n += 26
    else:
      return None
    result += chr(n)
  return result
