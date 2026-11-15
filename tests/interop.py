import base64
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import cryptography

root = Path(__file__).resolve().parents[1]
fixtures = root / "tests/test_cases"
output = root / "tests/results/interop" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
env = dict(os.environ, PYTHONPATH=str(root / "signer/src"), PYTHONDONTWRITEBYTECODE="1")
cli = [sys.executable, "-B", "-m", "signer.xaleidscopix"]
openssl = os.environ.get("OPENSSL") or shutil.which("openssl")
if not openssl:
    sys.exit("openssl not found, install it or set OPENSSL=/path/to/openssl")

PACKAGE = "interop-demo"
VERSION = "1.0.0"
PROFILES = ("rsa-pss-sha256", "ecdsa-p256-sha256", "ed25519")
ARTIFACTS = ("test.txt", "sample.bin", "empty.bin")

KEY_TEXT = {
    "rsa-pss-sha256": ("Public-Key: (3072 bit)", "Exponent: 65537 (0x10001)"),
    "ecdsa-p256-sha256": ("Public-Key: (256 bit)", "ASN1 OID: prime256v1", "NIST CURVE: P-256"),
    "ed25519": ("ED25519 Public-Key:",),
}

GENPKEY = {
    "rsa-pss-sha256": ["-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072", "-pkeyopt", "rsa_keygen_pubexp:65537"],
    "ecdsa-p256-sha256": ["-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-pkeyopt", "ec_param_enc:named_curve"],
    "ed25519": ["-algorithm", "ED25519"],
}
RSA_PSS_OPTS = ["-sigopt", "rsa_padding_mode:pss", "-sigopt", "rsa_pss_saltlen:32", "-sigopt", "rsa_mgf1_md:sha256"]

passed = 0


# logging / running


def record(kind, arguments, result, expected_code):
    log.write(f"\nCOMMAND: {kind} {' '.join(arguments)}\n")
    log.write(f"EXPECTED EXIT: {expected_code}\nACTUAL EXIT: {result.returncode}\n")
    out = result.stdout.decode("utf-8", "replace") if isinstance(result.stdout, bytes) else result.stdout
    err = result.stderr.decode("utf-8", "replace") if isinstance(result.stderr, bytes) else result.stderr
    log.write(f"STDOUT:\n{out}STDERR:\n{err}\n")
    log.flush()


