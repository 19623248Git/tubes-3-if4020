import os
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

from signer.subcommands.common import ECDSA_P256_SHA256, ED25519, RSA_PSS_SHA256, fingerprint


def generate_rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)


def generate_ecdsa_key():
    return ec.generate_private_key(ec.SECP256R1())


def generate_ed25519_key():
    return ed25519.Ed25519PrivateKey.generate()


def private_key_pem(private_key) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def public_key_pem(public_key) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def write_file(path: str, data: bytes, overwrite: bool, private: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if overwrite else os.O_EXCL)
    mode = 0o600 if private else 0o644
    fd = os.open(path, flags, mode)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def run(args) -> int:
    if args.algorithm == RSA_PSS_SHA256:
        key = generate_rsa_key()
    elif args.algorithm == ECDSA_P256_SHA256:
        key = generate_ecdsa_key()
    elif args.algorithm == ED25519:
        key = generate_ed25519_key()
    else:
        print(f"error: unsupported algorithm {args.algorithm}", file=sys.stderr)
        return 2

    priv_path = f"{args.out}.key.pem"
    pub_path = f"{args.out}.pub.pem"

    try:
        write_file(priv_path, private_key_pem(key), args.overwrite, private=True)
        write_file(pub_path, public_key_pem(key.public_key()), args.overwrite, private=False)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(fingerprint(key.public_key()))
    return 0
