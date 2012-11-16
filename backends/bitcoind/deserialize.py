# this code comes from ABE. it can probably be simplified
#
#

#from bitcoin import public_key_to_bc_address, hash_160_to_bc_address, hash_encode
#import socket
import time, hashlib
import struct
addrtype = 0


Hash = lambda x: hashlib.sha256(hashlib.sha256(x).digest()).digest()
hash_encode = lambda x: x[::-1].encode('hex')
hash_decode = lambda x: x.decode('hex')[::-1]

def hash_160(public_key):
    md = hashlib.new('ripemd160')
    md.update(hashlib.sha256(public_key).digest())
    return md.digest()

def public_key_to_bc_address(public_key):
    h160 = hash_160(public_key)
    return hash_160_to_bc_address(h160)

def hash_160_to_bc_address(h160):
    vh160 = chr(addrtype) + h160
    h = Hash(vh160)
    addr = vh160 + h[0:4]
    return b58encode(addr)

__b58chars = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
__b58base = len(__b58chars)

def b58encode(v):
    """ encode v, which is a string of bytes, to base58."""

    long_value = 0L
    for (i, c) in enumerate(v[::-1]):
        long_value += (256**i) * ord(c)

    result = ''
    while long_value >= __b58base:
        div, mod = divmod(long_value, __b58base)
        result = __b58chars[mod] + result
        long_value = div
    result = __b58chars[long_value] + result

    # Bitcoin does a little leading-zero-compression:
    # leading 0-bytes in the input become leading-1s
    nPad = 0
    for c in v:
        if c == '\0': nPad += 1
        else: break

    return (__b58chars[0]*nPad) + result

def b58decode(v, length):
    """ decode v into a string of len bytes."""
    long_value = 0L
    for (i, c) in enumerate(v[::-1]):
        long_value += __b58chars.find(c) * (__b58base**i)

    result = ''
    while long_value >= 256:
        div, mod = divmod(long_value, 256)
        result = chr(mod) + result
        long_value = div
    result = chr(long_value) + result

    nPad = 0
    for c in v:
        if c == __b58chars[0]: nPad += 1
        else: break

    result = chr(0)*nPad + result
    if length is not None and len(result) != length:
        return None

    return result


#
# Workalike python implementation of Bitcoin's CDataStream class.
#
import struct
import StringIO
import mmap

class SerializationError(Exception):
  """ Thrown when there's a problem deserializing or serializing """

class BCDataStream(object):
  def __init__(self):
    self.input = None
    self.read_cursor = 0

  def clear(self):
    self.input = None
    self.read_cursor = 0

  def write(self, bytes):  # Initialize with string of bytes
    if self.input is None:
      self.input = bytes
    else:
      self.input += bytes

  def map_file(self, file, start):  # Initialize with bytes from file
    self.input = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
    self.read_cursor = start
  def seek_file(self, position):
    self.read_cursor = position
  def close_file(self):
    self.input.close()

  def read_string(self):
    # Strings are encoded depending on length:
    # 0 to 252 :  1-byte-length followed by bytes (if any)
    # 253 to 65,535 : byte'253' 2-byte-length followed by bytes
    # 65,536 to 4,294,967,295 : byte '254' 4-byte-length followed by bytes
    # ... and the Bitcoin client is coded to understand:
    # greater than 4,294,967,295 : byte '255' 8-byte-length followed by bytes of string
    # ... but I don't think it actually handles any strings that big.
    if self.input is None:
      raise SerializationError("call write(bytes) before trying to deserialize")

    try:
      length = self.read_compact_size()
    except IndexError:
      raise SerializationError("attempt to read past end of buffer")

    return self.read_bytes(length)

  def write_string(self, string):
    # Length-encoded as with read-string
    self.write_compact_size(len(string))
    self.write(string)

  def read_bytes(self, length):
    try:
      result = self.input[self.read_cursor:self.read_cursor+length]
      self.read_cursor += length
      return result
    except IndexError:
      raise SerializationError("attempt to read past end of buffer")

    return ''

  def read_boolean(self): return self.read_bytes(1)[0] != chr(0)
  def read_int16(self): return self._read_num('<h')
  def read_uint16(self): return self._read_num('<H')
  def read_int32(self): return self._read_num('<i')
  def read_uint32(self): return self._read_num('<I')
  def read_int64(self): return self._read_num('<q')
  def read_uint64(self): return self._read_num('<Q')

  def write_boolean(self, val): return self.write(chr(1) if val else chr(0))
  def write_int16(self, val): return self._write_num('<h', val)
  def write_uint16(self, val): return self._write_num('<H', val)
  def write_int32(self, val): return self._write_num('<i', val)
  def write_uint32(self, val): return self._write_num('<I', val)
  def write_int64(self, val): return self._write_num('<q', val)
  def write_uint64(self, val): return self._write_num('<Q', val)

  def read_compact_size(self):
    size = ord(self.input[self.read_cursor])
    self.read_cursor += 1
    if size == 253:
      size = self._read_num('<H')
    elif size == 254:
      size = self._read_num('<I')
    elif size == 255:
      size = self._read_num('<Q')
    return size

  def write_compact_size(self, size):
    if size < 0:
      raise SerializationError("attempt to write size < 0")
    elif size < 253:
       self.write(chr(size))
    elif size < 2**16:
      self.write('\xfd')
      self._write_num('<H', size)
    elif size < 2**32:
      self.write('\xfe')
      self._write_num('<I', size)
    elif size < 2**64:
      self.write('\xff')
      self._write_num('<Q', size)

  def _read_num(self, format):
    (i,) = struct.unpack_from(format, self.input, self.read_cursor)
    self.read_cursor += struct.calcsize(format)
    return i

  def _write_num(self, format, num):
    s = struct.pack(format, num)
    self.write(s)

