import os
from pathlib import Path
import shutil
import sys
import tempfile

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


def write_file(path: Path, data: bytes, private: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    mode = 0o600 if private else 0o644
    fd = os.open(path, flags, mode)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def write_keypair(prefix: str, key, overwrite: bool) -> None:
    paths = (Path(f"{prefix}.key.pem"), Path(f"{prefix}.pub.pem"))
    for path in paths:
        if os.path.lexists(path):
            if not overwrite:
                raise FileExistsError(f"output {path} already exists; use --overwrite explicitly")
            if path.is_symlink() or not path.is_file():
                raise OSError(f"output {path} must be a regular file")

    staging = Path(tempfile.mkdtemp(prefix=".keygen-", dir=paths[0].parent))
    backups, published = {}, []
    cleanup = True
    try:
        staged = (staging / "private.pem", staging / "public.pem")
        write_file(staged[0], private_key_pem(key), private=True)
        write_file(staged[1], public_key_pem(key.public_key()), private=False)
        for index, path in enumerate(paths):
            if overwrite and path.exists():
                backups[path] = staging / f"backup-{index}.pem"
                shutil.copy2(path, backups[path])
        try:
            for source, destination in zip(staged, paths):
                if overwrite:
                    os.replace(source, destination)
                else:
                    os.link(source, destination)
                published.append(destination)
        except OSError:
            try:
                for path in reversed(published):
                    if path in backups:
                        os.replace(backups[path], path)
                    else:
                        path.unlink()
            except OSError as error:
                cleanup = False
                raise OSError(f"rollback failed; recovery files retained at {staging}: {error}") from error
            raise
    finally:
        if cleanup:
            shutil.rmtree(staging)


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

    try:
        write_keypair(args.out, key, args.overwrite)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(fingerprint(key.public_key()))
    return 0
