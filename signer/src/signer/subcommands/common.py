import hashlib
import json
import re

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

RSA_PSS_SHA256 = "rsa-pss-sha256"
ECDSA_P256_SHA256 = "ecdsa-p256-sha256"
ED25519 = "ed25519"
PROFILES = (RSA_PSS_SHA256, ECDSA_P256_SHA256, ED25519)

MANIFEST_SCHEMA = "minisign-manifest/v1"
BUNDLE_SCHEMA = "minisign-bundle/v1"
MAX_MANIFEST_BYTES = 16 * 1024
MAX_BUNDLE_BYTES = 64 * 1024
MAX_SAFE_INT = 2**53 - 1

PACKAGE_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")
ARTIFACT_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")


def serialize_manifest(
    package: str,
    version: str,
    algorithm: str,
    keyid: str,
    name: str,
    size: int,
    sha256: str,
) -> bytes:
    if not PACKAGE_RE.fullmatch(package):
        raise ValueError(f"invalid package name: {package!r}")
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"invalid version: {version!r}")
    if algorithm not in PROFILES:
        raise ValueError(f"unsupported algorithm: {algorithm!r}")
    if not HEX64_RE.fullmatch(keyid):
        raise ValueError(f"invalid keyid: {keyid!r}")
    if not ARTIFACT_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid artifact name: {name!r}")
    if type(size) is not int or not 0 <= size <= MAX_SAFE_INT:
        raise ValueError(f"invalid artifact size: {size!r}")
    if not HEX64_RE.fullmatch(sha256):
        raise ValueError(f"invalid artifact sha256: {sha256!r}")

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "package": package,
        "version": version,
        "algorithm": algorithm,
        "keyid": keyid,
        "artifact": {"name": name, "size": size, "sha256": sha256},
    }
    return json.dumps(manifest, separators=(",", ":")).encode("utf-8")


def fingerprint(public_key) -> str:
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def detect_profile(key) -> str:
    if isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey, ed25519.Ed25519PrivateKey)):
        key = key.public_key()

    if isinstance(key, rsa.RSAPublicKey):
        if key.key_size != 3072:
            raise ValueError(f"RSA key must be 3072 bits, got {key.key_size}")
        if key.public_numbers().e != 65537:
            raise ValueError(f"RSA public exponent must be 65537, got {key.public_numbers().e}")
        return RSA_PSS_SHA256

    if isinstance(key, ec.EllipticCurvePublicKey):
        if not isinstance(key.curve, ec.SECP256R1):
            raise TypeError(f"EC key must use P-256 (secp256r1), got {key.curve.name}")
        return ECDSA_P256_SHA256

    if isinstance(key, ed25519.Ed25519PublicKey):
        return ED25519

    raise ValueError(f"unsupported key type: {type(key).__name__}")
