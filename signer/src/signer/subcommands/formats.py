import base64
import binascii
import json
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from signer.subcommands.common import (
    BUNDLE_SCHEMA, HEX64_RE, MANIFEST_SCHEMA, MAX_BUNDLE_BYTES,
    MAX_MANIFEST_BYTES, PACKAGE_RE, detect_profile, fingerprint, serialize_manifest,
)

TRUST_SCHEMA = "minisign-trust/v1"

class FormatError(ValueError):
    pass

def parse_json_strict(data: bytes):
    def unique_fields(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise FormatError(f"duplicate field: {name}")
            result[name] = value
        return result

    def reject_constant(value):
        raise FormatError(f"invalid JSON constant: {value}")

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique_fields, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise FormatError(str(error)) from error


def check_fields(value, names, label):
    if type(value) is not dict or set(value) != set(names):
        raise FormatError(f"{label} must contain exactly: {', '.join(names)}")


def check_string(value, label, pattern=None):
    if type(value) is not str or (pattern is not None and not pattern.fullmatch(value)):
        raise FormatError(f"invalid {label}")


def decode_base64_strict(text: str) -> bytes:
    check_string(text, "Base64 string")
    try:
        decoded = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error) as error:
        raise FormatError("invalid Base64 encoding") from error
    if base64.b64encode(decoded).decode("ascii") != text:
        raise FormatError("noncanonical Base64 encoding")
    return decoded


def parse_manifest(data: bytes) -> dict:
    if len(data) > MAX_MANIFEST_BYTES:
        raise FormatError("manifest exceeds 16 KiB")
    manifest = parse_json_strict(data)
    check_fields(manifest, ("schema", "package", "version", "algorithm", "keyid", "artifact"), "manifest")
    for name in ("schema", "package", "version", "algorithm", "keyid"):
        check_string(manifest[name], name)
    if manifest["schema"] != MANIFEST_SCHEMA or not manifest["algorithm"].isascii():
        raise FormatError("invalid manifest schema or non-ASCII algorithm")
    artifact = manifest["artifact"]
    check_fields(artifact, ("name", "size", "sha256"), "artifact")
    check_string(artifact["name"], "artifact name")
    check_string(artifact["sha256"], "artifact hash")
    try:
        canonical = serialize_manifest(
            manifest["package"], manifest["version"], manifest["algorithm"], manifest["keyid"],
            artifact["name"], artifact["size"], artifact["sha256"], check_algorithm=False,
        )
    except ValueError as error:
        raise FormatError(str(error)) from error
    if canonical != data:
        raise FormatError("manifest is not canonically serialized")
    return manifest


def parse_bundle(data: bytes) -> tuple[bytes, bytes, dict]:
    """Return original manifest bytes, signature bytes, and parsed manifest."""
    if len(data) > MAX_BUNDLE_BYTES:
        raise FormatError("bundle exceeds 64 KiB")
    bundle = parse_json_strict(data)
    check_fields(bundle, ("schema", "manifest_b64", "signature_b64"), "bundle")
    if bundle["schema"] != BUNDLE_SCHEMA:
        raise FormatError("invalid bundle schema")
    manifest_bytes = decode_base64_strict(bundle["manifest_b64"])
    signature = decode_base64_strict(bundle["signature_b64"])
    return manifest_bytes, signature, parse_manifest(manifest_bytes)


def parse_public_key(pem: str):
    check_string(pem, "public_key_pem")
    header, footer = "-----BEGIN PUBLIC KEY-----", "-----END PUBLIC KEY-----"
    text = pem.strip()
    if not text.startswith(header) or not text.endswith(footer):
        raise FormatError("public key must use SPKI PUBLIC KEY PEM")
    der = decode_base64_strict("".join(text[len(header):-len(footer)].split()))
    try:
        key = serialization.load_der_public_key(der)
        detect_profile(key)
        exported = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    except (ValueError, TypeError, UnsupportedAlgorithm) as error:
        raise FormatError(f"invalid public key: {error}") from error
    if der != exported:
        raise FormatError("public key does not use the required SPKI encoding")
    return key


def parse_trust_store(data: bytes) -> dict:
    store = parse_json_strict(data)
    check_fields(store, ("schema", "keys"), "trust store")
    if store["schema"] != TRUST_SCHEMA or type(store["keys"]) is not list:
        raise FormatError("invalid trust store schema or keys array")
    seen = set()
    for entry in store["keys"]:
        check_fields(entry, ("keyid", "algorithm", "public_key_pem", "packages"), "trust entry")
        check_string(entry["keyid"], "keyid", HEX64_RE)
        check_string(entry["algorithm"], "algorithm")
        key = parse_public_key(entry["public_key_pem"])
        if entry["algorithm"] != detect_profile(key) or entry["keyid"] != fingerprint(key):
            raise FormatError("trust entry algorithm or fingerprint does not match public key")
        if entry["keyid"] in seen:
            raise FormatError("duplicate trust-store keyid")
        seen.add(entry["keyid"])
        packages = entry["packages"]
        if type(packages) is not list or not packages:
            raise FormatError("packages must be a nonempty array")
        for package in packages:
            check_string(package, "package", PACKAGE_RE)
        if len(set(packages)) != len(packages):
            raise FormatError("duplicate package permission")
    return store
