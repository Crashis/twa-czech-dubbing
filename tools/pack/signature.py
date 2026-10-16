"""Verify the RSA-2048/PKCS#1 v1.5 SHA-256 signature on an Arena file index.

The public key is recovered from the user's local game.dll. No private key,
signature generation, engine patching, or integrity-check bypass is provided.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
from tools.resources import ROOT

KEY_PATH = ROOT/'data/arena-index-public-key.json'
DIGEST_INFO = bytes.fromhex('3031300d060960864801650304020105000420')
EXPECTED_PUBLIC_KEY_DER_SHA256 = 'b509e5f323caa5f9638aad641c12ef9bb19cf182211143a1665c9312a8d302e6'

def tlv(data, offset, expected_tag):
    if offset+2 > len(data) or data[offset] != expected_tag:
        raise ValueError('Unexpected or truncated DER tag')
    length = data[offset+1]
    start = offset+2
    if length & 0x80:
        width = length & 0x7f
        if width == 0 or width > 4 or start+width > len(data):
            raise ValueError('Invalid DER length')
        length = int.from_bytes(data[start:start+width], 'big')
        start += width
    if start+length > len(data):
        raise ValueError('Truncated DER value')
    return data[start:start+length], start+length

def parse_public_key(der):
    outer, end = tlv(der, 0, 0x30)
    if end != len(der):
        raise ValueError('Trailing key data')
    algorithm, end = tlv(outer, 0, 0x30)
    if algorithm != bytes.fromhex('06092a864886f70d0101010500'):
        raise ValueError('Not an RSA public key')
    bit_string, end = tlv(outer, end, 0x03)
    if end != len(outer) or bit_string[:1] != b'\0':
        raise ValueError('Invalid public key bit string')
    integers, end = tlv(bit_string[1:], 0, 0x30)
    if end != len(bit_string)-1:
        raise ValueError('Trailing RSA key data')
    modulus, end = tlv(integers, 0, 0x02)
    exponent, end = tlv(integers, end, 0x02)
    if end != len(integers):
        raise ValueError('Trailing RSA integers')
    return int.from_bytes(modulus, 'big'), int.from_bytes(exponent, 'big')

def verify(index, signature, modulus, exponent):
    width = (modulus.bit_length()+7)//8
    if width != 256 or len(signature) != width:
        return False
    value = int.from_bytes(signature, 'big')
    if value >= modulus:
        return False
    recovered = pow(value, exponent, modulus).to_bytes(width, 'big')
    info = DIGEST_INFO + hashlib.sha256(index).digest()
    expected = b'\x00\x01' + b'\xff'*(width-len(info)-3) + b'\x00' + info
    return recovered == expected

def load_key():
    value = json.loads(KEY_PATH.read_text(encoding='utf-8'))
    der = base64.b64decode(value['der_base64'], validate=True)
    if hashlib.sha256(der).hexdigest() != value['der_sha256'] or value['der_sha256'] != EXPECTED_PUBLIC_KEY_DER_SHA256:
        raise ValueError('Public key integrity mismatch')
    modulus, exponent = parse_public_key(der)
    if modulus.bit_length() != 2048 or exponent != 65537:
        raise ValueError('Unexpected Arena signature key')
    return modulus, exponent