#
# enum-like type
# From the Python Cookbook, downloaded from http://code.activestate.com/recipes/67107/
#
import types, string, exceptions

class EnumException(exceptions.Exception):
    pass

class Enumeration:
    def __init__(self, name, enumList):
        self.__doc__ = name
        lookup = { }
        reverseLookup = { }
        i = 0
        uniqueNames = [ ]
        uniqueValues = [ ]
        for x in enumList:
            if type(x) == types.TupleType:
                x, i = x
            if type(x) != types.StringType:
                raise EnumException, "enum name is not a string: " + x
            if type(i) != types.IntType:
                raise EnumException, "enum value is not an integer: " + i
            if x in uniqueNames:
                raise EnumException, "enum name is not unique: " + x
            if i in uniqueValues:
                raise EnumException, "enum value is not unique for " + x
            uniqueNames.append(x)
            uniqueValues.append(i)
            lookup[x] = i
            reverseLookup[i] = x
            i = i + 1
        self.lookup = lookup
        self.reverseLookup = reverseLookup
    def __getattr__(self, attr):
        if not self.lookup.has_key(attr):
            raise AttributeError
        return self.lookup[attr]
    def whatis(self, value):
        return self.reverseLookup[value]


# This function comes from bitcointools, bct-LICENSE.txt.
def long_hex(bytes):
    return bytes.encode('hex_codec')

# This function comes from bitcointools, bct-LICENSE.txt.
def short_hex(bytes):
    t = bytes.encode('hex_codec')
    if len(t) < 11:
        return t
    return t[0:4]+"..."+t[-4:]



def parse_TxIn(vds):
  d = {}
  d['prevout_hash'] = hash_encode(vds.read_bytes(32))
  d['prevout_n'] = vds.read_uint32()
  scriptSig = vds.read_bytes(vds.read_compact_size())
  d['sequence'] = vds.read_uint32()
  # actually I don't need that at all
  # if not is_coinbase: d['address'] = extract_public_key(scriptSig)
  # d['script'] = decode_script(scriptSig)
  return d


def parse_TxOut(vds, i):
  d = {}
  d['value'] = vds.read_int64()
  scriptPubKey = vds.read_bytes(vds.read_compact_size())
  d['address'] = extract_public_key(scriptPubKey)
  #d['script'] = decode_script(scriptPubKey)
  d['raw_output_script'] = scriptPubKey.encode('hex')
  d['index'] = i
  return d


def parse_Transaction(vds, is_coinbase):
  d = {}
  start = vds.read_cursor
  d['version'] = vds.read_int32()
  n_vin = vds.read_compact_size()
  d['inputs'] = []
  for i in xrange(n_vin):
      o = parse_TxIn(vds)
      if not is_coinbase: 
          d['inputs'].append(o)
  n_vout = vds.read_compact_size()
  d['outputs'] = []
  for i in xrange(n_vout):
      o = parse_TxOut(vds, i)
      if o['address'] is not None:
          d['outputs'].append(o)
  d['lockTime'] = vds.read_uint32()
  return d




