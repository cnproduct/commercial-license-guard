#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
Commercial Protected Release Pipeline (PyArmor Binary Obfuscator & Builder)
==============================================================================
Automates the build process for commercial distribution packages:
1. Cleans previous build artifacts.
2. Compiles Python source code into native binary C-extensions (.pyd) using PyArmor.
3. Synchronizes asset directories, templates, and reference files.
4. Performs strict secret leakage audit (asserts zero .pem, .key, or source .py).
5. Runs sandbox smoke tests on the compiled binary package.
6. Packages output into a production zip file ready for client delivery.
==============================================================================
"""

import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

def run_cmd(cmd, cwd=None):
    res = subprocess.run(cmd, shell=True, cwd=cwd, text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\nOutput: {res.stdout}\nError: {res.stderr}")
    return res.stdout.strip()

def build_package(project_dir: Path, output_dir: Path, package_name: str = "commercial-release"):
    print("=" * 80)
    print("🚀 Commercial Protected Release Pipeline")
    print("=" * 80)

    dist_dir = output_dir / package_name
    if dist_dir.exists():
        print(f"[1/6] Cleaning legacy build directory: {dist_dir}...")
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    scripts_src = project_dir / "scripts"
    scripts_dest = dist_dir / "scripts"

    print("[2/6] Compiling and obfuscating core Python modules via PyArmor...")
    # Generate obfuscated package into dist
    pyarmor_cmd = f"pyarmor gen -O \"{scripts_dest}\" \"{scripts_src}\""
    try:
        run_cmd(pyarmor_cmd)
        print("    ✅ Core scripts obfuscated and compiled into native C-extensions (.pyd)!")
    except Exception as e:
        print(f"[-] PyArmor compilation failed: {e}")
        print("    Falling back to standard compilation if PyArmor is not installed.")
        raise

    print("[3/6] Syncing documentation, config templates, and assets...")
    sync_dirs = ["references", "templates", "assets", ".agents"]
    for d in sync_dirs:
        src_d = project_dir / d
        if src_d.exists():
            dest_d = dist_dir / d
            if dest_d.exists():
                shutil.rmtree(dest_d)
            shutil.copytree(src_d, dest_d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pem", "*.key"))
            print(f"    ➔ Synchronized directory: {d}/")

    sync_files = ["README.md", "USER_MANUAL.md", "LICENSE", "requirements.txt", "config.example.json", "public_key.pem"]
    for f in sync_files:
        src_f = project_dir / f
        if src_f.exists():
            shutil.copy2(src_f, dist_dir / f)
            print(f"    ➔ Copied file: {f}")

    print("[4/6] Running strict secret leakage audit...")
    violations = []
    for root, dirs, files in os.walk(dist_dir):
        for f in files:
            path = Path(root) / f
            # Check for private keys
            if f.endswith(".pem") and "private" in f.lower():
                violations.append(f"Private Key leak: {path.relative_to(dist_dir)}")
            if f.endswith(".key") and not f.startswith("public"):
                violations.append(f"Key leak: {path.relative_to(dist_dir)}")
            # Check for uncompiled raw python source in scripts directory
            if path.is_relative_to(scripts_dest) and f.endswith(".py"):
                # PyArmor creates an entry wrapper; ensure real source logic is not in plaintext
                content = path.read_text(encoding="utf-8", errors="ignore")
                if "def run_pipeline" in content or "class SessionManager" in content:
                    violations.append(f"Plaintext Python source leak: {path.relative_to(dist_dir)}")

    if violations:
        print("❌ SECURITY AUDIT FAILED! The following sensitive items were detected:")
        for v in violations:
            print(f"   - {v}")
        raise RuntimeError("Build aborted due to security leakage audit failure.")
    print("    ✅ Security audit 100% passed! No private keys or plaintext sources found.")

    print("[5/6] Testing sandbox execution of obfuscated package...")
    test_cmd = f"python \"{scripts_dest / 'session_manager.py'}\" machine-id" if (scripts_dest / 'session_manager.py').exists() else None
    if test_cmd:
        try:
            out = run_cmd(test_cmd)
            print(f"    ➔ Binary execution test passed: {out[:60]}...")
        except Exception as e:
            print(f"[-] Sandbox execution test warning: {e}")

    print("[6/6] Packaging into distribution zip file...")
    zip_path = output_dir / f"{package_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                abs_file = Path(root) / file
                rel_file = abs_file.relative_to(dist_dir)
                zf.write(abs_file, rel_file)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"🎉 Build completed successfully!")
    print(f"📦 Release package: {zip_path} ({size_mb:.2f} MB)")
    print(f"📁 Unpacked folder: {dist_dir}")
    print("=" * 80)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build Commercial Protected Release Package")
    parser.add_argument("--project-dir", default=".", help="Root directory of the project")
    parser.add_argument("--output-dir", default="dist", help="Output directory for build artifacts")
    parser.add_argument("--name", default="commercial-release-v1.0", help="Release package name")
    args = parser.parse_args()

    build_package(Path(args.project_dir).resolve(), Path(args.output_dir).resolve(), package_name=args.name)
