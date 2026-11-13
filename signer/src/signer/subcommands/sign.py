import base64
import hashlib
import json
import os
import sys

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from signer.subcommands.common import (
    BUNDLE_SCHEMA,
    ECDSA_P256_SHA256,
    ED25519,
    MAX_MANIFEST_BYTES,
    RSA_PSS_SHA256,
    detect_profile,
    fingerprint,
    serialize_manifest,
)

PKCS8_PEM_HEADER = b"-----BEGIN PRIVATE KEY-----"


class SignError(Exception):
    """Any input or I/O problem. Always ends the command with exit code 2."""


def load_private_key(path: str):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise SignError(f"cannot read private key {path}: {e.strerror}")

    if not data.lstrip().startswith(PKCS8_PEM_HEADER):
        raise SignError(f"{path} is not a PKCS8 PEM private key (expected '{PKCS8_PEM_HEADER.decode()}')")
    try:
        return serialization.load_pem_private_key(data, password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm) as e:
        raise SignError(f"cannot load private key {path}: {e}")


def hash_artifact(path: str) -> tuple[int, str]:
    try:
        with open(path, "rb") as f:
            digest = hashlib.file_digest(f, "sha256")
            size = f.tell()
    except OSError as e:
        raise SignError(f"cannot read artifact {path}: {e.strerror}")
    return size, digest.hexdigest()


def sign_manifest(private_key, profile: str, manifest: bytes) -> bytes:
    if profile == RSA_PSS_SHA256:
        return private_key.sign(
            manifest,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            hashes.SHA256(),
        )

    if profile == ECDSA_P256_SHA256:
        der = private_key.sign(manifest, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")

    if profile == ED25519:
        return private_key.sign(manifest)

    raise SignError(f"unsupported algorithm: {profile}")


def write_bundle(path: str, bundle: dict) -> None:
    data = json.dumps(bundle, indent=2).encode("utf-8") + b"\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except FileExistsError:
        raise SignError(f"output {path} already exists; remove it or choose another --out")
    except OSError as e:
        raise SignError(f"cannot write bundle {path}: {e.strerror}")


def sign(file: str, package: str, version: str, key_path: str, out: str) -> str:
    private_key = load_private_key(key_path)
    try:
        profile = detect_profile(private_key)
    except (ValueError, TypeError) as e:
        raise SignError(f"private key does not match any profile: {e}")

    keyid = fingerprint(private_key.public_key())
    size, sha256 = hash_artifact(file)

    try:
        manifest = serialize_manifest(
            package=package,
            version=version,
            algorithm=profile,
            keyid=keyid,
            name=os.path.basename(file),
            size=size,
            sha256=sha256,
        )
    except ValueError as e:
        raise SignError(str(e))

    if len(manifest) > MAX_MANIFEST_BYTES:
        raise SignError(f"manifest is {len(manifest)} bytes, limit is {MAX_MANIFEST_BYTES}")

    signature = sign_manifest(private_key, profile, manifest)

    bundle = {
        "schema": BUNDLE_SCHEMA,
        "manifest_b64": base64.b64encode(manifest).decode("ascii"),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    write_bundle(out, bundle)
    return keyid


def run(args) -> int:
    try:
        keyid = sign(args.file, args.package, args.version, args.key, args.out)
    except SignError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"signed {os.path.basename(args.file)} -> {args.out} (keyid {keyid})")
    return 0
