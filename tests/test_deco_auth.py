"""
Quick CLI test for the TP-Link Deco auth flow.

Run from the project root:
    .venv311/Scripts/python.exe test_deco_auth.py

Steps are printed individually so you can see exactly where a failure occurs
before the UI integration is trusted.
"""

import getpass
import json
import sys

HOST_DEFAULT = "192.168.68.1"


def main():
    import argparse, requests

    parser = argparse.ArgumentParser(description="Test Deco auth flow step-by-step")
    parser.add_argument("--host",     default="",  help="Gateway IP (default: prompt)")
    parser.add_argument("--password", default="",  help="TP-Link ID password (default: prompt)")
    args = parser.parse_args()

    host     = args.host.strip()     or input(f"Gateway IP [{HOST_DEFAULT}]: ").strip() or HOST_DEFAULT
    password = args.password.strip() or getpass.getpass("Password (TP-Link ID): ").strip()
    if not password:
        print("  (getpass returned empty — falling back to visible input)")
        password = input("Password (visible): ").strip()
    if not password:
        print("ERROR: password is required")
        sys.exit(1)

    base = f"http://{host}/cgi-bin/luci/;stok=/login"
    session = requests.Session()
    session.headers.update({"Referer": f"http://{host}/"})

    # ── Step 1: ?form=keys ────────────────────────────────────────────────────
    print("\n-- Step 1: POST ?form=keys --")
    r = session.post(base, params={"form": "keys"}, json={"operation": "read"}, timeout=10)
    print(f"  Status : {r.status_code}")
    keys_body = r.json()
    print(f"  Body   : {json.dumps(keys_body)[:400]}")

    # Parse RSA password key
    pw_n, pw_e = _extract_rsa(keys_body, "keys")
    print(f"  n bits : {pw_n.bit_length()}")
    print(f"  e      : {hex(pw_e)}")

    # ── Step 2: ?form=auth ────────────────────────────────────────────────────
    print("\n-- Step 2: POST ?form=auth --")
    r = session.post(base, params={"form": "auth"}, json={"operation": "read"}, timeout=10)
    print(f"  Status : {r.status_code}")
    auth_body = r.json()
    print(f"  Body   : {json.dumps(auth_body)[:400]}")

    sig_n, sig_e = _extract_rsa(auth_body, "auth")
    seq_raw = (
        auth_body.get("seq")
        or (auth_body.get("result") or {}).get("seq")
        or 0
    )
    seq = int(seq_raw)
    print(f"  sig n bits : {sig_n.bit_length()}")
    print(f"  sig e      : {hex(sig_e)}")
    print(f"  seq        : {seq}")

    # ── Step 3: build login request ───────────────────────────────────────────
    print("\n-- Step 3: build + POST ?form=login --")
    import hashlib, random, base64
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as _cpad
    from cryptography.hazmat.primitives.asymmetric import padding as _rpad
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

    # AES session key / IV
    lo, hi = 10 ** 15, 10 ** 16 - 1
    aes_key = str(random.randint(lo, hi))
    aes_iv  = str(random.randint(lo, hi))
    print(f"  aes_key : {aes_key}")
    print(f"  aes_iv  : {aes_iv}")

    # RSA-encrypt password
    pw_hex = _rsa_block(password.encode(), pw_n, pw_e).upper()
    print(f"  pw_hex  : {pw_hex[:32]}… ({len(pw_hex)} chars)")

    # Hash = MD5(username + plaintext_password) — per tpEncrypt.js setHash(user, pw)
    username = keys_body.get("result", {}).get("username", "")
    pw_hash  = hashlib.md5((username + password).encode()).hexdigest()
    print(f"  username: {username!r}  hash: {pw_hash}")

    # Deco inner payload: {"params": {"password": crypted_pwd}, "operation": "login"}
    # Source: tplinkrouterc6u/client/deco.py _get_login_data()
    payload_str = json.dumps({"params": {"password": pw_hex}, "operation": "login"})

    # Try two sign formats: legacy (k=/i=) and modern MR (key=/iv=)
    def _build_variants(payload):
        d = _aes_enc(payload, aes_key, aes_iv)
        s_legacy  = f"k={aes_key}&i={aes_iv}&h={pw_hash}&s={seq + len(d)}"
        s_modern  = f"key={aes_key}&iv={aes_iv}&h={pw_hash}&s={seq + len(d)}"
        sig_legacy = _rsa_block(s_legacy.encode(), sig_n, sig_e)
        sig_modern = _rsa_block(s_modern.encode(), sig_n, sig_e)
        print(f"  data_b64 ({len(d)} chars): {d[:40]}...")
        print(f"  sign_str legacy : {s_legacy[:80]}")
        print(f"  sign_str modern : {s_modern[:80]}")
        return d, sig_legacy, sig_modern

    data_b64, sign_legacy, sign_modern = _build_variants(payload_str)

    def _try_post(label, url, **kwargs):
        r = session.post(url, timeout=10, **kwargs)
        raw = r.text[:300]
        try:
            rj = r.json()
            d  = rj.get("data", "")
            if d and isinstance(d, str):
                try:
                    dec = _aes_dec(d, aes_key, aes_iv)
                    result = json.loads(dec)
                except Exception:
                    result = rj
            else:
                result = rj
        except Exception:
            result = {"_raw": raw}
        ec  = result.get("error_code", -99)
        msg = result.get("msg", result.get("_raw", ""))
        print(f"\n  [{label}]  status={r.status_code}  ec={ec}")
        print(f"    msg  : {str(msg)[:160]!r}")
        print(f"    full : {raw!r}")
        return r.status_code == 200 and ec == 0, result

    login_body = None
    login_url = f"http://{host}/cgi-bin/luci/;stok=/login"

    json_ct = {"Content-Type": "application/json"}

    # A: Deco payload + legacy sign, form-encoded body + Content-Type: application/json
    ok, res = _try_post("A deco legacy-sign JSON-CT", login_url,
                        params={"form": "login"},
                        data={"sign": sign_legacy, "data": data_b64},
                        headers=json_ct)
    if ok: login_body = res

    # B: same but no Content-Type override (default form-urlencoded)
    if not login_body:
        ok, res = _try_post("B deco legacy-sign form-CT", login_url,
                            params={"form": "login"},
                            data={"sign": sign_legacy, "data": data_b64})
        if ok: login_body = res

    # C: Old-style form string inner payload (operation=login&password=...&confirm=true)
    if not login_body:
        payload_old = f"operation=login&password={pw_hex}&confirm=true"
        d_old, sig_old_l, sig_old_m = _build_variants(payload_old)
        ok, res = _try_post("C old-form-str legacy-sign ?form=login", login_url,
                            params={"form": "login"},
                            data={"sign": sig_old_l, "data": d_old})
        if ok: login_body = res

    if not login_body:
        ok, res = _try_post("D old-form-str modern-sign ?form=login", login_url,
                            params={"form": "login"},
                            data={"sign": sig_old_m, "data": d_old})
        if ok: login_body = res

    # E: GET the raw login page and show what it returns
    print("\n-- Bonus: GET login page (no params) --")
    rg = session.get(f"http://{host}/cgi-bin/luci/;stok=/login", timeout=10)
    print(f"  status={rg.status_code}  body={rg.text[:300]!r}")

    if login_body is None:
        print("\nAll attempts failed. Capture browser network tab:")
        print("  1. Open http://192.168.68.1 in browser")
        print("  2. Open DevTools (F12) > Network tab")
        print("  3. Log in with your password")
        print("  4. Find the POST request and share: URL, headers, request body, response body")
        sys.exit(1)

    # Try to decrypt response — stok can be at data.stok or result.stok
    resp_data = login_body.get("data", "")
    if resp_data and isinstance(resp_data, str):
        try:
            plain  = _aes_dec(resp_data, aes_key, aes_iv)
            result = json.loads(plain)
            print(f"  Decrypted: {json.dumps(result)[:300]}")
            ec = result.get("error_code", -1)
            if ec == 0:
                stok = (result.get("data") or result.get("result") or {}).get("stok", "?")
                print(f"\n✓  LOGIN OK  stok={stok}")
            else:
                print(f"\n✗  error_code={ec}")
        except Exception as e:
            print(f"  Decrypt failed: {e}")
    else:
        print("  (no 'data' field in response — may be plain JSON)")
        ec = login_body.get("error_code", -1)
        if ec == 0:
            stok = (login_body.get("data") or login_body.get("result") or {}).get("stok", "?")
            print(f"\n✓  LOGIN OK  stok={stok}")
        else:
            print(f"\n✗  error_code={ec}")


