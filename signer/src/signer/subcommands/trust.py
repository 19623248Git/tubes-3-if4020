import json
import os
from pathlib import Path
import sys
import tempfile

from signer.subcommands.common import HEX64_RE, PACKAGE_RE, detect_profile, fingerprint
from signer.subcommands.formats import (
    TRUST_SCHEMA, check_string, parse_public_key, parse_trust_store,
)


def load_trust_store(path: str, create: bool = False) -> dict:
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        if create and not os.path.lexists(path):
            return {"schema": TRUST_SCHEMA, "keys": []}
        raise
    return parse_trust_store(data)


def save_trust_store(path: str, store: dict) -> None:
    data = json.dumps(store, indent=2).encode("utf-8") + b"\n"
    parse_trust_store(data)
    fd, temporary = tempfile.mkstemp(prefix=".trust-", dir=Path(path).parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def add_key(key_path: str, package: str, store_path: str) -> dict:
    check_string(package, "package", PACKAGE_RE)
    pem = Path(key_path).read_bytes().decode("utf-8")
    key = parse_public_key(pem)
    keyid = fingerprint(key)
    store = load_trust_store(store_path, create=True)
    for entry in store["keys"]:
        if entry["keyid"] == keyid:
            if package not in entry["packages"]:
                entry["packages"].append(package)
                save_trust_store(store_path, store)
            return entry
    entry = {
        "keyid": keyid,
        "algorithm": detect_profile(key),
        "public_key_pem": pem,
        "packages": [package],
    }
    store["keys"].append(entry)
    save_trust_store(store_path, store)
    return entry


def remove_key(keyid: str, store_path: str) -> None:
    check_string(keyid, "keyid", HEX64_RE)
    store = load_trust_store(store_path)
    for index, entry in enumerate(store["keys"]):
        if entry["keyid"] == keyid:
            del store["keys"][index]
            save_trust_store(store_path, store)
            return
    raise ValueError(f"keyid {keyid} not found in trust store")


def run(args) -> int:
    try:
        if args.trust_command == "add":
            entry = add_key(args.key, args.package, args.store)
            print(f"{entry['keyid']} {entry['algorithm']} package={args.package}")
        elif args.trust_command == "list":
            store = load_trust_store(args.store)
            for entry in store["keys"]:
                print(f"{entry['keyid']} {entry['algorithm']} packages={','.join(entry['packages'])}")
            if not store["keys"]:
                print("No trusted keys.")
        elif args.trust_command == "remove":
            remove_key(args.keyid, args.store)
            print(f"removed {args.keyid}")
        else:
            raise ValueError(f"unknown trust command: {args.trust_command}")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
