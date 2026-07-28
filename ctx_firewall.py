"""
Octron Context Firewall
Security layer that runs at startup to verify system integrity.
Checks that core identity files exist and haven't been tampered with.
"""

import os
import json
import hashlib


CORE_FILES = [
    "IDV2_core.txt",
]

# Hashes are persisted here after the first run and compared against on
# every run after that. Previously this was a hardcoded empty dict, so the
# "MODIFIED" check could never fire — this file is what makes it real.
HASH_STORE_PATH = ".octron_integrity.json"


def _file_hash(filepath: str) -> str:
    """Generate SHA-256 hash of a file."""
    if not os.path.exists(filepath):
        return "MISSING"
    with open(filepath, "r", encoding="utf-8") as f:
        return hashlib.sha256(f.read().encode("utf-8")).hexdigest()


def _load_known_hashes() -> dict:
    if not os.path.exists(HASH_STORE_PATH):
        return {}
    try:
        with open(HASH_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_known_hashes(hashes: dict) -> None:
    try:
        with open(HASH_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(hashes, f, indent=2)
    except OSError:
        pass


def run_firewall_check():
    """
    Startup security check:
    1. Verifies core identity files exist
    2. Checks for unexpected modifications since the last verified run
    3. Warns about missing components
    """
    print("\n[FIREWALL] Running integrity check...")
    issues = []
    known_hashes = _load_known_hashes()
    dirty = False

    for filepath in CORE_FILES:
        if not os.path.exists(filepath):
            issues.append(f"  MISSING: {filepath}")
            continue

        current = _file_hash(filepath)
        known = known_hashes.get(filepath)

        if known is None:
            # First time seeing this file — trust it and record its hash.
            known_hashes[filepath] = current
            dirty = True
        elif current != known:
            issues.append(f"  MODIFIED: {filepath} (hash mismatch vs. last verified run)")

    # Check Qdrant data directory
    if not os.path.exists("./qdrant_data"):
        issues.append("  WARNING: No memory database found. First run?")

    if dirty:
        _save_known_hashes(known_hashes)

    if issues:
        print("[FIREWALL] Issues detected:")
        for issue in issues:
            print(issue)
        print("[FIREWALL] Proceeding with caution.\n")
    else:
        print("[FIREWALL] All systems nominal.\n")
