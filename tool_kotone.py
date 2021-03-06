#!/usr/bin/env python
# coding: utf8
"""
* tool_kotone.py
* Author: stal, stqism; April 2014
* Copyright (c) 2014 Zodiac Labs.
* Further licensing information: see LICENSE.
"""
import requests
import sys
import time
import mmap
import binascii
import json
import nacl.encoding as crypto_encode
import nacl.public as crypto
import os
import random
import base64

def _compute_checksum(data, iv=(0, 0)):
    checksum = list(iv)
    for ind, byte in enumerate(binascii.unhexlify(data)):
        checksum[ind % 2] ^= byte
    return "".join(hex(byte)[2:].zfill(2) for byte in checksum).upper()

def _read_tox_cherry(open_file):
    m = mmap.mmap(open_file.fileno(), 0, prot=mmap.PROT_READ)
    idx = m.find(b"KEYs") + 8
    m.seek(idx)
    bs = m.read(68)
    
    pk = binascii.hexlify(bs[:32]).upper().decode("ascii")
    sk = binascii.hexlify(bs[32:64]).upper().decode("ascii")
    ns = binascii.hexlify(bs[64:]).upper().decode("ascii")

    m.close()
    return (pk, sk, ns)

def _read_tox_mono(open_file):
    m = mmap.mmap(open_file.fileno(), 0, prot=mmap.PROT_READ)
    m.seek(0x10)
    bs = m.read(68)

    pk = binascii.hexlify(bs[4:36]).upper().decode("ascii")
    sk = binascii.hexlify(bs[36:]).upper().decode("ascii")
    ns = binascii.hexlify(bs[:4]).upper().decode("ascii")

    m.close()
    return (pk, sk, ns)

def read_tox(fil):
    with open(fil, "rb") as file_:
        magic = file_.read(4)
        print(repr(magic))
        if magic == "桜\x00".encode("utf8"):
            return _read_tox_cherry(file_)
        elif magic == b"\x00\x00\x00\x00":
            return _read_tox_mono(file_)

def push(addr, name, bio, fil):
    pkr = requests.get(addr + "/pk", verify=False)
    sk = pkr.json()["key"]

    mypub, mysec, nospam = read_tox(fil)
    check = _compute_checksum(mypub + nospam)
    print("kotone: Publishing {0}/{1} to server.".format(mypub, check))
    inner = json.dumps({
        "tox_id": mypub + nospam + check, # Public key + checksum
        "name": name, # Desired name
        "privacy": 1, # Privacy level (1 or higher appears in FindFriends)
        "bio": bio.strip(), # Bio (quote displayed on web)
        "timestamp": int(time.time()) # A timestamp near the server's time
    })
    
    k = crypto.PrivateKey(mysec, crypto_encode.HexEncoder)
    nonce = os.urandom(crypto.Box.NONCE_SIZE)
    b = crypto.Box(k, crypto.PublicKey(sk, crypto_encode.HexEncoder))
    msg = b.encrypt(inner.encode("utf8"), nonce, crypto_encode.Base64Encoder)
    
    payload = json.dumps({
        "action": 1, # Action number
        "public_key": mypub, # Public key
        "encrypted": msg.ciphertext.decode("utf8"), # Encrypted payload base64 (above)
        "nonce": crypto_encode.Base64Encoder.encode(nonce).decode("utf8") # b64
    })
    resp = requests.post(addr + "/api", data=payload, verify=False)
    a = resp.json()
    if a["c"] == 0:
        print("\033[32mOK:\033[0m record successfully published.")
        print("Password is '{0}'.".format(a["password"]))
    else:
        print("\033[32mFailed:\033[0m {0}".format(a["c"]))

def del_(addr, fil):
    pkr = requests.get(addr + "/pk", verify=False)
    sk = pkr.json()["key"]
    
    mypub, mysec, nospam = read_tox(fil)
    check = _compute_checksum(mypub + nospam)
    print("kotone: Deleting {0} from server.".format(mypub, check))
    inner = json.dumps({
        "public_key": mypub, # Public key
        "timestamp": int(time.time()) # Timestamp
    })
    
    k = crypto.PrivateKey(mysec, crypto_encode.HexEncoder)
    nonce = os.urandom(crypto.Box.NONCE_SIZE)
    b = crypto.Box(k, crypto.PublicKey(sk, crypto_encode.HexEncoder))
    msg = b.encrypt(inner.encode("utf8"), nonce, crypto_encode.Base64Encoder)
    
    payload = json.dumps({
        "action": 2,
        "public_key": mypub,
        "encrypted": msg.ciphertext.decode("utf8"),
        "nonce": crypto_encode.Base64Encoder.encode(nonce).decode("utf8")
    })
    resp = requests.post(addr + "/api", data=payload, verify=False)
    a = resp.json()
    if a["c"] == 0:
        print("\033[32mOK:\033[0m record deleted. "
              "It may take a minute to update.")
    else:
        print("\033[32mFailed:\033[0m {0}".format(a["c"]))

def r(addr):
    pkr = requests.get(addr + "/pk", verify=False)
    sk = pkr.json()["key"]

    k = crypto.PrivateKey.generate()
    mypub = k.public_key.encode(crypto_encode.HexEncoder).upper().decode("ascii")
    nospam = "00000000"

    check = _compute_checksum(mypub + nospam)
    print("kotone: Deleting {0} from server.".format(mypub, check))
    inner = json.dumps({
        "s": mypub + check,
        "t": int(time.time()),
        "n": "test-" + str(random.randint(0, 999999999)),
        "b": "top test :^)",
        "l": 1,
    })

    nonce = os.urandom(crypto.Box.NONCE_SIZE)
    b = crypto.Box(k, crypto.PublicKey(sk, crypto_encode.HexEncoder))
    msg = b.encrypt(inner.encode("utf8"), nonce, crypto_encode.Base64Encoder)

    payload = json.dumps({
        "a": 1,
        "k": mypub,
        "e": msg.ciphertext.decode("utf8"),
        "r": crypto_encode.Base64Encoder.encode(nonce).decode("utf8")
    })
    resp = requests.post(addr + "/api", data=payload, verify=False)
    print(resp.text)
    a = resp.json()
    if a["c"] == 0:
        print("\033[32mOK:\033[0m ")
    else:
        print("\033[32mFailed:\033[0m {0}".format(a["c"]))

def main():
    invocation, addr, action = sys.argv[:3]
    rest = sys.argv[3:]
    
    if action == "push":
        push(addr, *rest)
    elif action == "delete":
        del_(addr, *rest)
    elif action == "kek":
        r(addr)

if __name__ == '__main__':
    main()