# ── helpers ────────────────────────────────────────────────────────────────────

def _extract_rsa(body: dict, label: str):
    """Try all known response shapes and return (n_int, e_int)."""
    # XE75: result.password list
    result_obj = body.get("result", {})
    if isinstance(result_obj, dict):
        for field in ("password", "key", "keys", "rsa_key"):
            val = result_obj.get(field)
            if isinstance(val, list) and len(val) >= 2:
                try:
                    return int(val[0], 16), int(val[1], 16)
                except Exception:
                    pass
    # X90: data list
    data = body.get("data")
    if isinstance(data, list) and len(data) >= 2:
        try:
            return int(data[0], 16), int(data[1], 16)
        except Exception:
            pass
    # dict format
    if isinstance(data, dict):
        try:
            return int(data["n"], 16), int(data["e"], 16)
        except Exception:
            pass
    print(f"  ✗  Could not parse RSA key from {label} response: {body!r:.300}")
    sys.exit(1)


def _rsa_block(data: bytes, n: int, e: int) -> str:
    from cryptography.hazmat.primitives.asymmetric import padding as _rpad
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
    pub = RSAPublicNumbers(e, n).public_key()
    key_bytes  = (n.bit_length() + 7) // 8
    block_size = key_bytes - 11
    result = b""
    for i in range(0, len(data), block_size):
        result += pub.encrypt(data[i : i + block_size], _rpad.PKCS1v15())
    return result.hex()


def _aes_enc(plain: str, key: str, iv: str) -> str:
    import base64
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as _cpad
    padder = _cpad.PKCS7(128).padder()
    padded = padder.update(plain.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode()))
    enc    = cipher.encryptor()
    return base64.b64encode(enc.update(padded) + enc.finalize()).decode()


def _aes_dec(b64: str, key: str, iv: str) -> str:
    import base64
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as _cpad
    raw    = base64.b64decode(b64)
    cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode()))
    dec    = cipher.decryptor()
    padded = dec.update(raw) + dec.finalize()
    try:
        unpadder = _cpad.PKCS7(128).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode()
    except Exception:
        return padded.rstrip(b"\x00").decode()


if __name__ == "__main__":
    main()
