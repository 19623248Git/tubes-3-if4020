import hashlib
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from signer.subcommands.common import (
    ECDSA_P256_SHA256, ED25519, MAX_BUNDLE_BYTES, PACKAGE_RE, PROFILES,
    RSA_PSS_SHA256, VERSION_RE, detect_profile,
)
from signer.subcommands.formats import FormatError, parse_bundle, parse_public_key, parse_trust_store


def verify_signature(public_key, profile: str, manifest: bytes, signature: bytes) -> bool:
    try:
        if detect_profile(public_key) != profile:
            return False
        if profile == RSA_PSS_SHA256:
            if len(signature) != 384:
                return False
            public_key.verify(
                signature, manifest,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                hashes.SHA256(),
            )
        elif profile == ECDSA_P256_SHA256:
            if len(signature) != 64:
                return False
            r = int.from_bytes(signature[:32], "big")
            s = int.from_bytes(signature[32:], "big")
            der = encode_dss_signature(r, s)
            public_key.verify(der, manifest, ec.ECDSA(hashes.SHA256()))
        elif profile == ED25519:
            if len(signature) != 64:
                return False
            public_key.verify(signature, manifest)
        else:
            return False
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True

def verification_result(status: str, message: str, manifest=None) -> dict:
    manifest = manifest or {}
    return {
        "valid": status == "OK",
        "status": status,
        "message": message,
        **{field: manifest.get(field) for field in ("algorithm", "keyid", "package", "version")},
    }


def verify(file: str, bundle: str, trust_store: str, package: str, version: str) -> dict:
    manifest = None
    if type(package) is not str or not PACKAGE_RE.fullmatch(package):
        return verification_result("INPUT_ERROR", "invalid expected package")
    if type(version) is not str or not VERSION_RE.fullmatch(version):
        return verification_result("INPUT_ERROR", "invalid expected version")
    try:
        with open(file, "rb") as artifact:
            with open(bundle, "rb") as source:
                bundle_data = source.read(MAX_BUNDLE_BYTES + 1)
            trust_data = Path(trust_store).read_bytes()
            manifest_bytes, signature, manifest = parse_bundle(bundle_data)
            store = parse_trust_store(trust_data)

            profile = manifest["algorithm"]
            if profile not in PROFILES:
                return verification_result("UNSUPPORTED_ALGORITHM", "unsupported algorithm", manifest)
            entry = next((entry for entry in store["keys"] if entry["keyid"] == manifest["keyid"]), None)
            if entry is None or entry["algorithm"] != profile or package not in entry["packages"]:
                return verification_result("KEY_NOT_TRUSTED", "key is not trusted for this package and profile", manifest)

            public_key = parse_public_key(entry["public_key_pem"])
            if not verify_signature(public_key, profile, manifest_bytes, signature):
                return verification_result("INVALID_SIGNATURE", "manifest signature is invalid", manifest)
            if manifest["package"] != package or manifest["version"] != version or manifest["artifact"]["name"] != os.path.basename(file):
                return verification_result("METADATA_MISMATCH", "package, version, or artifact filename differs", manifest)

            digest = hashlib.file_digest(artifact, "sha256").hexdigest()
            if artifact.tell() != manifest["artifact"]["size"] or digest != manifest["artifact"]["sha256"]:
                return verification_result("ARTIFACT_MISMATCH", "artifact size or SHA-256 differs", manifest)
    except FormatError as error:
        return verification_result("FORMAT_ERROR", str(error), manifest)
    except (OSError, ValueError) as error:
        return verification_result("INPUT_ERROR", str(error), manifest)
    return verification_result("OK", "signature and artifact are valid", manifest)


def run(args) -> int:
    result = verify(args.file, args.bundle, args.trust_store, args.package, args.version)
    if args.json:
        print(json.dumps(result))
    else:
        print(f"{result['status']}: {result['message']}")
    return 0 if result["valid"] else (2 if result["status"] == "INPUT_ERROR" else 1)
