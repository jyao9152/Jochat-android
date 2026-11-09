# -*- coding: utf-8 -*-
"""Fernet (AES-128-CBC + HMAC-SHA256) en Python pur, sans dépendance native.
Compatible avec cryptography.fernet (testé dans les deux sens)."""
import base64, hashlib, hmac, os, struct, time

def _xt(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1

def _mul(a, b):
    r = 0
    while b:
        if b & 1: r ^= a
        a = _xt(a); b >>= 1
    return r

def _sbox():
    S = [0] * 256; p = q = 1
    while True:
        p = (p ^ (p << 1) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        q ^= (q << 1) & 0xFF; q ^= (q << 2) & 0xFF; q ^= (q << 4) & 0xFF
        if q & 0x80: q ^= 0x09
        r = lambda x, s: ((x << s) | (x >> (8 - s))) & 0xFF
        S[p] = q ^ r(q, 1) ^ r(q, 2) ^ r(q, 3) ^ r(q, 4) ^ 0x63
        if p == 1: break
    S[0] = 0x63
    return S

S = _sbox()
X2 = [_xt(i) for i in range(256)]
M9, M11, M13, M14 = ([_mul(i, k) for i in range(256)] for k in (9, 11, 13, 14))
IS = [0] * 256
for _i, _v in enumerate(S): IS[_v] = _i

class AES128:
    def __init__(self, key):
        w = list(key); rc = 1
        for i in range(16, 176, 4):
            t = w[i - 4:i]
            if i % 16 == 0:
                t = [S[t[1]] ^ rc, S[t[2]], S[t[3]], S[t[0]]]; rc = _xt(rc)
            w += [w[i - 16 + j] ^ t[j] for j in range(4)]
        self.rk = [w[16 * r:16 * r + 16] for r in range(11)]

    def enc(self, b):
        s = [b[i] ^ self.rk[0][i] for i in range(16)]
        for r in range(1, 11):
            s = [S[x] for x in s]
            s = [s[((i // 4 + i % 4) % 4) * 4 + i % 4] for i in range(16)]
            if r < 10:
                m = []
                for c in range(4):
                    a = s[c * 4:c * 4 + 4]
                    m += [X2[a[0]] ^ X2[a[1]] ^ a[1] ^ a[2] ^ a[3],
                          a[0] ^ X2[a[1]] ^ X2[a[2]] ^ a[2] ^ a[3],
                          a[0] ^ a[1] ^ X2[a[2]] ^ X2[a[3]] ^ a[3],
                          X2[a[0]] ^ a[0] ^ a[1] ^ a[2] ^ X2[a[3]]]
                s = m
            s = [s[i] ^ self.rk[r][i] for i in range(16)]
        return bytes(s)

    def dec(self, b):
        s = [b[i] ^ self.rk[10][i] for i in range(16)]
        for r in range(9, -1, -1):
            s = [s[((i // 4 - i % 4) % 4) * 4 + i % 4] for i in range(16)]
            s = [IS[x] for x in s]
            s = [s[i] ^ self.rk[r][i] for i in range(16)]
            if r > 0:
                m = []
                for c in range(4):
                    a = s[c * 4:c * 4 + 4]
                    m += [M14[a[0]] ^ M11[a[1]] ^ M13[a[2]] ^ M9[a[3]],
                          M9[a[0]] ^ M14[a[1]] ^ M11[a[2]] ^ M13[a[3]],
                          M13[a[0]] ^ M9[a[1]] ^ M14[a[2]] ^ M11[a[3]],
                          M11[a[0]] ^ M13[a[1]] ^ M9[a[2]] ^ M14[a[3]]]
                s = m
        return bytes(s)

def pbkdf2(pw, salt, iters, dklen=32):
    """PBKDF2-HMAC-SHA256 (hashlib si disponible, sinon version Python pure)."""
    try:
        return hashlib.pbkdf2_hmac("sha256", pw, salt, iters, dklen)
    except Exception:
        base = hmac.new(pw, digestmod=hashlib.sha256)
        h = base.copy(); h.update(salt + struct.pack(">I", 1)); u = h.digest()
        acc = int.from_bytes(u, "big")
        for _ in range(iters - 1):
            h = base.copy(); h.update(u); u = h.digest(); acc ^= int.from_bytes(u, "big")
        return acc.to_bytes(32, "big")[:dklen]

class Fernet:
    def __init__(self, key):
        k = base64.urlsafe_b64decode(key)
        self.sig, self.aes = k[:16], AES128(k[16:])

    def encrypt(self, data):
        pad = 16 - len(data) % 16
        data += bytes([pad]) * pad
        iv = os.urandom(16); prev = iv; ct = b""
        for i in range(0, len(data), 16):
            blk = bytes(a ^ b for a, b in zip(data[i:i + 16], prev))
            prev = self.aes.enc(blk); ct += prev
        body = b"\x80" + struct.pack(">Q", int(time.time())) + iv + ct
        return base64.urlsafe_b64encode(body + hmac.new(self.sig, body, hashlib.sha256).digest())

    def decrypt(self, token):
        raw = base64.urlsafe_b64decode(token)
        body, mac = raw[:-32], raw[-32:]
        if not hmac.compare_digest(hmac.new(self.sig, body, hashlib.sha256).digest(), mac):
            raise ValueError("signature invalide")
        prev, ct = body[9:25], body[25:]; out = b""
        for i in range(0, len(ct), 16):
            blk = ct[i:i + 16]
            out += bytes(a ^ b for a, b in zip(self.aes.dec(blk), prev)); prev = blk
        return out[:-out[-1]]
