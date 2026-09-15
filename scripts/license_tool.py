#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
Commercial License Tool (Hardware Fingerprinting & Cryptographic Licensing)
==============================================================================
Provides zero-infrastructure, cryptographically tamper-proof commercial licensing:
- Machine ID extraction (Windows, macOS, Linux fallback)
- RSA-2048 keypair generation (PSS padding + SHA-256)
- Base64 license issuance with digital signature
- Offline verification with anti-time-rollback detection
==============================================================================
"""

import os
import sys
import json
import base64
import hashlib
import datetime
import argparse
import subprocess
import platform
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

def get_machine_id() -> str:
    """Extract deterministic, immutable hardware fingerprint for the local machine."""
    components = [platform.node(), platform.machine(), platform.processor()]
    system = platform.system().lower()

    if system == "windows":
        # 1. Motherboard UUID
        try:
            cmd = "powershell -NoProfile -Command \"(Get-CimInstance -Class Win32_ComputerSystemProduct).UUID\""
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                components.append(out)
        except Exception:
            pass

        # 2. CPU Processor ID
        try:
            cmd = "powershell -NoProfile -Command \"(Get-CimInstance -Class Win32_Processor).ProcessorId\""
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                components.append(out)
        except Exception:
            pass

        # 3. System Drive Volume Serial Number
        try:
            cmd = "powershell -NoProfile -Command \"(Get-CimInstance -Class Win32_LogicalDisk -Filter 'DeviceID=\"\"C:\"\"').VolumeSerialNumber\""
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                components.append(out)
        except Exception:
            pass

    elif system == "darwin":
        try:
            cmd = "ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ { split($0, line, \"\\\"\"); print line[4] }'"
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                components.append(out)
        except Exception:
            pass

    elif system == "linux":
        for p in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            if os.path.exists(p):
                try:
                    with open(p, "r") as f:
                        components.append(f.read().strip())
                        break
                except Exception:
                    pass

    raw_fingerprint = ":".join(str(c) for c in components if c)
    salted = f"SALT_LIC_COMMERCIAL_V3::{raw_fingerprint}::STATIC_PEPPER_2026"
    digest = hashlib.sha256(salted.encode("utf-8")).hexdigest().upper()
    mid = f"MID-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"
    return mid

def generate_keypair(out_dir: Path):
    """Generate RSA-2048 private key (stays local with vendor) and public key (embedded)."""
    if not HAS_CRYPTO:
        print("[-] Error: 'cryptography' package is required for keypair generation. Run: pip install cryptography")
        sys.exit(1)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    priv_path = out_dir / "admin_private_key.pem"
    pub_path = out_dir / "public_key.pem"

    with open(priv_path, "wb") as f:
        f.write(priv_pem)
    with open(pub_path, "wb") as f:
        f.write(pub_pem)

    print(f"[+] RSA-2048 Private Key generated: {priv_path} (KEEP STRICTLY CONFIDENTIAL!)")
    print(f"[+] RSA-2048 Public Key generated: {pub_path} (Safe to bundle with client code)")

def issue_license(private_key_path: Path, mid: str, name: str, days: int = 365, max_sessions: int = 1) -> str:
    """Issue a cryptographically signed Base64 license token."""
    if not HAS_CRYPTO:
        print("[-] Error: 'cryptography' package required.")
        sys.exit(1)

    if not private_key_path.exists():
        print(f"[-] Error: Private key not found at {private_key_path}")
        sys.exit(1)

    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), None)

    now = datetime.datetime.now()
    exp = now + datetime.timedelta(days=days)

    payload = {
        "v": "2.0",
        "mid": mid,
        "name": name,
        "max_s": max_sessions,
        "iat": now.strftime("%Y-%m-%d %H:%M:%S"),
        "exp": exp.strftime("%Y-%m-%d %H:%M:%S"),
        "perm": ["listing", "pricing", "stocks", "fast_list"]
    }

    payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    signature = private_key.sign(
        payload_json,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )

    token_dict = {
        "p": payload,
        "s": base64.b64encode(signature).decode('utf-8')
    }

    token_b64 = base64.b64encode(json.dumps(token_dict, separators=(',', ':')).encode('utf-8')).decode('utf-8')
    return f"LIC-RSA-{token_b64}"

def verify_license(public_key_path: Path, license_key: str, current_mid: str = None) -> dict:
    """Verify license signature, hardware binding, expiration date, and clock rollback."""
    if not HAS_CRYPTO:
        return {"valid": False, "error": "'cryptography' package is missing"}

    if not license_key.startswith("LIC-RSA-"):
        return {"valid": False, "error": "Invalid license prefix. Expected 'LIC-RSA-'"}

    raw_b64 = license_key[len("LIC-RSA-"):]
    try:
        token_dict = json.loads(base64.b64decode(raw_b64).decode('utf-8'))
        payload = token_dict["p"]
        signature = base64.b64decode(token_dict["s"])
    except Exception as e:
        return {"valid": False, "error": f"Malformed license payload: {e}"}

    if not public_key_path.exists():
        return {"valid": False, "error": f"Public key not found at {public_key_path}"}

    with open(public_key_path, "rb") as f:
        public_key = serialization.load_pem_public_key(f.read())

    payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')

    try:
        public_key.verify(
            signature,
            payload_json,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
    except InvalidSignature:
        return {"valid": False, "error": "Signature verification failed: Tampered or forged license!"}

    # 1. Anti-Clock-Skew Check (Clock Rollback Prevention)
    now = datetime.datetime.now()
    iat = datetime.datetime.strptime(payload["iat"], "%Y-%m-%d %H:%M:%S")
    if now < iat - datetime.timedelta(minutes=10):
        return {"valid": False, "error": "System clock rollback detected! Local time is earlier than license issue date."}

    # 2. Expiration Check
    exp = datetime.datetime.strptime(payload["exp"], "%Y-%m-%d %H:%M:%S")
    if now > exp:
        return {"valid": False, "error": f"License expired on {payload['exp']}"}

    # 3. Hardware Fingerprint Binding Check
    if current_mid is None:
        current_mid = get_machine_id()

    bound_mid = payload.get("mid")
    if bound_mid and bound_mid != current_mid:
        return {
            "valid": False,
            "error": f"Hardware mismatch: License bound to {bound_mid}, but current machine is {current_mid}."
        }

    return {
        "valid": True,
        "name": payload.get("name"),
        "mid": bound_mid,
        "expires_at": payload.get("exp"),
        "max_sessions": payload.get("max_s", 1),
        "permissions": payload.get("perm", [])
    }

def main():
    parser = argparse.ArgumentParser(description="Commercial License Management Tool")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("machine-id", help="Print local machine hardware fingerprint (MID)")

    kp_parser = subparsers.add_parser("keygen", help="Generate RSA-2048 private & public keypair")
    kp_parser.add_argument("--out-dir", default=".", help="Directory to save keys")

    gen_parser = subparsers.add_parser("generate", help="Issue a commercial signed license")
    gen_parser.add_argument("--key-path", default="admin_private_key.pem", help="Path to admin_private_key.pem")
    gen_parser.add_argument("--mid", required=True, help="Target machine hardware ID")
    gen_parser.add_argument("--name", required=True, help="Customer name / identifier")
    gen_parser.add_argument("--days", type=int, default=365, help="Validity period in days")
    gen_parser.add_argument("--max-sessions", type=int, default=1, help="Allowed concurrent session windows")

    v_parser = subparsers.add_parser("verify", help="Verify a license key")
    v_parser.add_argument("--key", required=True, help="The license key to verify")
    v_parser.add_argument("--pubkey-path", default="public_key.pem", help="Path to public_key.pem")

    args = parser.parse_args()

    if args.command == "machine-id":
        mid = get_machine_id()
        print(f"Machine ID: {mid}")

    elif args.command == "keygen":
        generate_keypair(Path(args.out_dir))

    elif args.command == "generate":
        lic = issue_license(Path(args.key_path), args.mid, args.name, days=args.days, max_sessions=args.max_sessions)
        print("\n========================================================")
        print("Generated Commercial License Key:")
        print("========================================================")
        print(lic)
        print("========================================================\n")

    elif args.command == "verify":
        res = verify_license(Path(args.pubkey_path), args.key)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
