#!/usr/bin/env python3
"""Compute SHA-256 hash chain + Merkle root for docs/data/* and write manifest.sig."""
import os, json, hashlib

DATA = os.path.join(os.path.dirname(__file__), "..", "docs", "data")

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def merkle_root(hashes):
    if not hashes: return hashlib.sha256(b"").hexdigest()
    layer = [bytes.fromhex(h) for h in hashes]
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer), 2):
            a = layer[i]; b = layer[i+1] if i+1 < len(layer) else layer[i]
            nxt.append(hashlib.sha256(a+b).digest())
        layer = nxt
    return layer[0].hex()

def main():
    files_list = []
    for name in sorted(os.listdir(DATA)):
        p = os.path.join(DATA, name)
        if os.path.isfile(p) and not name.startswith(".") and name != "manifest.sig":
            files_list.append({"path": name, "sha256": sha256_file(p), "size": os.path.getsize(p)})
    root = merkle_root([f["sha256"] for f in files_list])
    sig = {
        "version": "1.0.0",
        "algorithm": "sha256",
        "merkle_root": f"sha256:{root}",
        "file_count": len(files_list),
        "files": files_list,
        "signature": "ed25519:PLACEHOLDER_NO_KEY_PROVISIONED"
    }
    with open(os.path.join(DATA, "manifest.sig"), "w") as f:
        json.dump(sig, f, indent=2)
    print(f"Merkle root: {root}")
    print(f"Files: {len(files_list)}")

if __name__ == "__main__":
    main()