opcodes = Enumeration("Opcodes", [
    ("OP_0", 0), ("OP_PUSHDATA1",76), "OP_PUSHDATA2", "OP_PUSHDATA4", "OP_1NEGATE", "OP_RESERVED",
    "OP_1", "OP_2", "OP_3", "OP_4", "OP_5", "OP_6", "OP_7",
    "OP_8", "OP_9", "OP_10", "OP_11", "OP_12", "OP_13", "OP_14", "OP_15", "OP_16",
    "OP_NOP", "OP_VER", "OP_IF", "OP_NOTIF", "OP_VERIF", "OP_VERNOTIF", "OP_ELSE", "OP_ENDIF", "OP_VERIFY",
    "OP_RETURN", "OP_TOALTSTACK", "OP_FROMALTSTACK", "OP_2DROP", "OP_2DUP", "OP_3DUP", "OP_2OVER", "OP_2ROT", "OP_2SWAP",
    "OP_IFDUP", "OP_DEPTH", "OP_DROP", "OP_DUP", "OP_NIP", "OP_OVER", "OP_PICK", "OP_ROLL", "OP_ROT",
    "OP_SWAP", "OP_TUCK", "OP_CAT", "OP_SUBSTR", "OP_LEFT", "OP_RIGHT", "OP_SIZE", "OP_INVERT", "OP_AND",
    "OP_OR", "OP_XOR", "OP_EQUAL", "OP_EQUALVERIFY", "OP_RESERVED1", "OP_RESERVED2", "OP_1ADD", "OP_1SUB", "OP_2MUL",
    "OP_2DIV", "OP_NEGATE", "OP_ABS", "OP_NOT", "OP_0NOTEQUAL", "OP_ADD", "OP_SUB", "OP_MUL", "OP_DIV",
    "OP_MOD", "OP_LSHIFT", "OP_RSHIFT", "OP_BOOLAND", "OP_BOOLOR",
    "OP_NUMEQUAL", "OP_NUMEQUALVERIFY", "OP_NUMNOTEQUAL", "OP_LESSTHAN",
    "OP_GREATERTHAN", "OP_LESSTHANOREQUAL", "OP_GREATERTHANOREQUAL", "OP_MIN", "OP_MAX",
    "OP_WITHIN", "OP_RIPEMD160", "OP_SHA1", "OP_SHA256", "OP_HASH160",
    "OP_HASH256", "OP_CODESEPARATOR", "OP_CHECKSIG", "OP_CHECKSIGVERIFY", "OP_CHECKMULTISIG",
    "OP_CHECKMULTISIGVERIFY",
    ("OP_SINGLEBYTE_END", 0xF0),
    ("OP_DOUBLEBYTE_BEGIN", 0xF000),
    "OP_PUBKEY", "OP_PUBKEYHASH",
    ("OP_INVALIDOPCODE", 0xFFFF),
])

def script_GetOp(bytes):
  i = 0
  while i < len(bytes):
    vch = None
    opcode = ord(bytes[i])
    i += 1
    if opcode >= opcodes.OP_SINGLEBYTE_END:
      opcode <<= 8
      opcode |= ord(bytes[i])
      i += 1

    if opcode <= opcodes.OP_PUSHDATA4:
      nSize = opcode
      if opcode == opcodes.OP_PUSHDATA1:
        nSize = ord(bytes[i])
        i += 1
      elif opcode == opcodes.OP_PUSHDATA2:
        (nSize,) = struct.unpack_from('<H', bytes, i)
        i += 2
      elif opcode == opcodes.OP_PUSHDATA4:
        (nSize,) = struct.unpack_from('<I', bytes, i)
        i += 4
      vch = bytes[i:i+nSize]
      i += nSize

    yield (opcode, vch, i)

def script_GetOpName(opcode):
  return (opcodes.whatis(opcode)).replace("OP_", "")

def decode_script(bytes):
  result = ''
  for (opcode, vch, i) in script_GetOp(bytes):
    if len(result) > 0: result += " "
    if opcode <= opcodes.OP_PUSHDATA4:
      result += "%d:"%(opcode,)
      result += short_hex(vch)
    else:
      result += script_GetOpName(opcode)
  return result

def match_decoded(decoded, to_match):
  if len(decoded) != len(to_match):
    return False;
  for i in range(len(decoded)):
    if to_match[i] == opcodes.OP_PUSHDATA4 and decoded[i][0] <= opcodes.OP_PUSHDATA4:
      continue  # Opcodes below OP_PUSHDATA4 all just push data onto stack, and are equivalent.
    if to_match[i] != decoded[i][0]:
      return False
  return True

def extract_public_key(bytes):
  decoded = [ x for x in script_GetOp(bytes) ]

  # non-generated TxIn transactions push a signature
  # (seventy-something bytes) and then their public key
  # (65 bytes) onto the stack:
  match = [ opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4 ]
  if match_decoded(decoded, match):
    return public_key_to_bc_address(decoded[1][1])

  # The Genesis Block, self-payments, and pay-by-IP-address payments look like:
  # 65 BYTES:... CHECKSIG
  match = [ opcodes.OP_PUSHDATA4, opcodes.OP_CHECKSIG ]
  if match_decoded(decoded, match):
    return public_key_to_bc_address(decoded[0][1])

  # Pay-by-Bitcoin-address TxOuts look like:
  # DUP HASH160 20 BYTES:... EQUALVERIFY CHECKSIG
  match = [ opcodes.OP_DUP, opcodes.OP_HASH160, opcodes.OP_PUSHDATA4, opcodes.OP_EQUALVERIFY, opcodes.OP_CHECKSIG ]
  if match_decoded(decoded, match):
    return hash_160_to_bc_address(decoded[2][1])

  #raise BaseException("address not found in script") see ce35795fb64c268a52324b884793b3165233b1e6d678ccaadf760628ec34d76b
  return "(None)"