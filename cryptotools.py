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
import json
import urllib2
import math

# blockcypher api
from blockcypher import get_address_overview
from blockcypher import create_unsigned_tx
from blockcypher import make_tx_signatures
from blockcypher import broadcast_signed_transaction
from blockcypher import get_blockchain_overview

BLOCK_SIZE = 16
SERVICE_FEE = 0.0
SERVICE_FEE_LOWER_LIMIT = 1000

b58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
pad = lambda s: s + (BLOCK_SIZE - len(s) % BLOCK_SIZE) * chr(BLOCK_SIZE - len(s) % BLOCK_SIZE)
unpad = lambda s: s[:-ord(s[len(s) - 1:])]
base_index_characters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']

# load keys from keyfile
keys_str = open('keys.json').read()
keys = json.loads(keys_str)
api_key = keys['blockcypher_apikey']
addr_service_fee = keys['coinbase_addr_service_fee']

class Cheque(ndb.Model):
    """Models a cheque data object"""
    created = ndb.DateTimeProperty(auto_now_add=True)
    ident_sha256 = ndb.StringProperty()
    private_key_encrypted = ndb.StringProperty()
    public_key = ndb.StringProperty()
    public_address = ndb.StringProperty()
    verification_shifts = ndb.StringProperty()

def send_tx(private_key_sender, public_key_sender, public_address_sender, public_address_receiver):
  # get balance
  try:
    addr_overview = get_address_overview(public_address_sender)
    balance = int(addr_overview['final_balance'])
    service_fee, transaction_fee = get_fees(balance)

    if balance < (transaction_fee + service_fee + 1000):
        return 103, 'Error: Balance too low for payout. Minimum payout amout is {:.8f} BTC.'.format(float(transaction_fee + service_fee + 1000)/100000000.0)

    payout = int(balance - service_fee - transaction_fee)
  except Exception as e:
    logging.error(e)
    return 102, 'Service error, please try again later (Error T102).'

  # create unsigned transaction
  inputs = [{'address': public_address_sender}]
  if service_fee > 0:
    outputs = [{'address': public_address_receiver, 'value': payout}, {'address': addr_service_fee, 'value': service_fee}]
  else:
    outputs = [{'address': public_address_receiver, 'value': payout}]

  try:
    unsigned_tx = create_unsigned_tx(inputs=inputs, outputs=outputs, coin_symbol='btc', api_key=api_key, preference='low')
    logging.debug('unsigned_tx = ' + str(unsigned_tx))
  except Exception as e:
    logging.error(e)
    return 104, 'Service error, please try again later (Error T104).'

  # sign transaction
  privkey_list = [private_key_sender]
  pubkey_list = [public_key_sender]
  try:
    tx_signatures = make_tx_signatures(txs_to_sign=unsigned_tx['tosign'], privkey_list=privkey_list, pubkey_list=pubkey_list)
    logging.debug('tx_signatures = ' + str(tx_signatures))
  except Exception as e:
    return 105, 'Verification failed'

  if 'errors' in tx_signatures:
    return 106, 'Service error, please try again later (Error T106).'

  # push transaction
  try:
    broadcasted = broadcast_signed_transaction(unsigned_tx=unsigned_tx, signatures=tx_signatures, pubkeys=pubkey_list, coin_symbol='btc', api_key=api_key)
    logging.debug('broadcasted = ' + str(broadcasted))
  except Exception as e:
    logging.error(e)
    return 107, 'Service error, please try again later (Error T107).'

  if 'errors' in broadcasted:
    return 108, 'Service error, please try again later (Error T108).'

  return 0, broadcasted['tx']['hash']

def get_balance(ident):
  #logging.debug('getting balance for ident ' + ident)
  ident_hash256 = hashlib.sha256(ident).hexdigest()
  query = Cheque.query(Cheque.ident_sha256 == ident_hash256).fetch(1)
  if len(query) == 0:
    return None, None
  cheque = query[0]
  try:
    address_overview = get_address_overview(cheque.public_address)
  except Exception as e:
    logging.error(e)
    return None, None
  return address_overview['final_balance'], cheque.public_address

def get_fees(balance):
  if (balance is None) or (balance == 0):
    return 0, 0

  try:
    high_fees = int(get_blockchain_overview()['high_fee_per_kb'])
    medium_fees = int(get_blockchain_overview()['medium_fee_per_kb'])
    low_fees = int(get_blockchain_overview()['low_fee_per_kb'])
    # transaction size with 1 input, 2 outputs is below 0.150kB
    transaction_fee = int(math.ceil(0.2 * float(high_fees) * 0.01) * 100)
  except Exception as e:
    logging.error(e)
    return 0, 0

  if int(balance * SERVICE_FEE) < SERVICE_FEE_LOWER_LIMIT:
    service_fee = 0
  else:
    service_fee = int(balance * SERVICE_FEE)   # lower limit for transaction is 546 satoshis

  return service_fee, transaction_fee

def validate_btc_address(address):
  try:
    address_overview = get_address_overview(address)
  except Exception as e:
    return False
  return True

def get_exchange_rate_usd():
  try:
    #get usd exchange rate
    ticker_url = 'https://blockchain.info/ticker'
    req = urllib2.Request(ticker_url)
    response = urllib2.urlopen(req)
    result = json.load(response)
    return float(result['USD']['last'])
  except Exception as e:
    logging.error(e)
    return 1.0


def redeem(ident, verification_code, verification_index, receiver_address):
  logging.debug('redeeming ')
  logging.debug('verification_code ' + verification_code)
  logging.debug('verification_index ' + str(verification_index))
  logging.debug('receiver_address ' + receiver_address)
  ident_hash256 = hashlib.sha256(ident).hexdigest()
  logging.debug('ident_hash256 ' + ident_hash256)
  query = Cheque.query(Cheque.ident_sha256 == ident_hash256).fetch(1)
  if len(query) == 0:
    return None
  cheque = query[0]
  index_digits = cheque.verification_shifts.split(',')[int(verification_index)]
  logging.debug('index_digits ' + index_digits)
  verification_code_base = verification_master_decrypt(verification_code, index_digits)
  logging.debug('ident ' + ident)
  logging.debug('verification_code_base ' + verification_code_base)
  logging.debug('cheque.private_key_encrypted ' + cheque.private_key_encrypted)
  #try:
  private_key_sender = decrypt(cheque.private_key_encrypted, ident+verification_code_base)
  logging.debug('private_key_sender ' + private_key_sender)
  error_code, message = send_tx(private_key_sender, cheque.public_key, cheque.public_address, receiver_address)
  logging.debug('error_code ' + str(error_code))
  logging.debug('message ' + str(message))
    #address_overview = get_address_overview(cheque.public_address)
  #except:
    #return sys.exc_info()[0]
    #return 'redeem error'
  return error_code, message

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
    while True:
        ident = ''.join(random.choice(string.digits) for _ in range(15))
        ident_hash256 = hashlib.sha256(ident).hexdigest()
        query = Cheque.query(Cheque.ident_sha256 == ident_hash256).fetch(1)
        if len(query) == 0:
            break
    return ident

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

  return ident, verification_master, verification_shifts, key['private_key'], cheque


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
  if len(encrypted) != 6:
    return result
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
