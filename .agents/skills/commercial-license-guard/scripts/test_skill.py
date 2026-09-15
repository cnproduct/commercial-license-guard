#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Evaluation & Regression Suite for commercial-license-guard
Runs EVAL-01 through EVAL-05 locally to verify security gates.
"""

import sys
import tempfile
import json
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from license_tool import get_machine_id, generate_keypair, issue_license, verify_license

def run_tests():
    print("=================================================================")
    print("🧪 Running Regression Suite for commercial-license-guard")
    print("=================================================================")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # 1. Keypair generation
        print("\n[EVAL-SETUP] Generating temporary RSA-2048 keypair...")
        generate_keypair(tmp_path)
        priv_key = tmp_path / "admin_private_key.pem"
        pub_key = tmp_path / "public_key.pem"
        assert priv_key.exists() and pub_key.exists()
        print("  ✅ Keypair generated successfully.")

        # 2. Machine ID
        mid = get_machine_id()
        assert mid.startswith("MID-")
        print(f"\n[EVAL-01] Local Machine ID extraction: {mid}")
        print("  ✅ Machine ID format verified.")

        # 3. Valid issuance and verification
        print("\n[EVAL-02] Issuing and verifying valid license key...")
        lic = issue_license(priv_key, mid, "Acme Corp", days=30)
        res = verify_license(pub_key, lic, current_mid=mid)
        assert res["valid"] is True
        assert res["name"] == "Acme Corp"
        print("  ✅ Valid license successfully verified.")

        # 4. Hardware Mismatch Detection
        print("\n[EVAL-03] Testing hardware mismatch interception...")
        alien_mid = "MID-9999-8888-7777-6666"
        res_mismatch = verify_license(pub_key, lic, current_mid=alien_mid)
        assert res_mismatch["valid"] is False
        assert "Hardware mismatch" in res_mismatch["error"]
        print(f"  ✅ Hardware mismatch correctly intercepted: {res_mismatch['error']}")

        # 5. Tamper-Proof Signature Detection
        print("\n[EVAL-04] Testing tamper-proof signature rejection...")
        tampered_lic = lic[:-5] + ("A" if lic[-5] != "A" else "B") + lic[-4:]
        res_tamper = verify_license(pub_key, tampered_lic, current_mid=mid)
        assert res_tamper["valid"] is False
        print("  ✅ Tampered license signature correctly rejected.")

        # 6. Expired License Handling
        print("\n[EVAL-05] Testing expired license rejection...")
        expired_lic = issue_license(priv_key, mid, "Expired Client", days=-1)
        res_exp = verify_license(pub_key, expired_lic, current_mid=mid)
        assert res_exp["valid"] is False
        assert "expired" in res_exp["error"]
        print(f"  ✅ Expired license correctly rejected: {res_exp['error']}")

    print("\n=================================================================")
    print("🎉 All 5/5 Evaluation & Security Gates Passed Successfully!")
    print("=================================================================")

if __name__ == "__main__":
    run_tests()