def xaleidscopix(*arguments, expected_code=0):
    arguments = [str(a) for a in arguments]
    result = subprocess.run(cli + arguments, capture_output=True, text=True, env=env)
    record("xaleidscopix", arguments, result, expected_code)
    if result.returncode != expected_code:
        raise AssertionError(f"xaleidscopix {arguments[0]}: expected exit {expected_code}, got {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def run_openssl(*arguments, expected_code=0, binary_stdout=False):
    arguments = [str(a) for a in arguments]
    result = subprocess.run([openssl] + arguments, capture_output=True)
    shown = (
        result if not binary_stdout else subprocess.CompletedProcess(result.args, result.returncode, f"<{len(result.stdout)} bytes>\n", result.stderr)
    )
    record("openssl", arguments, shown, expected_code)
    if result.returncode != expected_code:
        raise AssertionError(f"openssl {arguments[0]}: expected exit {expected_code}, got {result.returncode}: {result.stderr.decode().strip()}")
    return result.stdout


def passes(label, detail):
    global passed
    passed += 1
    message = f"PASS {label}: {detail}"
    print(message)
    log.write(f"{message}\n")
    log.flush()


def expect(condition, label, detail):
    if not condition:
        raise AssertionError(f"{label}: {detail}")


# ECDSA r || s <-> DER


def der_to_rs(der: bytes) -> bytes:
    """ECDSA-Sig-Value ::= SEQUENCE { r INTEGER, s INTEGER } -> 32-byte r || 32-byte s."""
    # A P-256 signature is at most 72 bytes, so every length uses the 1-byte short form.
    expect(der[0] == 0x30 and der[1] == len(der) - 2, "der_to_rs", f"not a DER SEQUENCE: {der.hex()}")
    position, values = 2, []
    for _ in range(2):
        expect(der[position] == 0x02, "der_to_rs", "expected an INTEGER")
        length = der[position + 1]
        values.append(int.from_bytes(der[position + 2 : position + 2 + length], "big"))
        position += 2 + length
    expect(position == len(der), "der_to_rs", "trailing bytes after s")
    return values[0].to_bytes(32, "big") + values[1].to_bytes(32, "big")


def rs_to_der(rs: bytes) -> bytes:
    """32-byte r || 32-byte s -> DER, the form OpenSSL expects."""
    expect(len(rs) == 64, "rs_to_der", f"r || s must be 64 bytes, got {len(rs)}")

    def integer(value: int) -> bytes:
        body = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
        if body[0] & 0x80:  # high bit set would read as negative, so pad with 0x00
            body = b"\x00" + body
        return b"\x02" + bytes([len(body)]) + body

    content = integer(int.from_bytes(rs[:32], "big")) + integer(int.from_bytes(rs[32:], "big"))
    return b"\x30" + bytes([len(content)]) + content


# OpenSSL helpers


def openssl_keyid(public_pem: Path) -> str:
    der = run_openssl("pkey", "-pubin", "-in", public_pem, "-outform", "DER", binary_stdout=True)
    return hashlib.sha256(der).hexdigest()


def openssl_sha256(path: Path) -> str:
    # "-r" prints "<hex> *<file>"
    return run_openssl("dgst", "-sha256", "-r", path).decode().split()[0].lower()


def openssl_check_key_text(profile: str, public_pem: Path, label: str) -> None:
    text = run_openssl("pkey", "-pubin", "-in", public_pem, "-text", "-noout").decode()
    for needle in KEY_TEXT[profile]:
        expect(needle in text, label, f"OpenSSL key dump lacks {needle!r}")


def openssl_verify(profile: str, public_pem: Path, manifest: Path, signature: bytes, folder: Path, expect_valid: bool) -> None:
    code = 0 if expect_valid else 1
    sig_file = folder / "signature.openssl"
    if profile == "rsa-pss-sha256":
        sig_file.write_bytes(signature)
        run_openssl("dgst", "-sha256", *RSA_PSS_OPTS, "-verify", public_pem, "-signature", sig_file, manifest, expected_code=code)
    elif profile == "ecdsa-p256-sha256":
        sig_file.write_bytes(rs_to_der(signature))
        run_openssl("dgst", "-sha256", "-verify", public_pem, "-signature", sig_file, manifest, expected_code=code)
    else:
        sig_file.write_bytes(signature)
        run_openssl("pkeyutl", "-verify", "-pubin", "-inkey", public_pem, "-rawin", "-in", manifest, "-sigfile", sig_file, expected_code=code)


def openssl_sign(profile: str, private_pem: Path, manifest: Path, folder: Path) -> bytes:
    sig_file = folder / "signature.openssl"
    if profile == "rsa-pss-sha256":
        run_openssl("dgst", "-sha256", "-sign", private_pem, *RSA_PSS_OPTS, "-out", sig_file, manifest)
        return sig_file.read_bytes()
    if profile == "ecdsa-p256-sha256":
        run_openssl("dgst", "-sha256", "-sign", private_pem, "-out", sig_file, manifest)
        return der_to_rs(sig_file.read_bytes())
    run_openssl("pkeyutl", "-sign", "-inkey", private_pem, "-rawin", "-in", manifest, "-out", sig_file)
    return sig_file.read_bytes()


def openssl_keypair(profile: str, prefix: Path) -> tuple[Path, Path]:
    private_pem, public_pem = Path(f"{prefix}.key.pem"), Path(f"{prefix}.pub.pem")
    run_openssl("genpkey", *GENPKEY[profile], "-out", private_pem)
    run_openssl("pkey", "-in", private_pem, "-pubout", "-out", public_pem)
    expect(private_pem.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----"), str(prefix), "OpenSSL key is not PKCS8")
    return private_pem, public_pem


def read_bundle(path: Path) -> tuple[bytes, bytes, dict]:
    bundle = json.loads(path.read_bytes())
    manifest = base64.b64decode(bundle["manifest_b64"], validate=True)
    signature = base64.b64decode(bundle["signature_b64"], validate=True)
    return manifest, signature, json.loads(manifest)


def canonical_manifest(profile, keyid, name, size, sha256) -> bytes:
    # Built by this script from the section 2.3 rules, not by xaleidscopix.
    manifest = {
        "schema": "minisign-manifest/v1",
        "package": PACKAGE,
        "version": VERSION,
        "algorithm": profile,
        "keyid": keyid,
        "artifact": {"name": name, "size": size, "sha256": sha256},
    }
    return json.dumps(manifest, separators=(",", ":")).encode("ascii")


# the three directions


def direction_a(profile: str) -> None:
    folder = output / profile / "A-xaleidscopix-to-openssl"
    folder.mkdir(parents=True)
    prefix = folder / "xaleidscopix-publisher"
    keyid = xaleidscopix("keygen", "--algorithm", profile, "--out", prefix).strip()
    public_pem = Path(f"{prefix}.pub.pem")

    label = f"A {profile} key"
    expect(openssl_keyid(public_pem) == keyid, label, "keyid from keygen differs from SHA-256 of OpenSSL's DER export")
    openssl_check_key_text(profile, public_pem, label)
    passes(label, "OpenSSL parses the SPKI key, parameters match the profile, keyid matches")

    for name in ARTIFACTS:
        label = f"A {profile} {name}"
        artifact = folder / name
        artifact.write_bytes((fixtures / name).read_bytes())
        bundle = folder / f"{name}.bundle.json"
        xaleidscopix("sign", "--file", artifact, "--package", PACKAGE, "--version", VERSION, "--key", f"{prefix}.key.pem", "--out", bundle)
        manifest_bytes, signature, manifest = read_bundle(bundle)
        manifest_file = folder / f"{name}.manifest"
        manifest_file.write_bytes(manifest_bytes)

        expect(manifest["keyid"] == keyid, label, "manifest keyid differs")
        expect(manifest["artifact"]["sha256"] == openssl_sha256(artifact), label, "artifact SHA-256 differs from OpenSSL's")
        expect(manifest["artifact"]["size"] == artifact.stat().st_size, label, "artifact size differs")
        expected_length = 384 if profile == "rsa-pss-sha256" else 64
        expect(len(signature) == expected_length, label, f"signature is {len(signature)} bytes, expected {expected_length}")

        openssl_verify(profile, public_pem, manifest_file, signature, folder, expect_valid=True)

        tampered = bytearray(manifest_bytes)
        tampered[len(tampered) // 2] ^= 0x01
        tampered_file = folder / f"{name}.manifest.tampered"
        tampered_file.write_bytes(bytes(tampered))
        openssl_verify(profile, public_pem, tampered_file, signature, folder, expect_valid=False)
        passes(label, "OpenSSL verifies the signature and rejects a manifest with one changed byte")


def direction_b(profile: str) -> None:
    folder = output / profile / "B-openssl-to-xaleidscopix"
    folder.mkdir(parents=True)
    private_pem, public_pem = openssl_keypair(profile, folder / "openssl-publisher")
    keyid = openssl_keyid(public_pem)
    store = folder / "trust.json"

    label = f"B {profile} key"
    added = xaleidscopix("trust", "add", "--key", public_pem, "--package", PACKAGE, "--store", store)
    expect(added.split()[0] == keyid, label, f"trust add printed keyid {added.split()[0]}, OpenSSL gives {keyid}")
    passes(label, "xaleidscopix accepts the OpenSSL key, keyid matches")

    for name in ARTIFACTS:
        label = f"B {profile} {name}"
        artifact = folder / name
        artifact.write_bytes((fixtures / name).read_bytes())
        manifest_bytes = canonical_manifest(profile, keyid, name, artifact.stat().st_size, openssl_sha256(artifact))
        manifest_file = folder / f"{name}.manifest"
        manifest_file.write_bytes(manifest_bytes)
        signature = openssl_sign(profile, private_pem, manifest_file, folder)

        def write_bundle(path, sig):
            path.write_text(
                json.dumps(
                    {
                        "schema": "minisign-bundle/v1",
                        "manifest_b64": base64.b64encode(manifest_bytes).decode(),
                        "signature_b64": base64.b64encode(sig).decode(),
                    }
                ),
                encoding="utf-8",
            )

        bundle = folder / f"{name}.bundle.json"
        write_bundle(bundle, signature)
        text = xaleidscopix(
            "verify", "--file", artifact, "--bundle", bundle, "--trust-store", store, "--package", PACKAGE, "--version", VERSION, "--json"
        )
        (folder / f"{name}.verification.json").write_text(text, encoding="utf-8")
        result = json.loads(text)
        expect(result["status"] == "OK" and result["valid"] is True, label, f"expected OK, got {result}")

        flipped = bytearray(signature)
        flipped[-1] ^= 0x01
        bad_bundle = folder / f"{name}.bitflip.bundle.json"
        write_bundle(bad_bundle, bytes(flipped))
        text = xaleidscopix(
            "verify",
            "--file",
            artifact,
            "--bundle",
            bad_bundle,
            "--trust-store",
            store,
            "--package",
            PACKAGE,
            "--version",
            VERSION,
            "--json",
            expected_code=1,
        )
        (folder / f"{name}.bitflip.verification.json").write_text(text, encoding="utf-8")
        result = json.loads(text)
        expect(result["status"] == "INVALID_SIGNATURE", label, f"bit flip: expected INVALID_SIGNATURE, got {result}")
        passes(label, "xaleidscopix verifies an OpenSSL signature (OK) and rejects one flipped bit (INVALID_SIGNATURE)")


def direction_c(profile: str) -> None:
    folder = output / profile / "C-openssl-key-xaleidscopix-sign"
    folder.mkdir(parents=True)
    private_pem, public_pem = openssl_keypair(profile, folder / "openssl-publisher")
    name = "sample.bin"
    artifact = folder / name
    artifact.write_bytes((fixtures / name).read_bytes())
    bundle = folder / f"{name}.bundle.json"
    xaleidscopix("sign", "--file", artifact, "--package", PACKAGE, "--version", VERSION, "--key", private_pem, "--out", bundle)
    manifest_bytes, signature, manifest = read_bundle(bundle)
    manifest_file = folder / f"{name}.manifest"
    manifest_file.write_bytes(manifest_bytes)
    label = f"C {profile} {name}"
    expect(manifest["algorithm"] == profile, label, f"profile detected as {manifest['algorithm']}")
    expect(manifest["keyid"] == openssl_keyid(public_pem), label, "keyid differs")
    openssl_verify(profile, public_pem, manifest_file, signature, folder, expect_valid=True)
    passes(label, "xaleidscopix signs with an OpenSSL-generated key, OpenSSL verifies it")


output.mkdir(parents=True)
with (output / "results.txt").open("w", encoding="utf-8") as log:
    openssl_version = subprocess.run([openssl, "version"], capture_output=True, text=True).stdout.strip()
    log.write(f"Python {platform.python_version()}, cryptography {cryptography.__version__}, {platform.platform()}\n")
    log.write(f"Independent implementation: {openssl_version} ({openssl})\n")
    log.write("All private keys below are TEST-ONLY, generated for this run.\n")
    for profile in PROFILES:
        direction_a(profile)
        direction_b(profile)
        direction_c(profile)
    summary = f"All {passed} interoperability checks passed against {openssl_version}."
    log.write(f"\n{summary}\n")

print(f"{summary} Results: {output / 'results.txt'}")
